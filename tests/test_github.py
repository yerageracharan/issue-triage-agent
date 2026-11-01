import json
from unittest.mock import patch

import pytest

from issue_triage_agent.github import parse_repository, fetch_issues


def test_parse_repository_short_form():
    assert parse_repository("octocat/hello-world") == ("octocat", "hello-world")


def test_parse_repository_url_with_git_suffix():
    assert parse_repository("https://github.com/octocat/hello-world.git") == ("octocat", "hello-world")


def test_reject_non_github_url():
    with pytest.raises(ValueError):
        parse_repository("https://example.com/octocat/hello-world")


def test_fetch_issues_skips_pull_requests():
    payload = [
        {"number": 1, "title": "Issue", "body": "Details", "labels": [], "user": {"login": "dev"}},
        {"number": 2, "title": "PR", "body": "Changes", "labels": [], "pull_request": {"url": "https://api.github.com"}},
    ]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    with patch("issue_triage_agent.github.urlopen", return_value=FakeResponse()):
        result = fetch_issues("octocat/hello-world", limit=10)
    assert len(result) == 1
    assert result[0].number == 1
    assert result[0].author == "dev"
