#!/usr/bin/env python3
import argparse
import ast
import gzip
import io
import json
import os
import sys
from collections.abc import Sequence
from typing import Any, Dict, List, Tuple


class _LazySequence(Sequence):
    """Evaluate generated oracle results only for the cases being requested."""

    def __init__(self, indices, get_item):
        self.indices = indices
        self.get_item = get_item

    def __len__(self):
        return len(self.indices)

    def __getitem__(self, index):
        if isinstance(index, slice):
            return _LazySequence(self.indices[index], self.get_item)
        return self.get_item(self.indices[index])


def _tri(n):
    if n == 0:
        return [1]
    if n == 1:
        return [1, 3]
    ans = [1, 3]
    for i in range(2, n + 1):
        ans.append(1 + i / 2 if i % 2 == 0 else ans[-1] + ans[-2] + 1 + (i + 1) / 2)
    return ans


def _special_factorial(n):
    fac = ans = 1
    for i in range(2, n + 1):
        fac *= i
        ans *= fac
    return ans


# Exact AST matches for the six reference oracles in the bundled dataset.
# Dataset code is never executed. Unrecognized oracles are rejected explicitly.
_ORACLES = [
    ('string', 'return [string[:(i + 1)] for i in range(len(string))]',
     lambda string: [string[:i + 1] for i in range(len(string))]),
    ('n', 'return " ".join(map(str, range(n + 1)))',
     lambda n: ' '.join(map(str, range(n + 1)))),
    ('n', 'if n == 1: return 1\nreturn 18 * 10 ** (n - 2)',
     lambda n: 1 if n == 1 else 18 * 10 ** (n - 2)),
    ('n', 'ans, num = [], n\nfor _ in range(n):\n    ans.append(num)\n    num += 2\nreturn ans',
     lambda n: list(range(n, 3 * n, 2))),
    ('n', 'if n == 0: return [1]\nif n == 1: return [1, 3]\nans = [1, 3]\nfor i in range(2, n + 1):\n    if i % 2 == 0:\n        ans.append(1 + i / 2)\n    else:\n        ans.append(ans[-1] + ans[-2] + 1 + (i + 1) / 2)\nreturn ans',
     _tri),
    ('n', 'fac, ans = 1, 1\nfor i in range(2, n + 1):\n    fac *= i\n    ans *= fac\nreturn ans',
     _special_factorial),
]


class HumanEvalPairs:
    def __init__(self, path: str):
        self.path = path
        self.rows: List[Dict[str, Any]] = self._load_jsonl(path)
        if not self.rows:
            raise ValueError('empty or invalid JSONL')

    @staticmethod
    def _open_maybe_gzip(path: str) -> io.TextIOBase:
        if path.endswith('.gz'):
            return io.TextIOWrapper(gzip.open(path, 'rb'), encoding='utf-8')
        return open(path, 'r', encoding='utf-8')

    @classmethod
    def _load_jsonl(cls, path: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        with cls._open_maybe_gzip(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
        return rows

    @staticmethod
    def _extract_tests_str(obj: Dict[str, Any]) -> str:
        for key in ('tests', 'test', 'unit_tests', 'test_code', 'prompt_tests', 'check'):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                return v
        plus = obj.get('plus')
        if isinstance(plus, dict):
            v = plus.get('tests')
            if isinstance(v, str) and v.strip():
                return v
        return ''

    @classmethod
    def _parse_inputs_results(cls, tests: str) -> Tuple[List[Any], Sequence]:
        try:
            tree = ast.parse(tests)
            check = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'check'), None)
            assignments = {}
            for node in check.body if check else tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in ('inputs', 'results'):
                            assignments[target.id] = ast.literal_eval(node.value)
            inputs = assignments.get('inputs')
            results = assignments.get('results')
        except Exception as e:
            raise ValueError(f'failed to parse inputs/results as Python literals: {e}')
        if not isinstance(inputs, list):
            raise ValueError('inputs list not found in tests field')
        if results is None:
            reference = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'ref_func'), None)
            if reference is None or len(reference.args.args) != 1:
                raise ValueError('results list or supported ref_func not found in tests field')
            body = ast.dump(ast.Module(body=reference.body, type_ignores=[]))
            oracle = next((fn for arg, source, fn in _ORACLES
                           if reference.args.args[0].arg == arg and body == ast.dump(ast.parse(source))), None)
            if oracle is None:
                raise ValueError('unsupported ref_func: only bundled reference oracle bodies are accepted')
            if any(not isinstance(args, (list, tuple)) or len(args) != 1 for args in inputs):
                raise ValueError('reference oracle requires one argument per test case')
            results = _LazySequence(range(len(inputs)), lambda i: oracle(inputs[i][0]))
        elif not isinstance(results, list):
            raise ValueError('results is not a list')
        if len(inputs) != len(results):
            raise ValueError('inputs/results lengths differ')
        return inputs, results

    def get_pairs(self, index: int, one_based: bool = False) -> Sequence:
        idx = index - 1 if one_based else index
        if idx < 0 or idx >= len(self.rows):
            raise IndexError(f'index {index} out of range (n={len(self.rows)})')
        r = self.rows[idx]
        tests_str = self._extract_tests_str(r)
        if not tests_str:
            raise ValueError('tests field not found or empty')
        inputs, results = self._parse_inputs_results(tests_str)
        return _LazySequence(range(len(inputs)), lambda i: [inputs[i], results[i]])

    def get_results(self, index: int, one_based: bool = False) -> Sequence:
        idx = index - 1 if one_based else index
        if idx < 0 or idx >= len(self.rows):
            raise IndexError(f'index {index} out of range (n={len(self.rows)})')
        r = self.rows[idx]
        tests_str = self._extract_tests_str(r)
        if not tests_str:
            raise ValueError('tests field not found or empty')
        _, results = self._parse_inputs_results(tests_str)
        return results


def main() -> None:
    ap = argparse.ArgumentParser(description='Extract (inputs, results) pairs or results list from HumanEval/HumanEval+ item')
    ap.add_argument('-p', '--path', default='HumanEvalPlus.jsonl', help='Path to JSONL(.gz)')
    ap.add_argument('-i', '--index', required=True, type=int, help='Item index (0-based by default)')
    ap.add_argument('--one-based', action='store_true', help='Treat index as 1-based')
    ap.add_argument('--mode', choices=['pairs', 'results'], default='pairs', help='Output pairs or results list')
    ap.add_argument('-o', '--out', default='', help='Output file (default: stdout)')
    args = ap.parse_args()

    if not os.path.exists(args.path):
        print(f'error: file not found: {args.path}', file=sys.stderr)
        sys.exit(2)

    try:
        helper = HumanEvalPairs(args.path)
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(2)

    try:
        if args.mode == 'pairs':
            data = helper.get_pairs(args.index, one_based=args.one_based)
        else:
            data = helper.get_results(args.index, one_based=args.one_based)
    except Exception as e:
        print(f'error: {e}', file=sys.stderr)
        sys.exit(2)

    # Stream generated results rather than materializing every large oracle output.
    target = open(args.out, 'w', encoding='utf-8') if args.out else sys.stdout
    try:
        target.write('[')
        for i, item in enumerate(data):
            if i:
                target.write(', ')
            json.dump(item, target, ensure_ascii=False)
        target.write(']\n')
    finally:
        if args.out:
            target.close()


if __name__ == '__main__':
    main()

