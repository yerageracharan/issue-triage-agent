import json
from unittest.mock import patch

from issue_triage_agent.analyzer import analyse_issue
from issue_triage_agent.llm import LocalLLM
from issue_triage_agent.models import Issue


def test_local_model_only_adds_summary_and_follow_up():
    result = analyse_issue(Issue(number=4, title="Bug: export crashes", body="The export crashes."))
    original_category = result.category
    original_priority = result.priority

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            payload = {"choices": [{"message": {"content": json.dumps({"summary": "Export fails during use.", "follow_up": "What version are you running?"})}}]}
            return json.dumps(payload).encode()

    llm = LocalLLM("http://localhost:1234/v1", "local-model")
    with patch("issue_triage_agent.llm.urlopen", return_value=FakeResponse()):
        llm.enrich(result)

    assert result.llm_summary == "Export fails during use."
    assert result.llm_follow_up == "What version are you running?"
    assert result.category == original_category
    assert result.priority == original_priority
