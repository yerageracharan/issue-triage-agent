from issue_triage_agent.cli import run


def test_offline_cli_writes_reports(tmp_path):
    code = run([
        "example/demo",
        "--input-json", "examples/sample_issues.json",
        "--output", str(tmp_path),
        "--no-llm",
    ])
    assert code == 0
    assert (tmp_path / "triage-report.md").exists()
    assert (tmp_path / "triage-report.json").exists()


def test_cli_rejects_invalid_limit():
    assert run(["octocat/hello", "--limit", "501"]) == 2
