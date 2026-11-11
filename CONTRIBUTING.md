# Contributing

Thanks for improving Issue Triage Agent. The project is a read-only assistant for classifying, prioritizing, and explaining GitHub issues. Human maintainers retain control over every repository write action.

## Before changing code

1. Search existing issues and commits for overlapping work.
2. Open an issue before new classification categories, scoring changes, model integrations, or architecture changes. Describe the user problem, examples, alternatives, and evaluation plan.
3. For a bug, include a minimal synthetic issue payload, exact command, expected category/priority, actual result, and relevant redacted logs.
4. Keep each pull request focused on one behavior or one coherent maintenance change.

## Development setup

Python 3.10 or newer.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

For MCP work, install the optional extra separately:

```bash
python -m pip install -e ".[mcp]"
```

## Validation

```bash
python -m pytest -q
```

Add regression tests for category and priority rules, whole-word matching, malformed GitHub payloads, duplicate-candidate thresholds, and missing/ambiguous issue fields. Keep tests deterministic and network-free unless a test explicitly targets a mocked GitHub client.

## Product and safety expectations

- Classification and priority are heuristic recommendations, not authoritative labels or decisions.
- The default workflow is read-only. Do not add automatic comments, labels, assignments, or issue state changes without a separate design, explicit opt-in, and tests for permission/error handling.
- Keep human review visible in CLI, MCP, and report output.
- Preserve operation without paid model APIs; optional AI enrichment must not replace deterministic core behavior.
- Never expose GitHub tokens, private issue bodies, or sensitive repository data in logs, fixtures, screenshots, or reports.

## Pull requests

Use the repository PR template. Include the problem, user impact, exact test commands/results, and known limitations. Link the related issue when applicable.

## Security

Follow [SECURITY.md](SECURITY.md) for private vulnerability disclosure. Do not report vulnerabilities in public issues or PRs.
