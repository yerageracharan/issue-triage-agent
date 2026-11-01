import json

from issue_triage_agent.analyzer import analyse_issue
from issue_triage_agent.models import Issue
from issue_triage_agent.report import render_markdown, write_reports


def test_report_contains_explanations_and_read_only_notice(tmp_path):
    results = [analyse_issue(Issue(number=7, title="Bug: app crashes", body="It crashes on startup."))]
    markdown = render_markdown("octocat/hello-world", results)
    assert "# Issue triage report" in markdown
    assert "Suggested labels (not applied)" in markdown
    assert "It does not post comments" in markdown

    md_path, json_path = write_reports("octocat/hello-world", results, tmp_path)
    assert md_path.exists() and json_path.exists()
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["issue_count"] == 1
    assert parsed["results"][0]["issue"]["number"] == 7


def test_report_escapes_untrusted_issue_title():
    issue = Issue(number=8, title="Broken ](javascript:alert(1)) | export", body="The export fails.")
    markdown = render_markdown("octocat/hello-world", [analyse_issue(issue)])
    assert r"\]" in markdown
    assert r"\|" in markdown
    assert "](javascript:alert(1))" not in markdown


def test_report_rejects_non_github_issue_links():
    issue = Issue(number=9, title="Unsafe link", body="Details", html_url="javascript:alert(1)")
    markdown = render_markdown("octocat/hello-world", [analyse_issue(issue)])
    assert "javascript:" not in markdown
    assert "[#9](" not in markdown
