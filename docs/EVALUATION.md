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
