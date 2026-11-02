# Phase 6 decision record: frozen hybrid candidate ranker

**Status:** Held-out test completed successfully; frozen results recorded below.  
**Decision ID:** `phase6-frozen-hybrid-v1`  
**Repository:** `yerageracharan/issue-triage-agent`

## Product objective

The main experience is to show a developer a short ranked list of previous issues that may describe the same underlying problem. For this use case, top-three retrieval quality is the primary selection criterion. Pairwise classification quality remains an important secondary measure.

## Evidence used to select the method

The four methods were compared on the validation split. At their training-selected thresholds:

| Method | Pairwise F1 | MRR@3 | Recall@3 |
|---|---:|---:|---:|
| Lexical | 0.680372 | 0.810201 | 0.993311 |
| BM25 | 0.706040 | 0.871237 | 0.996656 |
| Semantic | **0.763701** | 0.915831 | 0.996656 |
| Hybrid | 0.753855 | **0.917781** | **1.000000** |

Semantic is stronger on pairwise F1. Hybrid is slightly stronger on top-three ranking and found a known positive among the first three candidates in all 598 eligible validation groups. Those groups require at least two sampled candidates and one source-positive pair; singleton groups are excluded.

**Decision:** select Hybrid for the Phase 6 test because ranked candidate retrieval is the product's primary job. This does not mean Hybrid is the best method for every possible operating goal.

## Frozen configuration

| Setting | Frozen value |
|---|---|
| Method | Hybrid: 50% BM25 + 50% semantic score |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Maximum embedding sequence length | 256 tokens |
| Score calibration | Training-only z-score followed by logistic mapping |
| Pairwise decision threshold | 0.41291124292046016 |
| Candidate list size | Top 3 |
| Dataset revision | `902b5805afa93e8cb018bd3c860c0f3eba55029e` |
| Dataset fingerprint | `24bb969f9437e210` |
| Training rows | 13,908 |
| Held-out test rows | 2,982 |

The machine-readable source of truth is `evaluation/frozen_hybrid_config.json`.

## Phase 5 human-review limitation

The separate AI-assisted audit examined all 56 examples and recorded preliminary evidence categories. It is not independent human adjudication. The reviewer-facing workbook remains blinded and its decision fields remain empty. No AI audit label is substituted for an original benchmark label, and no human review result is used to choose this Phase 6 configuration.

## Phase 6 procedure

The evaluator:

1. Confirms the dataset revision, fingerprint and seed.
2. Confirms training and test repositories and pair IDs are disjoint.
3. Recomputes the threshold using training data as an integrity check and requires it to match the frozen value.
4. Applies the frozen Hybrid configuration to the held-out test split.
5. Calculates pairwise metrics and top-three retrieval metrics.
6. Evaluates the unchanged production detector on the same test pairs for a like-for-like comparison.
7. Exports the per-pair scores and ranked top-three candidate groups for audit.

The test labels are used only to calculate metrics. They must not be used to select a different threshold or method.

## Guardrails

- Do not adjust the threshold after viewing the test result.
- Do not change the model, preprocessing, weights, score calibration or top-k based on the test result.
- Weak negatives are not confirmed non-duplicates. Their alerts must not be reported as verified false positives.
- If changes are necessary, tune using a new validation dataset and reserve a new untouched test set for the next final evaluation.
- Keep the production agent read-only. It may recommend candidates but must not close issues, apply labels, assign people or post comments.


## Held-out test results

The frozen evaluator completed successfully in [GitHub Actions run 41366209127](https://github.com/yerageracharan/issue-triage-agent/actions/runs/41366209127). The run uploaded artifact `issuedupeslite-benchmark-26` (artifact ID `13107604354`).

- Test size: 2,982 pairs across 150 repositories.
- Training size: 13,908 pairs across 700 repositories.
- Train/test repository overlap: none.
- Recomputed training threshold: `0.41291124292046016`, an exact match to the frozen value.
- Top-three retrieval groups evaluated: 620.

| Metric | Existing detector | Frozen Hybrid |
|---|---:|---:|
| Precision | 87.28% | 65.60% |
| Recall | 10.13% | 85.45% |
| F1 | 18.15% | 74.22% |
| ROC AUC | 64.10% | 78.90% |
| Average precision | 65.66% | 77.65% |
| MRR@3 | 79.76% | 92.15% |
| Recall@3 | 98.87% | 99.68% |

At the frozen threshold, Hybrid recorded 1,274 source-positive alerts, 668 weak-negative alerts, 823 weak negatives not flagged, and 217 source-positive pairs missed. The baseline recorded 151 source-positive alerts, 22 weak-negative alerts, 1,469 weak negatives not flagged, and 1,340 source-positive pairs missed.

For candidate ranking, Hybrid reached MRR@3 **0.921505** and Recall@3 **0.996774**, compared with **0.797581** and **0.988710** for the existing detector. These metrics include only groups with at least two sampled candidates and at least one source-positive pair.

## Decision after the test

The test supports using Hybrid as a **read-only ranked candidate recommender for human review**, subject to further validation. It does not support automatic duplicate confirmation or automatic issue mutation. Precision decreased relative to the existing conservative detector; consequently, candidate suggestions must be clearly labelled as suggestions and supported with evidence for a maintainer to inspect.

Do not tune this frozen configuration using these test results. Any future model/threshold change requires a new validation set and a new untouched test split. Independent human adjudication of the blinded 56-pair review sample remains outstanding.

## Artifact contents and reproducibility caveat

Artifact `issuedupeslite-benchmark-26` includes the test JSON and Markdown report, per-pair scores, top-three candidate CSV, benchmark splits, baseline, validation comparison, and blinded Phase 4 reviewer pack. The model identifier `sentence-transformers/all-MiniLM-L6-v2` was frozen, but its upstream model revision was not explicitly pinned; exact embedding-weight reproducibility is a known limitation.