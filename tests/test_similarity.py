from issue_triage_agent.analyzer import analyse_issue
from issue_triage_agent.models import Issue
from issue_triage_agent.similarity import attach_duplicate_candidates, similarity_score


def test_similar_issues_receive_duplicate_candidate():
    first = analyse_issue(Issue(number=1, title="App crashes when exporting CSV", body="Exporting a CSV causes a crash."))
    second = analyse_issue(Issue(number=2, title="CSV export causes the app to crash", body="The application crashes during CSV export."))
    third = analyse_issue(Issue(number=3, title="Add dark mode", body="Please add a dark theme."))
    assert similarity_score(first, second) > similarity_score(first, third)
    results = [first, second, third]
    attach_duplicate_candidates(results)
    assert any(candidate["number"] == 2 for candidate in first.duplicate_candidates)
    assert first.needs_attention is True


def test_no_self_duplicate():
    result = analyse_issue(Issue(number=1, title="A single issue", body="Details."))
    attach_duplicate_candidates([result])
    assert result.duplicate_candidates == []
