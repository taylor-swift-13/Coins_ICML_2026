#!/usr/bin/env python3
"""
Batch script to run equiv_proof_gen.py
Uses matching specification filenames in equiv/input.
"""
import subprocess
import sys
import os
import re

def run_equiv_proof(spec_id: str, model_name: str = None, max_attempts: int = 3):
    """Run equiv_proof_gen.py for a single spec_id (using equiv directory)"""
    script_path = os.path.join(os.path.dirname(__file__), "equiv_proof_gen.py")

    cmd = [sys.executable, script_path, "--spec", spec_id]

    if model_name:
        cmd.extend(["--model", model_name])

    if max_attempts != 3:
        cmd.extend(["--max-attempts", str(max_attempts)])

    print(f"\n{'='*60}")
    print(f"Processing spec_id: {spec_id}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, capture_output=False)

    if result.returncode == 0:
        print(f"✓ {spec_id} processing complete")
        return 0
    else:
        print(f"✗ {spec_id} processing failed")
        return 1 if result.returncode == 1 else 2


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Batch run equiv_proof_gen.py',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--model',
        type=str,
        default=None,
        metavar='MODEL_NAME',
        help='Model name (if not specified, uses default from equiv_proof_gen.py)'
    )
    parser.add_argument(
        '--max-attempts',
        type=int,
        default=3,
        metavar='N',
        help='Maximum number of attempts per direction (default: 3)'
    )
    parser.add_argument(
        '--include-underscore',
        action='store_true',
        help='Include underscore versions (e.g., 137_, 160_)'
    )

    args = parser.parse_args()
    if args.max_attempts < 1:
        parser.error("max-attempts must be positive")

    # Hardcoded to use equiv directory, only process if files exist in both directories
    equiv_human_dir = os.path.join(os.path.dirname(__file__), "..", "equiv", "input", "human")
    equiv_llm_dir = os.path.join(os.path.dirname(__file__), "..", "equiv", "input", "llm")

    human_specs = set()
    llm_specs = set()

    if os.path.exists(equiv_human_dir):
        for f in os.listdir(equiv_human_dir):
            if f.endswith('.v'):
                spec_id = f[:-2]
                human_specs.add(spec_id)

    if os.path.exists(equiv_llm_dir):
        for f in os.listdir(equiv_llm_dir):
            if f.endswith('.v'):
                spec_id = f[:-2]
                llm_specs.add(spec_id)

    # Only process if files exist in both directories
    common = {sid for sid in human_specs & llm_specs
              if re.fullmatch(r'\d+_?', sid)
              and (args.include_underscore or not sid.endswith('_'))}
    spec_ids = sorted(common, key=lambda sid: (int(sid.rstrip('_')), sid))
    print(f"Using equiv directory mode")
    print(f"human directory file count: {len(human_specs)}")
    print(f"llm directory file count: {len(llm_specs)}")
    print(f"Common files count: {len(spec_ids)}")

    print(f"Starting batch processing of {len(spec_ids)} spec_ids...")
    print(f"Model: {args.model if args.model else 'default'}")
    print(f"Max attempts: {args.max_attempts}")

    if not spec_ids:
        return 2
    success_count = 0
    fail_count = 0
    error_count = 0

    for spec_id in spec_ids:
        success = run_equiv_proof(spec_id, args.model, args.max_attempts)
        if success == 0:
            success_count += 1
        elif success == 1:
            fail_count += 1
        else:
            error_count += 1

    print(f"\n{'='*60}")
    print(f"Batch processing complete!")
    print(f"{'='*60}")
    print(f"Total: {len(spec_ids)}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Errors: {error_count}")

    return 2 if error_count else (0 if fail_count == 0 else 1)


if __name__ == '__main__':
    sys.exit(main())
