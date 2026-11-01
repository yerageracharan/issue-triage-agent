from issue_triage_agent.models import Issue
from issue_triage_agent.service import analyse_issues, analyse_single_issue, build_triage_payload


def test_service_builds_structured_summary():
    issues = [
        Issue(number=2, title="Feature request: add CSV export", body="Please add CSV export for reports."),
        Issue(number=3, title="CSV export crashes", body="The CSV export crashes with an exception."),
    ]
    results = analyse_issues(issues)
    payload = build_triage_payload("octocat/demo", results)
    assert payload["read_only"] is True
    assert payload["issue_count"] == 2
    assert payload["priority_counts"]
    assert all("suggested_labels_not_applied" in issue for issue in payload["issues"])


def test_single_issue_analysis_does_not_need_network():
    result = analyse_single_issue("Crash when exporting", "The app crashes when exporting a report.")
    assert result["category"] == "bug"
    assert result["priority"] in {"P0", "P1", "P2", "P3"}


def test_single_issue_rejects_blank_title():
    try:
        analyse_single_issue("  ")
    except ValueError as exc:
        assert "title" in str(exc)
    else:
        raise AssertionError("blank title should be rejected")
