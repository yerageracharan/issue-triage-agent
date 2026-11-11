from issue_triage_agent.analyzer import analyse_issue
from issue_triage_agent.models import Issue


def make_issue(title, body="", labels=None, number=1):
    return Issue(number=number, title=title, body=body, labels=labels or [])


def test_existing_bug_label_wins_over_wording():
    result = analyse_issue(make_issue("How can I improve this?", "More detail", ["bug"]))
    assert result.category == "bug"
    assert result.confidence == "high"


def test_crash_is_classified_as_bug():
    result = analyse_issue(make_issue("Application crashes on startup", "The app crashes every time."))
    assert result.category == "bug"
    assert result.priority == "P1"


def test_feature_request_is_classified_and_low_priority_by_default():
    result = analyse_issue(make_issue("Feature request: add CSV export", "Please add support for CSV export."))
    assert result.category == "feature"
    assert result.priority == "P3"


def test_security_phrase_is_flagged_as_provisional_p0():
    result = analyse_issue(make_issue("Potential security vulnerability", "A security vulnerability may expose data."))
    assert result.priority == "P0"
    assert result.needs_attention is True


def test_bug_report_checks_required_context():
    result = analyse_issue(make_issue("Bug: export fails", "The export is broken."))
    assert "Steps to reproduce" in result.missing_information
    assert "Expected behaviour" in result.missing_information
    assert "Actual behaviour" in result.missing_information


def test_empty_issue_body_is_flagged():
    result = analyse_issue(make_issue("A vague request", ""))
    assert result.missing_information == ["A description of the issue is missing."]
    assert result.needs_attention is True


def test_existing_priority_label_is_respected():
    result = analyse_issue(make_issue("Bug report", "It crashes.", ["bug", "priority: high"]))
    assert result.priority == "P1"


def test_debugger_word_does_not_trigger_bug_category():
    result = analyse_issue(make_issue("Debugger output is confusing", "The debugger prints a confusing stack view."))
    assert result.category == "other"
    assert result.priority == "P2"


def test_bug_phrase_still_matches_as_a_complete_word():
    result = analyse_issue(make_issue("Bug: debugger crashes", "The debugger crashes on startup."))
    assert result.category == "bug"
    assert result.priority == "P1"


def test_debugger_does_not_trigger_p0_security_phrase():
    result = analyse_issue(make_issue("Debugging security settings", "The debugger output mentions a security vulnerability scanner."))
    assert result.priority == "P0"


def test_unrelated_substrings_do_not_trigger_crash_priority():
    result = analyse_issue(make_issue("Crash-course documentation", "This is a crash-course on debugging."))
    assert result.category == "documentation"
    assert result.priority == "P3"
