# Phase 1 benchmark: IssueDupesLite

This folder contains the reproducible data-preparation workflow for evaluating the current duplicate-candidate detector. It does not change the detector itself.

## Source dataset

[Primordic / IssueDupesLite](https://huggingface.co/datasets/primordic/IssueDupesLite)

The dataset contains pairs of GitHub issues from the same repository. Each source row records a primary issue and an issue identified as its duplicate. The available fields include repository, issue numbers, titles, bodies, creation timestamps, duplicate-closing comment, and comment timestamp.

The Hugging Face viewer currently reports 10,000 rows and 992 distinct repository values. The dataset-card prose says "10 issue pairs from 1,000 repositories", which conflicts with the viewer's 10K-row count. The preparation script records actual downloaded counts rather than hardcoding either number.

The declared dataset licence is CC-BY-SA-4.0. See the generated ATTRIBUTION.md for attribution and the share-alike note.

## Windows setup

Run these commands from the root of the issue-triage-agent repository:

~~~powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[benchmark,test]'
~~~

The base agent does not need the datasets dependency. It is installed only for this benchmark preparation step.

## Download and prepare

~~~powershell
python -m evaluation.benchmark.prepare_benchmark --output-dir evaluation/benchmark/generated --seed 42 --negative-ratio 1.0 --hard-negative-fraction 0.5 --train-ratio 0.70 --validation-ratio 0.15 --test-ratio 0.15
~~~

The script resolves the Hub branch to a commit SHA, downloads the train split at that immutable revision, and records the revision and dataset fingerprint in manifest.json.

To pin a particular Hub revision later, pass --revision followed by a commit SHA. Re-running with the same source revision and settings produces deterministic pair selections and repository assignments.

The first download requires an internet connection. The downloaded dataset is cached under evaluation/benchmark/.cache by default.

## Files produced

The generated directory is ignored by Git because it contains third-party issue text and derived benchmark data. It is created locally when the preparation command runs.

| File | Contents |
|---|---|
| positive_pairs.csv | Deduplicated source-labelled duplicate pairs (pair_label=1). |
| negative_pairs.csv | Sampled same-repository unlinked pairs (pair_label=0, weak/unverified). |
| repository_splits.csv | One train/validation/test assignment per repository. |
| train.csv | Training positives and sampled negatives. |
| validation.csv | Validation positives and sampled negatives. |
| test.csv | Held-out positives and sampled negatives. |
| manifest.json | Source revision, settings, counts, split distribution, and caveats. |
| ATTRIBUTION.md | Source attribution and data-licence note. |

All three split files use the same columns. They include both issue texts, source pair roles, pair label, negative sampling type, a lexical-overlap hint, and chronological issue ordering where timestamps allow it.

## How positive pairs are defined

A positive is a pair present in IssueDupesLite. The source's primary/duplicate roles are preserved in separate columns. For pair IDs and issue text columns, the two issue records are placed in ascending issue-number order to make deduplication stable.

Duplicate rows for the same repository/issue-number pair are collapsed, with the number of source rows recorded. The most informative text version of an issue is retained for negative candidate generation.

## How negative pairs are sampled

The source only provides labelled duplicate pairs. It does not provide a verified exhaustive list of non-duplicate pairs.

The script therefore creates weak negatives as follows:

1. Collect the unique issue records appearing in the dataset.
2. Restrict candidate pairs to issues from the same repository.
3. Build connected components from all known positive edges.
4. Exclude candidates within the same connected component. For example, if A-B and A-C are known positives, B-C is not sampled as a negative.
5. Sample a target number of remaining candidates per repository.
6. Reserve a configurable fraction for hard_lexical candidates with greater title/body word overlap; fill the remainder with seeded random same-repository candidates.

Every sampled negative is marked weak_unlinked_candidate_not_human_verified. It is not a claim that a maintainer confirmed the two reports describe different defects. Some may be undiscovered duplicates because the source card explicitly warns that not every true duplicate was labelled.

The default is one weak negative per positive, with half of the target reserved for lexical hard negatives. Change this with --negative-ratio and --hard-negative-fraction.

## Repository-level split design

Repository names—not rows—are assigned to train, validation, or test. All positive and negative examples from one repository stay in the same split. This reduces leakage from project-specific terminology, issue templates, and repeated product names.

The default targets are 70% / 15% / 15% by positive-pair count. Because repositories are indivisible groups, final counts may not match those percentages exactly. The actual numbers are written to manifest.json.

With fewer than three repositories in a fixture, one or more splits can be empty. The preparation script reports actual counts rather than assuming every split is populated.

## Chronology and the primary/duplicate caveat

The source card explicitly warns that the selected primary issue can sometimes have a later creation date than the issue labelled duplicate. Therefore:

- Source primary and duplicate roles are kept exactly as supplied.
- historical_issue_number is calculated from the earlier creation timestamp.
- incoming_issue_number is calculated from the later creation timestamp.
- chronology_status is ordered, same_timestamp_order_unknown, or missing_or_invalid_date.

For a chronological replay, query with the later-created issue and only expose earlier-created issue candidates. Do not assume that source primary_issue_num is always the earlier issue.

## What this benchmark can and cannot prove

The positive pairs are source-annotated, not independently re-labelled by this project. The generated negatives are weak/unverified. This dataset can provide a useful first retrieval benchmark, but it is not a perfectly clean gold-standard classification dataset.

Before publishing definitive precision/recall claims, manually audit a sample of negative pairs (especially hard negatives) and record adjudicated labels separately. Keep the original label_quality field so future metrics can exclude uncertain examples or report them separately.

This Phase 1 step intentionally does not change src/issue_triage_agent/similarity.py. First create and inspect the benchmark. Algorithm experiments belong in the next phase.

## Test the preparation logic without downloading Hugging Face data

~~~powershell
python -m pytest tests/test_benchmark.py
~~~

The tests use tiny synthetic fixtures and verify deterministic sampling, transitive duplicate exclusion, repository-level split isolation, chronology handling, and output files. They do not pretend to validate the real-world detector.


## Run the download and preparation on GitHub

You do not need to upload the original dataset yourself. The repository includes a GitHub Actions workflow that downloads the public Hugging Face dataset directly on a GitHub-hosted runner, prepares the files, validates the outputs, and uploads a downloadable artifact.

1. Open the [Issue Triage Agent Actions tab](https://github.com/yerageracharan/issue-triage-agent/actions).
2. Select **Prepare duplicate-detection benchmark** in the workflow list.
3. Click **Run workflow**.
4. For the first run, keep seed 42, negative ratio 1.0, and hard-negative fraction 0.5.
5. Open the run after it finishes.
6. In the Artifacts section near the bottom of the run page, download the artifact whose name begins with issuedupeslite-benchmark.
7. Unzip it. It contains positive_pairs.csv, negative_pairs.csv, repository_splits.csv, train.csv, validation.csv, test.csv, manifest.json, and ATTRIBUTION.md.

The workflow runs the benchmark preparation unit tests first. After downloading and preparing the dataset, it validates that every repository belongs to only one split, no pair ID occurs in multiple splits, weak negatives carry their warning label, and the split totals match the manifest.

The artifact is retained for 30 days. It is deliberately not committed to the Git repository: these files contain third-party GitHub issue text derived from IssueDupesLite, whose declared licence is CC-BY-SA-4.0. Keep the generated ATTRIBUTION.md alongside the files when you use or redistribute the derived benchmark.

You can also download the original dataset yourself from [Hugging Face — IssueDupesLite](https://huggingface.co/datasets/primordic/IssueDupesLite). The GitHub Actions route is easier because it performs the same preparation and validation automatically.
