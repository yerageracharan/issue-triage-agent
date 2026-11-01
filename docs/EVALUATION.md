# Evaluation and verification

## What has been tested

The automated test suite covers:

- Repository identifier parsing and rejection of non-GitHub hosts.
- GitHub issue fetching through mocked HTTP responses.
- Pull-request exclusion from GitHub's issue endpoint results.
- Category selection using labels and wording.
- Provisional priority rules.
- Missing-information checks.
- Duplicate-candidate scoring and threshold behaviour.
- Markdown and JSON report generation.
- CLI execution on a synthetic offline fixture.
- Local-model response parsing and the rule that enrichment cannot override category or priority.
- Shared service output for MCP-compatible structured payloads.
- Importability of the MCP server and default stdio transport when the MCP extra is installed.

Run the suite locally:

```bash
python -m pip install -e ".[test,mcp]"
python -m pytest
```

The CI workflow tests Python 3.10 through 3.13 and installs the MCP extra, so the MCP server module is import-checked as part of the build.

## What has not been established

The tests use synthetic issue data and mocked HTTP responses. They do not establish classification accuracy on a large real-world corpus, calibrated confidence, real-world duplicate precision/recall, or the safety of every possible issue text. There is no independently annotated benchmark in this repository. Do not describe the current rule engine as a high-accuracy AI classifier.

A live MCP client connection should be smoke-tested in the target host after installation. Host behaviour, available features, and account permissions can change independently of this project.

## Example fixture

`examples/sample_issues.json` contains deliberately similar synthetic CSV-export issues. `examples/sample_report.md` and `examples/sample_report.json` show the expected kind of output. The issue titles and URLs are illustrative and must not be mistaken for real GitHub issue evidence.

![Illustrative issue triage report](assets/sample-dashboard.svg)

## Interpreting test results

A passing unit test means that the tested function behaves as expected for the fixture and assertion. It does not prove that the same heuristic is correct for every repository. A high similarity score means that two texts share words or patterns, not that one issue should be closed. A P0 phrase means that a high-impact phrase was detected, not that an incident has been verified.


## Phase 1: IssueDupesLite benchmark preparation

The reproducible preparation workflow lives in the evaluation/benchmark folder. It downloads [Primordic/IssueDupesLite](https://huggingface.co/datasets/primordic/IssueDupesLite), resolves and records the dataset revision, extracts source-labelled positive pairs, samples same-repository weak negatives, and assigns entire repositories—not individual pairs—to train/validation/test splits.

Important evaluation caveats:

- The source card declares CC-BY-SA-4.0. Generated derivatives retain attribution and a share-alike notice in ATTRIBUTION.md.
- The dataset viewer reports 10,000 rows and 992 repository values, while the card prose says "10 issue pairs from 1,000 repositories". The preparation script records actual loaded counts.
- The source warns that some genuine duplicates are not labelled. Generated non-linked pairs are therefore weak/unverified negatives, not verified ground-truth non-duplicates.
- A source primary issue can have a later creation timestamp than its duplicate. The output preserves source roles and separately records chronological historical/incoming issue IDs.
- All rows for one repository stay in one split to reduce repository-level leakage.

Install the optional dependency and run:

~~~powershell
python -m pip install -e '.[benchmark,test]'
python -m evaluation.benchmark.prepare_benchmark --seed 42
~~~

Generated source-derived data is placed in evaluation/benchmark/generated/, which is ignored by Git. This avoids accidentally committing a large copy of third-party issue text. The generated manifest records the source revision, dataset fingerprint, preparation settings, counts, and split distribution.

This is a data-preparation milestone only. No duplicate-detection algorithm has been changed and no real-world precision/recall result is claimed until the prepared benchmark has been generated, checked, and evaluated.


## GitHub Actions benchmark artifact

The workflow at .github/workflows/benchmark-data.yml downloads IssueDupesLite on a GitHub-hosted runner, runs the benchmark preparation unit tests, generates the dataset, validates repository isolation and pair uniqueness, and uploads the generated benchmark directory as an Actions artifact with a 30-day retention period.

The artifact is not committed to the source repository. This is intentional because it contains third-party issue text from the CC-BY-SA-4.0 source dataset. Keep ATTRIBUTION.md with any derived benchmark data you download.


## Phase 2: current duplicate detector baseline

A reproducible evaluator now measures the existing duplicate scorer without changing it. It reuses `analyse_issue` to obtain the categories that the production scorer expects, then calls the production `similarity_score` function for each prepared issue pair. The current `0.48` candidate threshold is retained.

Run the evaluator after preparing the benchmark:

~~~powershell
python -m evaluation.benchmark.evaluate_baseline --test-csv evaluation/benchmark/generated/test.csv --manifest evaluation/benchmark/generated/manifest.json --output-dir evaluation/benchmark/generated/baseline
~~~

Outputs are `baseline_metrics.json`, `baseline_scores.csv`, and `baseline_report.md`. The Actions workflow runs this evaluator on the held-out test split and includes the files in the generated benchmark artifact.

### Initial result

Using IssueDupesLite revision `902b5805afa93e8cb018bd3c860c0f3eba55029e`, the test split contained 2,982 pairs from 150 repositories, balanced between 1,491 source-annotated duplicate pairs and 1,491 weak/unverified negatives. At threshold 0.48, the unchanged detector produced:

- Accuracy: 54.33%
- Precision: 87.28%
- Recall: 10.13%
- F1: 18.15%
- Specificity: 98.52%
- ROC AUC: 64.10%
- Average precision: 65.66%

The confusion counts were 151 true-positive labels flagged, 22 weak-negative labels flagged, 1,469 weak-negative labels not flagged, and 1,340 source-positive labels missed.

Interpretation: among the pairs flagged by the current threshold, 87.28% carried a positive source label. However, only 10.13% of source-labelled positives crossed the threshold. This is a high-precision / low-recall operating point on this particular pair benchmark.

The negative labels are unverified and may contain undiscovered duplicates. Therefore, a pair counted as a false positive may be a missed source annotation rather than a genuine detector mistake. The numbers measure agreement with the dataset labels, not proven real-world accuracy. The score is pairwise and does not establish top-three retrieval quality in a live repository scan.

The test split must remain untouched for later final comparisons. Threshold tuning and algorithm experiments should use the validation split. No detector logic was changed in this baseline step.


## Phase 3: compare similarity methods (validation only)

The Phase 3 experiment compares the existing lexical scorer, a repository-specific BM25 index, local semantic embeddings, and an equal-weight BM25/semantic hybrid. It uses the training split for score scaling and threshold selection, then reports the frozen settings on validation. The held-out test split is not used for Phase 3 tuning.

Run the comparison after preparing the benchmark:

~~~powershell
python -m pip install -e '.[benchmark,test,similarity-experiments]'
python -m evaluation.benchmark.evaluate_similarity_methods --train-csv evaluation/benchmark/generated/train.csv --validation-csv evaluation/benchmark/generated/validation.csv --model sentence-transformers/all-MiniLM-L6-v2 --output-dir evaluation/benchmark/generated/phase3
~~~

The optional dependency group keeps the standard Issue Triage Agent installation lightweight. The embedding model runs locally; no paid API key is required.

### Early local comparison: lexical versus BM25

On 13,908 training pairs and 2,984 validation pairs, a local run comparing the existing lexical scorer and BM25 produced:

| Validation metric | Lexical | BM25 |
|---|---:|---:|
| ROC AUC | 0.6541 | 0.7031 |
| Average precision | 0.6419 | 0.6780 |
| F1 at training-selected threshold | 0.6804 | 0.7060 |
| MRR@3 | 0.8102 | 0.8712 |
| Recall@3 | 0.9933 | 0.9967 |

For top-three retrieval, 598 qualifying incoming-issue query groups were evaluated; groups with fewer than two sampled candidates or no source-positive candidate were excluded. BM25 performed better than the lexical scorer on these validation measures. This is an early comparison, not a final test-set result or proof of real-world accuracy.

The semantic embedding and hybrid methods are implemented but their full CPU run is still pending in GitHub Actions run [41356083341](https://github.com/yerageracharan/issue-triage-agent/actions/runs/41356083341). Do not treat them as evaluated until the workflow saves the comparison artifact. The final test split remains untouched.

As in Phases 1 and 2, positive labels are source-annotated and negative labels are weak/unverified unlinked candidates. Some negatives may be undiscovered duplicates. Validation metrics measure agreement with these dataset labels, not independently confirmed truth.
