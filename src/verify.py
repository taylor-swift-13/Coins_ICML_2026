#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
import subprocess
import re
from typing import Tuple


class VerificationError(RuntimeError):
    """The verifier could not run; no proof outcome is available."""


def verify_coq_content(content: str, timeout_seconds: int = 30, strict_errors: bool = False) -> Tuple[bool, str]:
    """Verify if the given Coq source code content can be successfully processed by coqtop."""
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(content)
            temp_file.flush()
            temp_path = temp_file.name
        result = subprocess.run(
            ['coqtop', '-batch', '-l', temp_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        diagnostics = (result.stderr or "") + (result.stdout or "")
        if strict_errors and (result.returncode not in (0, 1) or
                              (result.returncode and not diagnostics.strip()) or
                              re.search(r'Anomaly|Out of memory|Stack overflow|Segmentation fault', diagnostics, re.I)):
            raise VerificationError('Coq failed to complete verification: ' + diagnostics)
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or "") + (result.stdout or "")
    except VerificationError:
        raise
    except subprocess.TimeoutExpired as exc:
        if strict_errors:
            raise VerificationError('Coq verification timed out') from exc
        return False, "Coq verification timed out"
    except Exception as e:
        if strict_errors:
            raise VerificationError(f'Cannot run Coq: {e}') from e
        return False, f"Error during verification: {e}"
    finally:
        if temp_path is not None and os.path.exists(temp_path):
            os.unlink(temp_path)


def verify_coq_file(path: str, timeout_seconds: int = 30) -> Tuple[bool, str]:
    """Verify if the given .v file can be successfully processed by coqtop."""
    if not os.path.exists(path):
        return False, f"File not found: {path}"
    try:
        result = subprocess.run(
            ['coqtop', '-batch', '-l', path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or "") + (result.stdout or "")
    except subprocess.TimeoutExpired:
        return False, "Coq verification timed out"
    except Exception as e:
        return False, f"Error during verification: {e}"


def batch_verify(directory: str, start_n: int, end_m: int, timeout_seconds: int = 30) -> Tuple[float, list]:
    """
    Batch verify .v files from n to m in the directory, return correctness rate and detailed results.

    Args:
        directory: Directory path containing .v files
        start_n: Starting file number
        end_m: Ending file number (inclusive)
        timeout_seconds: Timeout for each file

    Returns:
        (correct_rate, results): Correctness rate (0.0-1.0) and detailed results list
    """
    if start_n < 0 or end_m < start_n:
        raise ValueError("Range must satisfy 0 <= START <= END")
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    results = []
    total_files = end_m - start_n + 1
    successful_files = 0

    for i in range(start_n, end_m + 1):
        file_path = os.path.join(directory, f"{i}.v")

        if os.path.exists(file_path):
            is_valid, error_msg = verify_coq_file(file_path, timeout_seconds)

            result = {
                'file': f"{i}.v",
                'path': file_path,
                'valid': is_valid,
                'error': error_msg if not is_valid else ""
            }
            results.append(result)

            if is_valid:
                successful_files += 1
                print(f"✓ {i}.v - Verification successful")
            else:
                print(f"✗ {i}.v - Verification failed: {error_msg[:100]}...")
        else:
            print(f"? {i}.v - File not found")
            results.append({
                'file': f"{i}.v",
                'path': file_path,
                'valid': False,
                'error': "File not found"
            })

    correct_rate = successful_files / total_files if total_files > 0 else 0.0

    print(f"\n=== Batch Verification Results ===")
    print(f"Total files: {total_files}")
    print(f"Successful verifications: {successful_files}")
    print(f"Failed verifications: {total_files - successful_files}")
    print(f"Correctness rate: {correct_rate:.2%}")

    return correct_rate, results


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Verify Coq proofs using coqtop',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file proof.v
  echo "Definition x := 1." | %(prog)s --stdin
  %(prog)s --batch --directory ./spec/llm/input/gemini-3-pro-preview --range 1:10
        """
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--file', '-f',
        metavar='FILE',
        help='Path to the .v file to verify'
    )
    group.add_argument(
        '--batch',
        action='store_true',
        help='Batch verify files from n to m in the directory'
    )
    group.add_argument('--stdin', action='store_true', help='Read Coq source from standard input')
    parser.add_argument(
        '--directory', '-d',
        metavar='DIR',
        help='Directory containing .v files (required for batch mode)'
    )
    parser.add_argument(
        '--range',
        type=str,
        metavar='START:END',
        help='File number range, format: START:END (START and END are inclusive, required for batch mode)'
    )
    args = parser.parse_args()

    if args.batch:
        if not args.directory or not args.range:
            parser.error("--batch requires --directory and --range arguments")

        try:
            # Parse range parameter
            start, end = map(int, args.range.split(':'))
            correct_rate, results = batch_verify(args.directory, start, end)
            if correct_rate == 1.0:
                print('ALL_OK')
                sys.exit(0)
            else:
                print('SOME_FAIL')
                sys.exit(1)
        except ValueError as e:
            print(f'Error: invalid --range (expected START:END, 0 <= START <= END): {e}', file=sys.stderr)
            sys.exit(2)
        except Exception as e:
            print(f'BATCH_ERROR: {e}', file=sys.stderr)
            sys.exit(1)
    elif args.file or args.stdin:
        ok, err = verify_coq_file(args.file) if args.file else verify_coq_content(sys.stdin.read())
        if ok:
            print('OK')
            sys.exit(0)
        else:
            print('FAIL')
            if err:
                print(err)
            sys.exit(1)

    else:
        print('FAIL')
        sys.exit(1)


if __name__ == '__main__':
    main()
