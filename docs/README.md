# Documentation map

The [project README](../README.md) is the canonical product guide for installation, issue import, deterministic classification, duplicate suggestions, optional AI summaries, and GitHub integration.

## Architecture and operating guidance

- [System architecture](ARCHITECTURE.md) — the pipeline from issue payload to typed issue, deterministic triage, optional similarity, and report.
- [Local agent setup](LOCAL_AGENT_SETUP.md) — run the agent locally.
- [GitHub setup](GITHUB_SETUP.md) — configure GitHub access and repository inputs.
- [Human review guide](HUMAN_REVIEW_GUIDE.md) — interpret categories, priorities, confidence, and suggested labels before taking action.
- [Phase 6 decision record](PHASE6_DECISION.md) — recorded implementation decision and rationale.

## AI assistant integrations

- [Claude Desktop setup](CLAUDE_DESKTOP_SETUP.md)
- [ChatGPT setup](CHATGPT_SETUP.md)

## Evaluation and quality

- [Evaluation guide](EVALUATION.md) — datasets, metrics, and known limitations.
- [Benchmark engineering walkthrough](BENCHMARK_ENGINEERING_WALKTHROUGH.md) — how the benchmark is assembled and interpreted.
- [Automated tests](../tests/) — deterministic classification, payload validation, similarity, and regression coverage.

## Code ownership map

- `src/issue_triage_agent/models.py` — normalized issue and triage result contracts.
- `src/issue_triage_agent/analyzer.py` — deterministic category, priority, confidence, and rationale rules.
- `src/issue_triage_agent/similarity.py` — heuristic duplicate candidates.
- `src/issue_triage_agent/` — GitHub/provider adapters, orchestration, and report generation.

## Repository governance

- [Contribution workflow](../CONTRIBUTING.md)
- [AI coding-agent instructions](../AGENTS.md)
- [Security policy](../SECURITY.md)
- [Issue forms and PR template](../.github/)

Suggested labels and priorities are review aids. They should not automatically close, assign, or modify issues without an explicit maintainer action.
