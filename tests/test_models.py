from issue_triage_agent.models import Issue


def test_github_payload_accepts_missing_or_non_object_user_safely():
    issue = Issue.from_github_payload({
        "number": 12,
        "title": "Issue",
        "labels": [{"name": "bug"}, "needs-triage", None],
        "user": "unexpected",
        "comments": 0,
    })
    assert issue.number == 12
    assert issue.author == "unknown"
    assert issue.labels == ["bug", "needs-triage"]


def test_github_payload_ignores_malformed_optional_text_fields():
    issue = Issue.from_github_payload({
        "number": 1,
        "title": {"unexpected": "object"},
        "body": ["not", "text"],
        "state": None,
        "user": {"login": 42},
    })
    assert issue.title == "Untitled issue"
    assert issue.body == ""
    assert issue.state == "open"
    assert issue.author == "unknown"


def test_github_payload_rejects_invalid_numbers_and_boolean_counts():
    import pytest

    for payload in (
        {"number": True},
        {"number": -1},
        {"number": "2.5"},
        {"number": 1, "comments": True},
        {"number": 1, "comments": -2},
    ):
        with pytest.raises(ValueError):
            Issue.from_github_payload(payload)


def test_github_payload_requires_object():
    import pytest

    with pytest.raises(TypeError, match="payload must be an object"):
        Issue.from_github_payload(None)
