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


def test_duplicate_candidate_limits_are_validated():
    import pytest

    sample = analyse_issue(Issue(number=1, title="Bug: login fails", body="Cannot log in."))
    for threshold in (-0.1, 1.1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="threshold"):
            attach_duplicate_candidates([sample], threshold=threshold)
    for limit in (-1, 51, 1.5, True):
        with pytest.raises(ValueError, match="max_candidates"):
            attach_duplicate_candidates([sample], max_candidates=limit)


def test_zero_duplicate_candidate_limit_is_allowed():
    sample = analyse_issue(Issue(number=1, title="Bug: login fails", body="Cannot log in."))
    attach_duplicate_candidates([sample], max_candidates=0)
    assert sample.duplicate_candidates == []


def test_duplicate_candidates_requires_triage_results():
    import pytest

    with pytest.raises(TypeError, match="TriageResult"):
        attach_duplicate_candidates([{"issue": 1}])
