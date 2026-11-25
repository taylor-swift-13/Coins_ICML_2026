
<h1 align="center">How Powerful are LLMs in Generating Formal Program Specifications?</h1>

<p align="center">
A Coq-based formal verification framework for evaluating LLM-generated program specifications.
</p>

<p align="center">
<a href="https://icml.cc/virtual/2026/poster/66406"><img src="https://img.shields.io/badge/Conference-ICML%202026-A42E25" alt="Conference"></a>
<a href="paper/main.pdf"><img src="https://img.shields.io/badge/Paper-PDF-blue" alt="Paper"></a>
<a><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python"></a>
<a><img src="https://img.shields.io/badge/Verified%20with-Coq-8A2BE2" alt="Coq"></a>
</p>

<p align="center">
<a href="paper/images/flow.pdf"><img src="paper/images/flow.png" alt="COINS evaluation framework"></a>
</p>

COINS is a Coq-based formal verification framework for evaluating HumanEval code specifications. It uses LLMs to automatically generate Coq proofs and verify the correctness and robustness of specifications.

## Setup

Run the commands below in **Bash on Linux or WSL**, from the repository root (the directory containing `src/` and `HumanEvalPlus.jsonl`).

The command workflows are tested with Python **3.10.12**, OpenAI Python SDK **2.50.0**, and Coq **8.20.1**. Use Python 3.10+ and ensure `coqtop` is on `PATH` in the same shell as Python.

```bash
python3 --version
coqtop --version
python3 -m pip install -r requirements.txt
```

Only generation commands require an OpenAI-compatible API. Set your own endpoint and key; the endpoint must serve the model identifiers you select and accept their configured temperature.

```bash
export COINS_API_KEY="your-api-key"
export COINS_BASE_URL="https://your-api-url/v1"
```

Edit these two values in `src/config.py` before running the examples:

```python
TYPE = "human"
MODEL_NAME = "gemini-3-pro-preview"
```

`TYPE` selects the input group; it does not select a proof model. The example configuration evaluates human-written specifications with Gemini. To evaluate GPT-5 specifications using Gemini, set `TYPE = "gpt-5"` and keep `MODEL_NAME` unchanged.

| Command | Specification inputs | Model setting |
|---|---|---|
| `proof_gen.py`, `batch_proof_gen.py` | `spec/<TYPE>/input/` | `MODEL_NAME`, or `--model` |
| `tester.py` | Saved first proof under `spec/<TYPE>/output/<MODEL_NAME>/` | `MODEL_NAME` |
| `negative_proof.py`, `negative_batch_proof.py` | `negative/input/<TYPE>/` | `LLM_MODEL` in each negative script; defaults to `gemini-3-pro-preview` |
| `equiv_proof_gen.py`, `equiv_proof_batch.py` | Matching filenames in `equiv/input/human/` and `equiv/input/llm/` | `MODEL_NAME`, or `--model` |
| `spec_gen.py` | `HumanEvalPlus.jsonl`, or `--dataset` | Required `--model` |

When changing the negative-test prover, update `LLM_MODEL` in **both** negative scripts. When using `--model` for a first proof, set `MODEL_NAME` to that same value before running `tester.py`, so it reads the correct output directory.

Specification generation uses temperature **0**; proof generation uses **0.7**. Positive and implication proofs allow three attempts by default; negative testing makes one model request per uncached case. Coq verification times out after 30 seconds for positive/negative cases and 60 seconds for implications. The API request timeout is 300 seconds.

## Input data and identifiers

The repository includes specification inputs and positive/negative test-case data. Generated proofs, filtered results, failed attempts and logs are local outputs ignored by Git; they are created by the commands below.

Task IDs are **0–163**. A filename such as `1_.v` is an alternative specification for task 1; use it only when that file exists in the selected input group. Positive batch commands scan both numbered and underscore variants in the requested inclusive range, so a range can select more files than task IDs.

Negative testing and implication checking use their own prepared input directories. They do not automatically select or copy specifications from a positive run. To evaluate a newly generated specification through these stages, prepare the corresponding inputs after reviewing its positive results.

## Positive evaluation

With the example configuration above, generate the first-case proof, check it, then evaluate all remaining cases:

```bash
python3 src/proof_gen.py 1
python3 src/verify.py --file spec/human/output/gemini-3-pro-preview/1.v
python3 src/tester.py 1
```

Proceed to `tester.py` only after the first proof succeeds. It verifies the saved first proof and uses that proof as a reference for each subsequent case. By default, it stops at the first failed case (`SKIP_ON_FIRST_FAIL` in `src/config.py`). A model can fail to prove a case; a nonzero result is a reported evaluation outcome, not a guarantee that the specification is incorrect.

The alternative specification is a separate run:

```bash
python3 src/proof_gen.py 1_ --max-attempts 5
python3 src/tester.py 1_ --max-attempts 5
```

To save an additional copy of a successful first proof, choose an output filename that does not already exist:

```bash
python3 src/proof_gen.py 42 --output proof-42.v
```

Batch generation runs **first-case proofs only**. This example uses two workers and includes both endpoints:

```bash
python3 src/batch_proof_gen.py --range 1:2 --num-workers 2 --max-attempts 3
python3 src/verify.py --batch --directory spec/human/output/gemini-3-pro-preview --range 1:2
```

The standalone batch verifier checks numbered files (`1.v`, `2.v`); verify underscore variants with `--file`. Missing requested files count as failures. Neither batch command runs the full positive suite or creates a `pass_all` directory automatically.

## Specification generation

These two examples use separate local output directories, avoiding collisions with the specifications already supplied in the repository:

```bash
python3 src/spec_gen.py --model gpt-4o --spec 0 --output-dir runs/spec-with-code
python3 src/spec_gen.py --model gpt-4o --spec 0 --without-reference-impl --output-dir runs/spec-without-code
```

Each writes `0.v` in its chosen directory. Repeating a command requires a fresh output directory or an explicit `--overwrite`. Without `--output-dir`, the destination is `spec/<model>/input/`; `--type GROUP` changes that group. To evaluate newly generated specifications with the positive commands, place them in `spec/<TYPE>/input/` and select that `TYPE` in `src/config.py`.

## Negative evaluation

With `TYPE = "human"`, these commands use the supplied `negative/input/human/` specifications:

```bash
python3 src/negative_proof.py --spec-id 42
python3 src/negative_batch_proof.py --range 1:2 --num-workers 2
```

Each case asks for an accepting proof. The model can instead return exactly `Test case is not accepted`, in which case the proof is skipped and the response is saved as `.txt`.

- `GOOD` / exit 0: no accepting proof was found for any case. This does not establish formal rejection or robustness.
- `BAD` / exit 1: an accepting proof was found for at least one negative case.
- Error / exit 2: no conclusive result is available because of a configuration, API or verifier failure. A previously saved accepting proof still establishes `BAD` if a later case fails to run.

Case responses are saved under `negative/output/<TYPE>/good/` or `bad/`. Specifications that pass the negative filter are copied to `negative/fail_all/<TYPE>/`. This is the negative-stage result; identifying final COINS candidates also requires checking the positive-stage result.

## Implication checking

Task 122 has both supplied input files, `equiv/input/human/122.v` and `equiv/input/llm/122.v`:

```bash
python3 src/equiv_proof_gen.py --spec 122 --model gemini-3-pro-preview
```

The two directions are attempted independently. Successful proofs are saved to `equiv/output/122_l.v` (human implies LLM) and `122_r.v` (LLM implies human). Both directions must succeed for equivalence.

To process all matching pairs:

```bash
python3 src/equiv_proof_gen.py --all --model gemini-3-pro-preview
python3 src/equiv_proof_batch.py --model gemini-3-pro-preview
```

These are alternative batch entry points. `--all` includes all matching variants; the batch wrapper includes underscore variants only with `--include-underscore`. Implication output paths do not include the model name, so use a separate checkout for comparisons across provers.

## Offline inspection

These commands require no API credentials. Coq is needed for compilation.

```bash
python3 src/tester.py 1 --count-only
python3 src/verify.py --file spec/human/input/1.v
python3 src/extract_pairs.py -i 0 -p HumanEvalPlus.jsonl
python3 src/extract_pairs.py -i 1 --one-based
python3 src/extract_pairs.py -i 0 --mode results
```

`--one-based -i 1` refers to task 0. Without `--one-based`, indices are zero-based.

## Local results and reruns

Existing proof files are checked and reused rather than overwritten. Existing negative responses are also reused. Failed proof attempts and logs remain local. `proof_gen.py --output` requires a new destination filename.

For a fresh run after changing specifications, prompts or the prover, use a separate checkout with the same inputs and configuration. Reuse checks compile the saved file; they do not bind it to a changed input specification. Likewise, successful compilation alone does not establish that the generated theorem faithfully represents the supplied specification and test case.

## Project layout

| Path | Contents |
|---|---|
| `src/` | Generation, testing, verification and logging scripts |
| `HumanEvalPlus.jsonl` | Positive test-case inputs and reference outputs |
| `spec/<group>/input/` | Human-written or model-generated input specifications |
| `spec/<group>/output/<prover>/` | Local first-case proofs |
| `spec/<group>/test/<prover>/<id>/` | Local proofs for subsequent positive cases |
| `spec/<group>/bad/<prover>/` | Local failed proof attempts |
| `negative/input/<group>/` | Prepared negative-stage specification inputs |
| `negative/negative_cases.jsonl` | Negative input/output cases |
| `negative/output/<group>/` | Local negative-stage responses |
| `negative/fail_all/<group>/` | Local specifications passing the negative filter |
| `equiv/input/human/`, `equiv/input/llm/` | Prepared specification pairs |
| `equiv/output/` | Local implication proofs |
| `log/` | Local per-case run logs |
| `runs/` | Optional local output directory used in the examples |
| `paper/` | LaTeX source, figures, build instructions and [paper PDF](paper/main.pdf) |

All scripts provide `--help`. The paper build instructions are in [`paper/README.md`](paper/README.md).

## Citation

If you use COINS in your research, please cite our paper on [OpenReview](https://openreview.net/forum?id=41zGzIEpQd):

```bibtex
@inproceedings{yang2026how,
  title = {How Powerful are {LLM}s in Generating Formal Program Specifications?},
  author = {Fanpeng Yang and Xing Li and Shuling Wang and Jie An and Zeyu Sun and Shenghua Feng and Wenhan Wang and Weiyi Wang and Naijun Zhan and Fanjiang Xu},
  booktitle = {The Forty-third International Conference on Machine Learning},
  year = {2026},
  url = {https://openreview.net/forum?id=41zGzIEpQd}
}
```
