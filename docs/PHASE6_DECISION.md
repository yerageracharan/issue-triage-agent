# Phase 6 decision record: frozen hybrid candidate ranker

**Status:** Configuration frozen; held-out test execution is in progress.  
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
