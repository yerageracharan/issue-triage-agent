# Agent Instructions

These instructions apply across Issue Triage Agent.

## Product invariants

- The agent classifies and prioritizes issues; it does not decide whether an issue is valid, mergeable, or resolved.
- Similarity scores are candidate-ranking signals, not proof that two issues share a root cause.
- Category and priority rules are explainable heuristics; preserve their rationale and limitations.
- Keep the default workflow read-only. Never write comments, labels, assignments, milestones, or state changes without an explicitly reviewed opt-in feature.
- Human review is required before operational decisions.
- Secrets, GitHub tokens, private issue bodies, and sensitive repository data must never appear in logs, test fixtures, or public reports.

## Repository map

- `src/issue_triage_agent/`: typed issue models, analyzer, classification, similarity, GitHub client, CLI, reporting, and MCP integration.
- `tests/`: deterministic fixtures and regression tests.
- `docs/`: GitHub setup, human review, architecture, evaluation, and local-agent integration.
- `evaluation/`: benchmark/evaluation assets; keep examples reproducible and clearly labelled.

## Working rules

- Read the affected module, callers, tests, and relevant docs before changing classification or API contracts.
- Add boundary tests for tokenization, malformed payloads, empty inputs, confidence thresholds, and external API failures.
- Keep GitHub API scopes minimal and use mocked clients in tests.
- Never claim a category or priority is objective ground truth.
- Update evaluation notes whenever a rule or similarity behavior changes.

## Validation

```bash
python -m pytest -q
```

## Change ownership and proof

- Keep one authoritative owner for each domain rule and each persisted state. UI, CLI, MCP, and provider adapters translate inputs and outputs; they must not reimplement business policy or become competing sources of truth.
- Before changing a contract, trace the input through its owner to every consumer. Update callers, schemas, examples, docs, and regression tests together. Remove superseded paths unless a documented public-compatibility requirement keeps them.
- Keep optional external model/provider integrations behind adapters. Use injected or mocked adapters for deterministic unit tests; label live network/provider checks separately and never describe a mock as live verification.
- Validate untrusted user, model, file, and network data at the boundary. Preserve the product's evidence/provenance rules and reject malformed inputs rather than silently inventing defaults.
- Verify the supported user entry point and at least one relevant failure path. Report exact commands and results; CI on a different commit SHA is not proof for the current change.
- Keep the root README as the user entry point, `docs/README.md` as the documentation map, and focused guides as the owners of detailed contracts. Update links when files move. Do not hand-edit generated output when a source or generator owns it.


## Repository automation rules

- Treat files under `.github/workflows/` as production code. When changing a workflow, inspect the triggered run for the exact commit SHA; a prior green run is not proof for a newer commit.
- Pin third-party GitHub Actions to full 40-character commit SHAs and keep the upstream release tag in a trailing comment. Do not replace a pinned SHA with a floating major-version tag.
- Use the least-privilege `permissions` block. Default to read-only; grant write access only to the specific job that must publish or commit generated output.
- Give every job a finite `timeout-minutes`. Add a clear `concurrency` group for expensive or supersedable work; cancel stale pull-request runs, but do not cancel workflows whose purpose is to publish a completed artifact or evidence.
- Keep workflow logs and uploaded artifacts free of secrets and personal data. Set retention to the shortest period that still serves the evaluation or debugging purpose.
- Rely on the existing Dependabot configuration for action updates, then review release notes and run the affected workflow before considering the update complete.
