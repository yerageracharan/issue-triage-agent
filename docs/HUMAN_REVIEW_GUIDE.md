# Issue-pair human adjudication guide

Use this guide with the Phase 4 file named reviewer_blind.csv.

## Goal

Independently decide whether two GitHub reports describe the same underlying defect or feature request. The purpose is to inspect uncertain benchmark examples, not to confirm the model's predictions.

## Review procedure

1. Open both issue URLs and read the complete issue descriptions.
2. Read useful comments, linked pull requests, reproduction steps, environment details, and stack traces where available.
3. Decide whether the reports describe the same underlying problem/request, merely a related topic, or different problems.
4. Record one value in human_adjudication:
   - same_underlying_issue: substantially the same bug, failure, or feature request.
   - related_but_distinct: connected feature/component, but a different underlying problem or request.
   - different_issues: unrelated problems.
   - insufficient_context: available evidence is not enough to decide.
5. Record reviewer_confidence as high, medium, or low.
6. Explain the evidence in reviewer_notes.

## Avoid common mistakes

- Identical titles or error strings do not automatically mean duplicate reports. Generic templates can describe different failures.
- Two issues in the same repository or subsystem are not automatically duplicates.
- A follow-up, documentation request, workaround, or enhancement may be related but distinct.
- A source-linked pair is not automatically correct; original dataset links can be noisy.
- An unlinked pair is not automatically distinct; it may be a duplicate that was never linked.
- Do not guess from the short body excerpts. Open the source issues and use insufficient_context when evidence remains inadequate.

## Keep the review blind

The reviewer_blind.csv file intentionally excludes the original source label, sample type, method names, model scores, and threshold decisions. Do not merge in those columns until the independent review has been completed.

Keep the original blind CSV unchanged. Save completed reviewer copies separately. Preserve pair_id so results can be merged back into the diagnostic review_examples.csv. Ideally, two reviewers should independently label a subset; resolve disagreements before treating the adjudications as reference labels.

## Interpretation

These examples come from the validation split. They can help diagnose weak labels and understand model disagreements. They must not be used to repeatedly tune on the held-out test split. A review of 56 selected pairs is not a substitute for a larger, representative, independently labelled test set.
