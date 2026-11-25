#!/usr/bin/env python3
import argparse
import os
import sys
import re
import tempfile
import subprocess
from typing import Any, List, Tuple
from config import LLMConfig, SKIP_ON_FIRST_FAIL
from llm import Chatbot, LLMError
from verify import verify_coq_content, VerificationError
from proof_gen import CoqProofGenerator
from logger import get_logger


class CoqTester:
    """Coq test case prover class"""

    def __init__(self):
        self.generator = CoqProofGenerator()
        self.type_name = self.generator.type_name
        self.spec_input_dir = self.generator.spec_input_dir
        self.spec_output_dir = self.generator.spec_output_dir
        self.spec_bad_dir = self.generator.spec_bad_dir
        self.root_dir = self.generator.root_dir
        self.model_name = self.generator.model_name
        self.logger = None  # Will be initialized when needed

    def read_existing_proof(self, spec_id: str) -> str:
        """Read existing proof file (from output directory)

        Args:
            spec_id: Specification identifier, can be a number (e.g., "1") or underscore format (e.g., "1_")
        """
        proof_path = os.path.join(self.spec_output_dir, f"{spec_id}.v")
        if not os.path.exists(proof_path):
            raise FileNotFoundError(f"Proof file not found: {proof_path}")

        with open(proof_path, 'r', encoding='utf-8') as f:
            return f.read()

    def format_example_for_coq(self, example: List[Any]) -> str:
        """Convert Python test case to Coq format"""
        def convert_value(val):
            if isinstance(val, bool):
                return "true" if val else "false"
            elif isinstance(val, int):
                return f"{val}%Z"
            elif isinstance(val, float):
                return f"{val}%R"
            elif isinstance(val, str):
                return f'"{val}"'
            elif isinstance(val, list):
                if not val:
                    return "[]"
                elements = [convert_value(x) for x in val]
                return f"[{'; '.join(elements)}]"
            else:
                return str(val)

        if len(example) == 2:
            input_val, output_val = example
            return f"input = {convert_value(input_val)}, output = {convert_value(output_val)}"
        else:
            return str(example)


    def call_llm_for_test_proof(self, existing_output_content: str, first_test_case: str, test_case: str, error_info: str = "") -> str:
        """Call LLM to generate Coq proof for test case.
        Note: existing_output_content is the full content of output/i.v (including spec and proof for first test case),
        only use this as reference to generate Example proof for "remaining test cases", do not repeat the spec.
        """
        base_prompt = f"""You are given the full content of an existing Coq output file for a HumanEval spec.
It already includes the specification definitions and the proof for the first test case.

Existing Coq output file content
specification for the first test case `{first_test_case}`:
```coq
{existing_output_content}
```

Now, generate a Coq Example proof for the following new test case `{test_case}` and replace the first test case:


Requirements:
- Return the full content of the Coq output file for the new test case.
- Do NOT add any natural language comments.
- End with Qed.
"""

        if error_info:
            prompt = f"""{base_prompt}

IMPORTANT: The previous proof attempt failed with the following error:
{error_info}

Please fix the proof based on this error information and generate a corrected version:
"""
        else:
            prompt = base_prompt

        llm = Chatbot(LLMConfig(api_model=self.model_name))
        proof = llm.chat(prompt)

        # Remove possible code block markers
        proof = proof.strip()
        if proof.startswith('```coq'):
            proof = proof[6:]
        if proof.startswith('```'):
            proof = proof[3:]
        if proof.endswith('```'):
            proof = proof[:-3]
        proof = proof.strip()

        return proof

    def verify_coq_proof(self, combined_content: str) -> Tuple[bool, str]:
        return verify_coq_content(combined_content, timeout_seconds=30, strict_errors=True)


    def save_test_proof(self, spec_id: str, test_idx: int, proof: str) -> None:
        """Save test case proof to spec/test/{spec_id}/n.v file

        Args:
            spec_id: Specification identifier, can be a number (e.g., "1") or underscore format (e.g., "1_")
            test_idx: Test case index
            proof: Proof content
        """
        spec_root = self.root_dir
        test_root = os.path.join(spec_root, f"test/{self.model_name}")
        test_dir = os.path.join(test_root, spec_id)
        os.makedirs(test_dir, exist_ok=True)

        test_file = os.path.join(test_dir, f"{test_idx}.v")
        with open(test_file, 'x', encoding='utf-8') as f:
            f.write(proof)
        self.logger.info(f"Saved test proof to: {test_file}")

    def save_bad_proof(self, spec_id: str, test_idx: int, proof: str) -> None:
        """Save failed proof to bad folder

        Args:
            spec_id: Specification identifier
            test_idx: Test case index
            proof: Failed proof content
        """
        os.makedirs(self.spec_bad_dir, exist_ok=True)
        bad_file = os.path.join(self.spec_bad_dir, f"{spec_id}_{test_idx}.v")
        if os.path.exists(bad_file):
            return
        with open(bad_file, 'x', encoding='utf-8') as f:
            f.write(proof)
        if self.logger:
            self.logger.info(f"Saved bad proof to: {bad_file}")

    def sat_spec(self, spec_id: str):
        """Count input cases without requiring an existing proof or API access."""
        numeric_id = int(spec_id.rstrip('_'))
        count = len(self.generator.get_pairs(numeric_id))
        print(count)
        return count

    def test_spec(self, spec_id: str, max_attempts: int = 3, skip_on_first_fail: bool = None) -> List[Tuple[int, bool, str]]:
        """Test all test cases for specification

        Args:
            spec_id: Specification identifier, can be a number (e.g., "1") or underscore format (e.g., "1_")
            max_attempts: Maximum number of attempts per test case
            skip_on_first_fail: If True, stop immediately when first test case fails. If None, use SKIP_ON_FIRST_FAIL from config
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        # Extract numeric part from spec_id for getting test cases
        numeric_id = int(re.sub(r'[^0-9]', '', spec_id)) if spec_id else 0

        # If skip_on_first_fail is not specified, use value from config
        if skip_on_first_fail is None:
            skip_on_first_fail = SKIP_ON_FIRST_FAIL

        results = []
        try:
            # Read existing proof file (including spec and proof for first test case)
            existing_output_content = self.read_existing_proof(spec_id)
            valid, error = self.verify_coq_proof(existing_output_content)
            if not valid:
                return [(1, False, error)]

            # Get all test cases; first one is already in output/{spec_id}.v
            all_pairs_full = self.generator.get_pairs(numeric_id)
            # Control how many cases to take
            all_pairs = all_pairs_full[1:]


            results = [(1, True, "")]

            # First test case (already exists in output/{spec_id}.v)
            if not all_pairs_full:
                print("No test pairs found.")
                return []
            first_test_case_str = self.format_example_for_coq(all_pairs_full[0])

            for offset, example in enumerate(all_pairs, start=2):


                test_case_str = self.format_example_for_coq(example)
                test_idx = offset
                saved = os.path.join(self.root_dir, "test", self.model_name, spec_id, f"{test_idx}.v")
                if os.path.exists(saved):
                    with open(saved, encoding="utf-8") as stream:
                        valid, error = self.verify_coq_proof(stream.read())
                    results.append((test_idx, valid, error))
                    if not valid and skip_on_first_fail:
                        return results
                    continue



                self.logger = get_logger(model_name=self.model_name, spec_id=numeric_id, test_id=test_idx, type_name=self.type_name)

                self.logger.info(f"\n=== Testing case {test_idx} for spec {spec_id} ===")

                self.logger.info(f"Test case: {test_case_str}")

                error_info = ""
                success = False
                final_error = ""
                final_proof = ""

                for attempt in range(max_attempts):
                    self.logger.info(f"Attempt {attempt + 1}/{max_attempts}")

                    # Generate proof (reference output/{spec_id}.v, do not repeat spec)
                    proof = self.call_llm_for_test_proof(existing_output_content, first_test_case_str, test_case_str, error_info)

                    # Output generated proof
                    self.logger.print_section(f"Generated Proof for Attempt {attempt + 1}")
                    self.logger.info(proof)
                    self.logger.print_separator()


                    is_valid, error_output = self.verify_coq_proof(proof)

                    if is_valid:
                        self.logger.info(f"✓ Test case {test_idx} passed!")
                        success = True
                        final_proof = proof
                        break
                    else:
                        self.logger.info(f"✗ Test case {test_idx} failed, attempt {attempt + 1}")
                        self.logger.info(f"Error: {error_output}")
                        error_info = error_output
                        final_error = error_output
                        final_proof = proof  # Save last attempt's proof

                if not success:
                    self.logger.info(f"✗ Test case {test_idx} failed after {max_attempts} attempts")
                    # Save failed proof to bad folder
                    if final_proof:
                        self.save_bad_proof(spec_id, test_idx, final_proof)

                # Only save if verification succeeds
                if success and final_proof:
                    self.save_test_proof(spec_id, test_idx, final_proof)

                results.append((test_idx, success, final_error))

                # First Fail logic: if enabled and current test case fails, return immediately
                if skip_on_first_fail and not success:
                    self.logger.info(f"First fail detected at test case {test_idx}. Stopping test execution.")
                    self.logger.close()
                    return results

                self.logger.close()

            return results

        except Exception as e:
            if self.logger is not None:
                self.logger.close()
            print(f"Error testing spec {spec_id}: {e}")
            return results + [(0, False, str(e))]


def main():
    parser = argparse.ArgumentParser(
        description='Test Coq proof for HumanEval specification (serial version)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 1
  %(prog)s 1_ --max-attempts 5
  %(prog)s 42

This command checks one specification's positive suite serially.
        """
    )
    parser.add_argument(
        'spec_id',
        type=str,
        metavar='SPEC_ID',
        help='Specification identifier, can be a number (e.g., "1") or underscore format (e.g., "1_")'
    )
    parser.add_argument(
        '--max-attempts',
        type=int,
        default=3,
        metavar='N',
        help='Maximum number of attempts per test case (default: 3)'
    )
    parser.add_argument("--count-only", action="store_true", help="Count cases without calling the model")
    args = parser.parse_args()

    tester = CoqTester()
    if args.count_only:
        tester.sat_spec(args.spec_id)
        return 0
    results = tester.test_spec(args.spec_id, args.max_attempts)

    print(f"\n=== Test Results for Spec {args.spec_id} ===")
    passed = 0
    interrupted = any(test_idx == 0 for test_idx, _, _ in results)
    total = sum(test_idx != 0 for test_idx, _, _ in results)

    for test_idx, success, error in results:
        if test_idx == 0:
            print(f"Run interrupted: {error}")
            continue
        status = "PASS" if success else "FAIL"
        print(f"Test case {test_idx}: {status}")
        if not success and error:
            print(f"  Error: {error}")
        if success:
            passed += 1

    suffix = " (interrupted; completed cases only)" if interrupted else ""
    print(f"\n{args.spec_id} Summary: {passed}/{total} test cases passed{suffix}")
    return 0 if results and passed == total and not interrupted else 1

if __name__ == '__main__':
    sys.exit(main())
