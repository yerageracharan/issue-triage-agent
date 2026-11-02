# Issue Triage Agent: Benchmark Engineering Walkthrough

**From the original duplicate detector to the frozen 1,000-repository benchmark**  
**Project:** `yerageracharan/issue-triage-agent`  
**Prepared:** 2 November 2026  
**Coverage:** Benchmark Phases 1-6  
**Source dataset:** [Primordic / IssueDupesLite](https://huggingface.co/datasets/primordic/IssueDupesLite)

> This walkthrough records how the original duplicate-candidate detector was measured, how the benchmark was prepared from 10,000 issue-pair rows spanning 1,000 repositories, how four methods were compared without test leakage, how uncertain examples were prepared for review, and how the final Hybrid configuration was frozen and evaluated.
>
> **Scope clarification:** this was a benchmark built from dataset records covering 1,000 repositories. It was **not** a live crawl of 1,000 repositories through the GitHub API. The final held-out test split contains 150 repositories. The existing production detector was measured as-is; Hybrid was an experimental candidate ranker.

---

## Contents

1. [Executive summary](#1-executive-summary)
2. [Starting point: the Issue Triage Agent](#2-starting-point-the-issue-triage-agent)
3. [Why a benchmark was necessary](#3-why-a-benchmark-was-necessary)
4. [Phase 1: obtain and pin the dataset](#4-phase-1-obtain-and-pin-the-dataset)
5. [Phase 1: clean records and construct pairs](#5-phase-1-clean-records-and-construct-pairs)
6. [Phase 1: build weak negatives](#6-phase-1-build-weak-negatives)
7. [Phase 1: prevent repository leakage](#7-phase-1-prevent-repository-leakage)
8. [Phase 2: measure the unchanged baseline](#8-phase-2-measure-the-unchanged-baseline)
9. [Phase 3: compare four similarity methods](#9-phase-3-compare-four-similarity-methods)
10. [Phase 4: analyse errors and create blind review files](#10-phase-4-analyse-errors-and-create-blind-review-files)
11. [Phase 5: AI-assisted source evidence audit](#11-phase-5-ai-assisted-source-evidence-audit)
12. [Phase 6: freeze the Hybrid decision](#12-phase-6-freeze-the-hybrid-decision)
13. [Phase 6: final held-out test results](#13-phase-6-final-held-out-test-results)
14. [End-to-end GitHub Actions workflow](#14-end-to-end-github-actions-workflow)
15. [What changed in the repository](#15-what-changed-in-the-repository)
16. [How to reproduce the work](#16-how-to-reproduce-the-work)
17. [How to interpret the metrics](#17-how-to-interpret-the-metrics)
18. [Limitations and reproducibility risks](#18-limitations-and-reproducibility-risks)
19. [What the benchmark proves - and does not prove](#19-what-the-benchmark-proves---and-does-not-prove)
20. [Next engineering steps](#20-next-engineering-steps)
21. [Key files, run records and references](#21-key-files-run-records-and-references)

---

## 1. Executive summary

The project began with a read-only GitHub issue triage tool. It could inspect issue text, suggest a category and priority, identify missing information, and find possible duplicates using an existing lexical/rule-based similarity function. The open question was whether that duplicate detector could find enough of the known duplicates, and whether a different method could place better candidates near the top of a short suggestion list.

The work followed a controlled experiment:

1. Retrieve a public duplicate-issue dataset and pin the exact dataset revision.
2. Normalize issue records, retain source-linked positive pairs, and create a balanced set of weak negative candidates.
3. Split by repository, not by individual pair, to prevent the same repository appearing across training, validation and test.
4. Measure the existing detector without changing its scoring logic.
5. Compare Lexical, BM25, Semantic and Hybrid methods using training and validation data.
6. inspect model disagreements, make a reviewer-blind file, and separately perform an AI-assisted evidence audit.
7. Freeze the method, calibration, threshold and top-three ranking rule before the held-out test evaluation.
8. Evaluate the frozen method once and compare it with the existing detector on the exact same test pairs.

### Final benchmark result

| Metric | Existing detector | Frozen Hybrid |
|---|---:|---:|
| Precision | 87.28% | 65.60% |
| Recall | 10.13% | 85.45% |
| F1 | 18.15% | 74.22% |
| ROC AUC | 64.10% | 78.90% |
| Average precision | 65.66% | 77.65% |
| MRR@3 | 79.76% | 92.15% |
| Recall@3 | 98.87% | 99.68% |

Hybrid found far more source-labelled duplicate pairs and ranked known duplicates better in the first three candidate positions. Precision decreased, meaning more unlinked examples were also flagged. Since the negative pairs are weak labels rather than independently verified non-duplicates, those alerts cannot all be called confirmed false positives.

**Engineering conclusion:** Hybrid is a stronger benchmark candidate ranker and is suitable for a read-only suggestion prototype with human confirmation. It is not a basis for automatically declaring issues duplicates or changing repository state.

### Dataset at a glance

| Item | Prepared value |
|---|---:|
| Source issue-pair rows loaded | 10,000 |
| Repositories represented in manifest | 1,000 |
| Unique source-annotated positive pairs | 9,937 |
| Newly sampled weak negative pairs | 9,937 |
| Total prepared pairs | 19,874 |
| Training | 13,908 pairs / 700 repositories |
| Validation | 2,984 pairs / 150 repositories |
| Held-out test | 2,982 pairs / 150 repositories |
| Random seed | 42 |
| Repository overlap between splits | 0 |

---

## 2. Starting point: the Issue Triage Agent

The benchmark did not start by replacing the application with a new AI model. It started with the existing Issue Triage Agent and its current duplicate-candidate logic.

The application is designed to be **read-only**. Its existing analysis can provide:
- a provisional category such as bug, feature request, documentation issue or question;
- a provisional P0-P3 priority hint and an explanation;
- missing information that would help reproduce or investigate a report;
- possible duplicate candidates based on issue content and similarity.

The original duplicate scoring path uses:
- `issue_triage_agent.analyzer.analyse_issue(...)` to analyse an issue and create the fields used by the rule-based similarity logic;
- `issue_triage_agent.similarity.similarity_score(...)` to compare two analysed issues and return the existing similarity score.

The production duplicate threshold was **0.48**. The baseline evaluator reused these functions unchanged. No model was trained as part of the baseline, and the baseline path did not call a hosted LLM.

This is important scientifically: a baseline is the control measurement. If the original scoring function had been quietly changed before it was measured, there would be no trustworthy “before” result.

---

## 3. Why a benchmark was necessary

A few manually selected examples are not enough to establish whether a duplicate detector generalises. A useful experiment needs a large number of examples, consistent labels, a reproducible preparation procedure and a rule that prevents test data from influencing model selection.

Three data roles were kept separate:

| Data split | Purpose | What it is allowed to influence |
|---|---|---|
| Training | Fit score scaling and choose thresholds | Calibration and threshold selection |
| Validation | Compare methods and choose a candidate | Method selection and design decisions |
| Test | One final measurement after settings are frozen | Reporting only; no tuning |

A second issue is the meaning of a negative label. The source dataset contains known duplicate links, but it does not prove that every pair with no link is unrelated. Some real duplicates may simply be absent from the source labels. The project therefore calls the constructed negative pairs **weak negatives** and keeps that warning in the dataset columns, manifest, reports and documentation.

The main evaluation questions were:
1. How many source-labelled duplicate pairs does the existing detector find?
2. Does it rank a useful historical issue near the top?
3. Does BM25 or a semantic model improve on word-overlap logic?
4. What is the precision/recall trade-off when a larger share of duplicates is found?
5. Can the result be reproduced without using test labels to pick the method or threshold?

---

## 4. Phase 1: obtain and pin the dataset

### 4.1 Source dataset

The project used [Primordic / IssueDupesLite](https://huggingface.co/datasets/primordic/IssueDupesLite). Each source row describes a relationship between two GitHub issues and contains repository identity, issue numbers, titles, bodies, creation timestamps and source closing-comment information.

The run recorded:

| Field | Value |
|---|---|
| Dataset ID | `primordic/IssueDupesLite` |
| Resolved dataset revision | `902b5805afa93e8cb018bd3c860c0f3eba55029e` |
| Dataset fingerprint | `24bb969f9437e210` |
| Declared data licence | `CC-BY-SA-4.0` |
| Loaded source rows | 10,000 |

The downloader asks the Hugging Face Hub for dataset metadata, resolves the requested revision to a commit SHA, and loads rows from that exact revision. The resolved SHA and fingerprint are saved in the generated manifest. This is safer than saving only a moving branch name such as `main`.

### 4.2 What “1,000 repositories” means

The 10,000 source rows are issue-pair records, not 10,000 separate individual issues. The preparation script gathers the issue records appearing in those pairs, groups them by repository, and records **1,000 distinct repository names** in the manifest.

This means the benchmark's dataset population represents 1,000 repositories. It does **not** mean the workflow crawled all 1,000 repositories live through the GitHub API. The final held-out evaluation is a repository-disjoint subset of 150 repositories.

### 4.3 Normalize the issue records

For each row, the preparation code:
1. reads the repository name from the available source fields;
2. validates issue numbers as positive integers;
3. normalizes titles, descriptions and creation timestamps;
4. stores records by repository and issue number;
5. if the same issue appears more than once, keeps the richer title/body record;
6. creates a stable pair identifier from the repository and sorted issue numbers.

A stable pair ID makes it possible to detect duplicated rows and prove that the same pair was not placed in more than one split.

### 4.4 Cleanup counts

| Preparation event | Count |
|---|---:|
| Source rows loaded | 10,000 |
| Invalid issue-record rows skipped | 0 |
| Invalid, self-pair or otherwise unusable positive rows skipped | 43 |
| Repeated source positive rows collapsed | 20 |
| Unique positive pairs kept | 9,937 |

The 43 skipped rows and the 20 collapsed repeated rows are different cases. The first group did not become valid positive pairs. The second group repeated an already represented pair and was merged rather than counted twice.

### 4.5 Preserve chronology instead of assuming source roles

The dataset notes that the selected “primary” issue can sometimes be newer than the issue called its “duplicate”. The code therefore does not assume that source primary/duplicate roles are the same as chronological incoming/historical roles.

It compares the issue creation timestamps:
- earlier issue = historical candidate;
- later issue = incoming issue;
- missing, invalid or equal timestamps = chronology unknown/unordered.

Original source roles are preserved separately. Retrieval metrics only group candidates by incoming issue when chronology is valid.

---

## 5. Phase 1: clean records and construct pairs

### 5.1 Source positives

A positive pair is a relationship that the source dataset labels as duplicate. The preparation script validates both issue numbers, rejects a self-pair, normalizes the record and deduplicates the pair using its stable pair ID.

The final prepared set contains **9,937 unique source-annotated positives**. These are source labels, not independent human adjudications conducted by this project.

### 5.2 Why the benchmark adds negative examples

The source data provides positive relationships. To compare a detector, the experiment also needs pairs that are not linked as known duplicates in that source sample. The script constructs same-repository pairs from issue records, excluding pairs connected through a known positive duplicate component.

These constructed rows are marked:

`weak_unlinked_candidate_not_human_verified`

That label is deliberately verbose so it cannot be mistaken for ground truth.

### 5.3 Prevent duplicate chains from becoming negatives

Consider three reports A, B and C. If the source says A-B are duplicates and A-C are duplicates, then B and C belong to the same known duplicate family. Treating B-C as a negative simply because the exact B-C relationship is not separately listed would be contradictory.

The preparation code uses a **Union-Find / disjoint-set** structure to join issue numbers connected through known positive links. Candidate negative pairs whose endpoints fall inside the same connected component are excluded.

In plain language: if the source already connects two reports through a chain of duplicate relationships, the sampler does not label them as different just because there is no direct pair row between those two particular reports.

---

## 6. Phase 1: build weak negatives

### 6.1 Sampling target

The preparation target is one negative per positive pair:
- negative-to-positive ratio: `1.0`;
- random seed: `42`;
- hard-negative target fraction: `0.5`.

The sampling occurs within repositories. This is more challenging than pairing an issue from one project with an unrelated issue from a completely different project.

### 6.2 Hard lexical examples

Hard negatives are unlinked issue pairs with some word overlap. A sampling hint combines:
- 65% title token Jaccard similarity;
- 35% issue-text token Jaccard similarity.

Eligible non-zero overlap pairs are sorted by this hint, and the highest-ranked ones are chosen first. This is only a **sampling heuristic**. It is not the live detector's similarity score, and it is not used as the final label or prediction rule.

### 6.3 Random same-repository examples

After choosing the hard lexical pairs, the script shuffles the remaining eligible same-repository pairs with the seeded random generator. It selects enough to fill the remaining per-repository target.

This gives the experiment two types of difficult cases: examples that look lexically similar but lack a known duplicate link, and a random sample of other unlinked pairs.

### 6.4 Final counts

| Weak-negative type | Pair count |
|---|---:|
| Hard lexical | 4,941 |
| Random same-repository | 4,996 |
| **Total** | **9,937** |

The totals balance the 9,937 positives. The hard/random split is not exactly 50/50 because the target is rounded per repository and some repositories do not have enough eligible hard-negative candidates.

---

## 7. Phase 1: prevent repository leakage

### 7.1 Why the split unit is the repository

A random row split can put some issue pairs from the same repository into training and other pairs from that repository into test. The model could then benefit from project-specific words, component names or writing conventions seen during training. That would make the test look more general than it really is.

This benchmark assigns each repository to exactly one split. All positive and weak-negative pairs from that repository follow the same assignment.

### 7.2 Deterministic allocation

The split procedure:
1. counts source-positive pairs for each repository;
2. shuffles repository order using seed 42 to make tie-breaking deterministic;
3. sorts repositories by descending pair count;
4. greedily assigns each repository to the split furthest below its target pair count;
5. applies the repository assignment to every pair in that repository.

Target ratios are 70% training, 15% validation and 15% test. The procedure aims to balance pair counts while preserving repository boundaries.

### 7.3 Actual split counts

| Split | Repositories | Positive pairs | Weak negatives | Total pairs |
|---|---:|---:|---:|---:|
| Training | 700 | 6,954 | 6,954 | 13,908 |
| Validation | 150 | 1,492 | 1,492 | 2,984 |
| Test | 150 | 1,491 | 1,491 | 2,982 |
| **Total** | **1,000** | **9,937** | **9,937** | **19,874** |

The workflow checks:
- every repository is assigned to one split only;
- each pair ID occurs in exactly one split;
- actual repository names match their split manifest;
- the train/test repository sets are disjoint;
- all negative rows carry the weak-label warning.

The Phase 6 evaluator repeats the train/test isolation checks before it scores the final test set. Repository separation is stronger than pair-level separation for this use case, because it tests whether a method can generalize to repositories it has not trained on.

---

## 8. Phase 2: measure the unchanged baseline

The baseline evaluator imports the application's existing analyser and similarity function. It does not substitute a new model or adjust the scoring code.

### Baseline settings

| Setting | Value |
|---|---|
| Scorer | Existing lexical/rule-based detector |
| Production threshold | 0.48 |
| Evaluation split | Held-out test |
| Pairs | 2,982 |
| Positive source labels | 1,491 |
| Weak negatives | 1,491 |

### Results

| Metric | Result |
|---|---:|
| Accuracy | 54.33% |
| Precision | 87.28% |
| Recall | 10.13% |
| F1 | 18.15% |
| Specificity | 98.52% |
| ROC AUC | 64.10% |
| Average precision | 65.66% |

Confusion-style counts:
- 151 source-positive pairs were flagged;
- 1,340 source-positive pairs were not flagged;
- 22 weak-negative pairs were flagged;
- 1,469 weak-negative pairs were not flagged.

The detector was conservative: when it flagged a pair, that pair often matched the source label, but it missed many source-labelled positive pairs at the existing threshold. The 22 weak-negative alerts are not necessarily genuine false positives because a weak negative may itself be a duplicate missing from the source relationships.

This baseline is a fixed reference point. It remains the same in the final comparison.

---

## 9. Phase 3: compare four similarity methods

The four methods were evaluated with the same train/validation data and the same repository isolation rule.

### 9.1 Existing Lexical method

This is the existing Issue Triage Agent analyser and similarity function. It relies on the application's current rules and lexical features. The comparison script caches repeated issue analyses for efficiency but does not alter the scoring function.

### 9.2 BM25

BM25 is a search-ranking method that rewards useful terms and down-weights words that appear in many documents. For this experiment:
- issue records are grouped by repository within each split;
- the indexed text uses the issue title and up to 3,000 body characters;
- each pair is scored in both query directions;
- the two directions are averaged to create a symmetric pair score.

The BM25 index is built from the issue records present in that prepared split. It is not a complete index of every issue currently in that GitHub repository.

### 9.3 Semantic embeddings

Semantic similarity uses the local model `sentence-transformers/all-MiniLM-L6-v2`:
- run locally on CPU;
- title and issue text are encoded;
- maximum sequence length is 256 tokens;
- embeddings are normalized;
- cosine similarity is computed as a dot product between normalized vectors.

Unlike word overlap, semantic embeddings can score descriptions with different words as related in meaning. The model is downloaded and run locally; the benchmark does not require a hosted LLM API key.

### 9.4 Hybrid

Hybrid combines BM25 and Semantic:
- 50% BM25;
- 50% Semantic;
- each component is standardized using training-set mean and standard deviation;
- the standardized component is passed through a logistic mapping;
- training-derived scaling statistics are reused for validation and later test data.

This is important because raw BM25 scores and cosine similarities live on different scales. Averaging raw values directly would allow one component's scale to dominate the result.

### 9.5 Threshold selection

Each method's F1-maximizing threshold is selected using **training labels only**. The selected threshold is applied unchanged to validation. Test labels are not involved in this phase.

### 9.6 Validation results

| Method | ROC AUC | Average precision | F1 | MRR@3 | Recall@3 |
|---|---:|---:|---:|---:|---:|
| Lexical | 0.6541 | 0.6419 | 0.6804 | 0.8102 | 0.9933 |
| BM25 | 0.7031 | 0.6780 | 0.7060 | 0.8712 | 0.9967 |
| Semantic | **0.8120** | **0.7893** | **0.7637** | 0.9158 | 0.9967 |
| Hybrid | 0.7918 | 0.7614 | 0.7539 | **0.9178** | **1.0000** |

Eligible validation retrieval groups: **598**. A group is eligible only if it contains at least two sampled candidates and at least one source-positive candidate. Singleton groups are excluded.

Semantic led on pairwise F1, ROC AUC and average precision. Hybrid had a small lead on top-three ranking measures. Hybrid was selected because the product's main proposed interaction is a shortlist of up to three previous issues for a maintainer to inspect. This is a decision based on product objective, not a claim that Hybrid is best at every metric.

### Training-selected thresholds

| Method | Threshold |
|---|---:|
| Lexical | 0.093209 |
| BM25 | 5.445388 |
| Semantic | 0.426541 |
| Hybrid | 0.41291124292046016 |

Threshold values are not directly comparable across methods because the score scales differ.

---

## 10. Phase 4: analyse errors and create blind review files

Phase 4 looks at examples where methods disagree or where a pair deserves manual inspection. It uses validation data only and does not adjust the live detector.

The selection procedure considers, for each method:
- high-scoring weak-negative pairs that crossed its training-selected threshold;
- low-scoring source-positive pairs below its threshold.

It selects up to ten examples of each review reason per method. Repeated pairs are deduplicated by pair/reason, and a `triggered_by` field records which methods selected them. The result is **56 unique review rows**.

Two files are generated for different audiences:

| File | Contents | Intended use |
|---|---|---|
| `review_examples.csv` | Labels, sample types, method scores, thresholds and reasons | Diagnostic analysis only |
| `reviewer_blind.csv` | Canonical issue links, titles, shortened descriptions and blank reviewer fields | First view for independent reviewers |

The blind file intentionally hides source labels, model scores, sample type and the reason each pair was selected. This reduces anchoring bias. The guide uses four decisions:
- `same_underlying_issue`;
- `related_but_distinct`;
- `different_issues`;
- `insufficient_context`.

Reviewers should open both original issues, read full descriptions and useful discussion, record confidence (high/medium/low), and add evidence notes. Identical titles or error strings alone are not enough to call a pair a duplicate.

---

## 11. Phase 5: AI-assisted source evidence audit

A separate AI-assisted audit examined the 56 selected pairs using original GitHub issue descriptions and available discussion comments.

Its preliminary evidence breakdown was:
- 26 likely same underlying issue;
- 16 related but distinct;
- 13 different issues;
- 1 insufficient context.

This was a diagnostic evidence review, not independent human adjudication. It was not substituted for the source dataset labels, was not used as a new benchmark label set, and was not used for threshold tuning.

The separate blind-review workbook remained available, with reviewer decision fields blank. Independent human decisions are still outstanding. This distinction must remain explicit in future reports: AI-produced notes and human-adjudicated labels are not interchangeable.

---

## 12. Phase 6: freeze the Hybrid decision

### 12.1 Why freeze before test

Repeatedly checking a test set and changing the model in response turns the test set into another validation set. The final score then becomes biased by the tuning process.

Before running Phase 6, the project stored the complete decision in `evaluation/frozen_hybrid_config.json`. It includes:
- decision ID: `phase6-frozen-hybrid-v1`;
- method: Hybrid;
- BM25 weight: 0.5;
- Semantic weight: 0.5;
- embedding model: `sentence-transformers/all-MiniLM-L6-v2`;
- maximum sequence length: 256;
- train-only score calibration;
- frozen threshold: `0.41291124292046016`;
- retrieval list size: top 3;
- dataset ID, revision, fingerprint and seed;
- expected training/test row counts and test repository count;
- an explicit statement that the configuration was frozen before test evaluation.

### 12.2 Integrity protections

The Phase 6 runner (`evaluation/frozen_hybrid.py`) fails closed if:
- dataset revision, fingerprint or seed differ from the frozen config;
- training or test row counts change;
- test repository count changes;
- a repository appears in both training and test;
- pair IDs overlap between the two splits;
- the method is no longer Hybrid;
- the requested model name differs from the frozen model name;
- the training-derived threshold does not match the recorded frozen value.

The threshold is recomputed from training data only as an integrity check. The evaluator does not use the test labels to select a replacement threshold. It also runs the unchanged baseline evaluator on the exact same test rows.

### 12.3 Frozen threshold and score construction

Training-only component statistics are used to transform BM25 and Semantic scores. Each transformed component is then weighted 50/50. The frozen threshold is applied to the resulting Hybrid score. The top-three candidate ranking sorts historical candidates by the Hybrid score for each eligible incoming issue.

---

## 13. Phase 6: final held-out test results

The completed run was [GitHub Actions run 41366209127](https://github.com/yerageracharan/issue-triage-agent/actions/runs/41366209127). It evaluated **2,982 pairs across 150 test repositories**. Training contained 13,908 pairs across 700 other repositories. The repository sets were disjoint, and the training-derived threshold recomputed exactly to `0.41291124292046016`.

### 13.1 Classification and ranking results

| Metric | Existing detector | Frozen Hybrid |
|---|---:|---:|
| Precision | 87.28% | 65.60% |
| Recall | 10.13% | 85.45% |
| F1 | 18.15% | 74.22% |
| ROC AUC | 64.10% | 78.90% |
| Average precision | 65.66% | 77.65% |
| MRR@3 | 79.76% | 92.15% |
| Recall@3 | 98.87% | 99.68% |

### 13.2 What the frozen threshold flagged

| Count | Existing detector | Frozen Hybrid |
|---|---:|---:|
| Source-positive pairs flagged | 151 | 1,274 |
| Weak-negative alerts | 22 | 668 |
| Weak negatives not flagged | 1,469 | 823 |
| Source-positive pairs below threshold | 1,340 | 217 |

Hybrid's increased recall means it captures substantially more source-positive pairs on this prepared dataset. It also flags more unlinked weak-negative pairs. A weak-negative alert is **not automatically a verified false positive**.

### 13.3 Top-three candidate ranking

The final retrieval comparison used **620 eligible incoming-issue groups**: at least two sampled candidate pairs and at least one source-positive pair.

| Ranking metric | Existing detector | Frozen Hybrid |
|---|---:|---:|
| MRR@3 | 0.797581 (79.76%) | 0.921505 (92.15%) |
| Recall@3 | 0.988710 (98.87%) | 0.996774 (99.68%) |

The Hybrid ranked shortlist improved in this benchmark. The eligible groups are a subset, not every live incoming issue that could exist in those repositories.

### 13.4 Practical interpretation

The result has a clear trade-off:
- the existing detector is conservative and has higher precision against the source labels;
- Hybrid finds many more known positive pairs and improves ranking quality;
- Hybrid generates more review candidates and therefore needs a clear review interface and evidence explanations.

This supports a human-in-the-loop suggestion tool. It does not support treating the score as a calibrated probability or automatically taking action on issues.

---

## 14. End-to-end GitHub Actions workflow

The benchmark is reproducible through `.github/workflows/benchmark-data.yml`. The workflow:
1. checks out the repository;
2. sets up Python 3.11;
3. installs CPU-only PyTorch and benchmark/test/similarity dependencies;
4. runs benchmark preparation, baseline, similarity, error-analysis and frozen-evaluator tests;
5. downloads the pinned IssueDupesLite snapshot and prepares the 1,000-repository splits;
6. validates expected files, dataset revision, weak-label markers and repository isolation;
7. evaluates the unchanged baseline on the held-out test split;
8. compares Lexical, BM25, Semantic and Hybrid on validation;
9. creates the Phase 4 analysis and blind-review pack;
10. executes the frozen Hybrid evaluator on the test split;
11. uploads the complete generated folder as a GitHub Actions artifact.

The completed artifact is `issuedupeslite-benchmark-26`, artifact ID `13107604354`. It contains prepared data, manifest and attribution, train/validation/test CSVs, baseline outputs, Phase 3 comparison, Phase 4 review files, and Phase 6 JSON/Markdown results plus per-pair and top-three CSVs. Artifact retention is 30 days; the recorded artifact expiry is 2 December 2026.

The separate test workflow runs on Python 3.10, 3.11, 3.12 and 3.13. In run [41368431336](https://github.com/yerageracharan/issue-triage-agent/actions/runs/41368431336), **53 tests passed on each Python version**.

---

## 15. What changed in the repository

| Area | File or component | What it does |
|---|---|---|
| Dataset preparation | `evaluation/benchmark/prepare_benchmark.py` | Loads source data, normalizes issue records, samples pairs, creates repository splits and manifest |
| Baseline | `evaluation/benchmark/evaluate_baseline.py` | Runs unchanged production analyser/similarity logic against prepared pairs |
| Similarity research | `evaluation/benchmark/evaluate_similarity_methods.py` | Implements lexical, BM25, Semantic and Hybrid comparisons |
| Error analysis | `evaluation/benchmark/analyze_similarity_errors.py` | Summarises disagreements and prepares diagnostic and blinded review files |
| Frozen final runner | `evaluation/frozen_hybrid.py` | Validates frozen inputs and computes the one-time final test metrics |
| Frozen decision | `evaluation/frozen_hybrid_config.json` | Stores method, model, threshold, weights, dataset identity and guardrails |
| Automation | `.github/workflows/benchmark-data.yml` | Runs the full data-to-report benchmark workflow |
| Cross-version tests | `.github/workflows/tests.yml` | Runs automated tests on four supported Python versions |
| Review instructions | `docs/HUMAN_REVIEW_GUIDE.md` | Explains blind human adjudication |
| Evaluation record | `docs/EVALUATION.md` | Maintains the experiment history and limitations |
| Decision record | `docs/PHASE6_DECISION.md` | Records why Hybrid was selected and what the final test showed |

The production detector itself was not silently swapped to Hybrid as part of the offline benchmark. The Hybrid result is an experimental evaluation; a later integration must be implemented and tested separately.

---

## 16. How to reproduce the work

The following commands are for PowerShell from the repository root. Run the steps in order. The dataset-derived issue text is stored in the generated directory and should not be committed casually to the source repository.

### 16.1 Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[benchmark,test,similarity-experiments]"
```

For a CPU-only PyTorch installation, follow the CPU wheel command used by the workflow before installing the experiment extras.

### 16.2 Prepare the benchmark

```powershell
python -m evaluation.benchmark.prepare_benchmark `
  --dataset-id primordic/IssueDupesLite `
  --seed 42 `
  --negative-ratio 1.0 `
  --hard-negative-fraction 0.5 `
  --train-ratio 0.70 `
  --validation-ratio 0.15 `
  --test-ratio 0.15 `
  --output-dir evaluation/benchmark/generated `
  --cache-dir evaluation/benchmark/.cache
```

Check the generated `manifest.json`, repository split file and attribution before proceeding.

### 16.3 Re-run the unchanged baseline

```powershell
python -m evaluation.benchmark.evaluate_baseline `
  --test-csv evaluation/benchmark/generated/test.csv `
  --manifest evaluation/benchmark/generated/manifest.json `
  --output-dir evaluation/benchmark/generated/baseline
```

### 16.4 Compare the four methods on validation

```powershell
python -m evaluation.benchmark.evaluate_similarity_methods `
  --train-csv evaluation/benchmark/generated/train.csv `
  --validation-csv evaluation/benchmark/generated/validation.csv `
  --model sentence-transformers/all-MiniLM-L6-v2 `
  --output-dir evaluation/benchmark/generated/phase3
```

This step uses the training split to fit score calibration and choose each method's threshold, then measures validation without tuning on validation labels.

### 16.5 Generate the Phase 4 review pack

```powershell
python -m evaluation.benchmark.analyze_similarity_errors `
  --validation-csv evaluation/benchmark/generated/validation.csv `
  --scores-csv evaluation/benchmark/generated/phase3/similarity_scores.csv `
  --comparison-json evaluation/benchmark/generated/phase3/similarity_comparison.json `
  --output-dir evaluation/benchmark/generated/phase4 `
  --top-n 10
```

Use `reviewer_blind.csv` for reviewers. Do not provide `review_examples.csv` as the first view because it contains labels and model information.

### 16.6 Run the frozen final evaluator

```powershell
python -m evaluation.frozen_hybrid `
  --train-csv evaluation/benchmark/generated/train.csv `
  --test-csv evaluation/benchmark/generated/test.csv `
  --manifest evaluation/benchmark/generated/manifest.json `
  --config evaluation/frozen_hybrid_config.json `
  --model sentence-transformers/all-MiniLM-L6-v2 `
  --output-dir evaluation/benchmark/generated/phase6
```

Do not tune the method based on the resulting test report. A changed method needs new validation data and a new untouched test set.

---

## 17. How to interpret the metrics

| Metric | Plain-language meaning |
|---|---|
| Precision | Of the pairs the model flagged, how many have a source-positive label? |
| Recall | Of the source-positive pairs, how many did the model find? |
| F1 | A combined precision/recall measure. |
| Specificity | Of the weak negatives, how many did not cross the threshold? |
| ROC AUC | How well scores rank positive-label pairs above weak-negative pairs over many thresholds. |
| Average precision | How concentrated positive-label examples are near the top of the full score ranking. |
| MRR@3 | How highly the first known positive appears among the first three suggestions. |
| Recall@3 | How much of the source-positive candidate set is retrieved within the first three results. |

A MRR@3 value of 0.92 is **not** a 92% probability that a specific suggestion is correct. It is an average ranking metric over eligible groups. Likewise, the Hybrid score is not automatically a calibrated probability.

---

## 18. Limitations and reproducibility risks

1. **Weak negative labels.** The 9,937 negative pairs are unlinked candidates, not pairs independently confirmed to be different issues. Some may be genuine duplicates missing from the source links.
2. **Source positives are not fully adjudicated.** The 9,937 positives come from source duplicate links. The project has not independently verified every source relationship.
3. **AI evidence notes are not human labels.** The Phase 5 audit is AI-assisted and does not replace independent reviewer decisions.
4. **Top-three metrics cover eligible groups only.** The final 620 retrieval groups must contain at least two sampled candidates and at least one source-positive pair. The metrics do not cover every possible live incoming issue.
5. **Pair benchmark is not a live production study.** It does not measure current GitHub API coverage, rate limits, full repository candidate generation, latency, memory, deployment cost, maintainer acceptance or usefulness in day-to-day triage.
6. **Model revision is not pinned.** The name `sentence-transformers/all-MiniLM-L6-v2` is frozen, but the upstream model commit SHA is not explicitly recorded. Future downloads could resolve to changed weights.
7. **BM25 index scope.** The BM25 index contains only issue records present in the prepared split, not a complete index of all current repository issues.
8. **One test sample is still one test sample.** Do not repeatedly tune against it. Another experiment needs new validation data and a fresh untouched test set.
9. **Dataset licence.** IssueDupesLite declares CC-BY-SA-4.0. Generated data includes third-party GitHub issue text. Preserve dataset attribution and comply with the share-alike licence for derived benchmark data. The project's MIT source-code licence is separate.

---

## 19. What the benchmark proves - and does not prove

### Supported by this experiment

- The original detector was conservative at its existing 0.48 threshold on the prepared test pairs.
- BM25 and Semantic improved on important validation measures compared with the lexical baseline.
- Hybrid was a defensible method choice for a top-three shortlist objective.
- The frozen config passed dataset, repository isolation and threshold integrity checks.
- On the held-out sample, Hybrid improved recall, F1 and top-three ranking metrics compared with the unchanged detector.
- The full workflow and four-version automated test matrix completed successfully.

### Not established by this experiment

- It does not prove that 65.60% of all live Hybrid alerts are truly duplicates.
- It does not prove that the 668 weak-negative alerts are confirmed false positives.
- It does not prove production accuracy on every GitHub repository or issue type.
- It does not prove that the live agent already uses Hybrid in its production output path.
- It does not prove that maintainers will accept or act on the suggestions.
- It does not justify automatically closing, labelling, assigning or commenting on GitHub issues.

The correct conclusion is limited: Hybrid performed better on this prepared benchmark and merits a read-only suggestion prototype with human confirmation.

---

## 20. Next engineering steps

1. **Build a read-only ranked-suggestion interface.** Return up to three historical issue candidates for an incoming issue, with canonical links, titles and evidence fields.
2. **Explain the score.** Show BM25 contribution, Semantic contribution, combined ranking score and chronology validity. Do not describe the score as a probability.
3. **Use shadow mode first.** Run the ranker on representative current repositories without changing repository state. Log candidate coverage, latency, failures and maintainer usefulness.
4. **Complete independent adjudication.** Have reviewers inspect the 56 blinded examples. Ideally label a larger representative sample and have two reviewers independently assess a subset.
5. **Pin model provenance.** Record upstream model commit SHA, package versions, preprocessing details and a model artifact checksum.
6. **Create a new evaluation set before future tuning.** Preserve the Phase 6 result. Future threshold/model changes require new validation data and a new untouched test set.
7. **Keep actions disabled.** Do not automatically close issues, add labels, assign people or post comments. Any future action feature needs separate authorisation and safeguards.

---

## 21. Key files, run records and references

### Core repository files

- [Dataset preparation](https://github.com/yerageracharan/issue-triage-agent/blob/main/evaluation/benchmark/prepare_benchmark.py)
- [Baseline evaluator](https://github.com/yerageracharan/issue-triage-agent/blob/main/evaluation/benchmark/evaluate_baseline.py)
- [Four-method comparison](https://github.com/yerageracharan/issue-triage-agent/blob/main/evaluation/benchmark/evaluate_similarity_methods.py)
- [Phase 4 error analyser](https://github.com/yerageracharan/issue-triage-agent/blob/main/evaluation/benchmark/analyze_similarity_errors.py)
- [Frozen Hybrid evaluator](https://github.com/yerageracharan/issue-triage-agent/blob/main/evaluation/frozen_hybrid.py)
- [Frozen configuration](https://github.com/yerageracharan/issue-triage-agent/blob/main/evaluation/frozen_hybrid_config.json)
- [Benchmark workflow](https://github.com/yerageracharan/issue-triage-agent/blob/main/.github/workflows/benchmark-data.yml)
- [Python test workflow](https://github.com/yerageracharan/issue-triage-agent/blob/main/.github/workflows/tests.yml)
- [Blind-review guide](https://github.com/yerageracharan/issue-triage-agent/blob/main/docs/HUMAN_REVIEW_GUIDE.md)
- [Full evaluation record](https://github.com/yerageracharan/issue-triage-agent/blob/main/docs/EVALUATION.md)
- [Phase 6 decision record](https://github.com/yerageracharan/issue-triage-agent/blob/main/docs/PHASE6_DECISION.md)

### Recorded workflow runs

- [Phase 6 benchmark run 41366209127](https://github.com/yerageracharan/issue-triage-agent/actions/runs/41366209127) - completed successfully; artifact `issuedupeslite-benchmark-26`.
- [Python tests run 41368431336](https://github.com/yerageracharan/issue-triage-agent/actions/runs/41368431336) - 53 tests passed on Python 3.10, 3.11, 3.12 and 3.13.

### Dataset and licence

- [IssueDupesLite dataset card](https://huggingface.co/datasets/primordic/IssueDupesLite)
- Dataset revision: `902b5805afa93e8cb018bd3c860c0f3eba55029e`
- Declared dataset licence: CC-BY-SA-4.0
- Project source-code licence: MIT. These licences apply to different materials and must not be confused.

---

**End of benchmark engineering walkthrough.**  
This record describes the work through Phase 6. If the code, dataset revision or model configuration changes later, add a new dated record rather than silently rewriting the historical result.
