"""Deterministic issue classification, prioritisation, and completeness checks."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import Issue, TriageResult


_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bug", ("bug", "crash", "crashes", "exception", "traceback", "regression", "not working", "does not work", "doesn't work", "broken", "fails", "failure", "incorrect result", "unexpected behavior", "unexpected behaviour")),
    ("feature", ("feature request", "enhancement", "would be nice", "please add", "add support", "support for", "new feature", "proposal")),
    ("documentation", ("documentation", "docs", "readme", "typo", "spelling", "clarify the", "unclear instructions")),
    ("question", ("how do i", "how can i", "how to", "question", "help wanted", "is it possible")),
)

_PRIORITY_LABELS = {
    "p0": "P0", "priority: critical": "P0", "severity: critical": "P0", "critical": "P0", "blocker": "P0",
    "p1": "P1", "priority: high": "P1", "severity: high": "P1", "high priority": "P1",
    "p2": "P2", "priority: medium": "P2", "medium priority": "P2",
    "p3": "P3", "priority: low": "P3", "low priority": "P3",
}

_P0_PHRASES = (
    "data loss", "data corruption", "remote code execution", "security vulnerability",
    "production is down", "complete outage", "all users are affected", "cannot access any data",
)
_P1_PHRASES = (
    "application crashes", "app crashes", "cannot log in", "can't log in", "unable to log in",
    "blocks deployment", "blocks release", "cannot start", "service unavailable", "major regression",
)


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match complete words/phrases, not accidental substrings such as 'bug' in 'debugger'."""
    pattern = rf"(?<![a-z0-9-]){re.escape(phrase)}(?![a-z0-9-])"
    return re.search(pattern, text) is not None


def classify_category(issue: Issue) -> tuple[str, str, list[str]]:
    text = _normalise(f"{issue.title}\n{issue.body}")
    labels = {label.casefold().strip() for label in issue.labels}
    label_categories = {
        "bug": "bug", "type: bug": "bug", "feature": "feature",
        "enhancement": "feature", "feature request": "feature", "type: feature": "feature",
        "documentation": "documentation", "docs": "documentation",
        "type: documentation": "documentation", "question": "question",
        "type: question": "question",
    }
    for label in sorted(labels):
        if label in label_categories:
            category = label_categories[label]
            return category, "high", [f"Matched existing label: {label}"]
    for category, phrases in _CATEGORY_RULES:
        matched = [phrase for phrase in phrases if _contains_phrase(text, phrase)]
        if matched:
            confidence = "high" if len(matched) > 1 or matched[0] in text[: len(issue.title) + 1] else "medium"
            return category, confidence, [f"Matched wording: {', '.join(matched[:3])}"]
    return "other", "low", ["No strong category signal was found; manual review is recommended."]


def assign_priority(issue: Issue, category: str) -> tuple[str, list[str]]:
    labels = {label.casefold().strip() for label in issue.labels}
    for label, priority in _PRIORITY_LABELS.items():
        if label in labels:
            return priority, [f"Existing repository label indicates {priority} priority."]

    text = _normalise(f"{issue.title}\n{issue.body}")
    if any(_contains_phrase(text, phrase) for phrase in _P0_PHRASES):
        return "P0", ["Potential severe impact language detected; verify impact before escalation."]
    if any(_contains_phrase(text, phrase) for phrase in _P1_PHRASES):
        return "P1", ["Potentially release-blocking or major workflow impact language detected."]
    if category in {"question", "documentation"}:
        return "P3", [f"{category.title()} issues are assigned a provisional low priority."]
    if category == "feature":
        return "P3", ["Feature requests default to P3 until impact and demand are assessed."]
    if category == "bug":
        return "P2", ["Bug report defaults to P2 because no explicit severity signal was found."]
    return "P2", ["No explicit severity signal was found; P2 is a provisional default."]


def check_missing_information(issue: Issue, category: str) -> list[str]:
    body = _normalise(issue.body)
    missing: list[str] = []
    if not body:
        return ["A description of the issue is missing."]

    if category == "bug":
        checks = (
            (("steps to reproduce", "steps", "reproduction", "repro steps"), "Steps to reproduce"),
            (("expected behavior", "expected result", "should happen"), "Expected behaviour"),
            (("actual behavior", "actual result", "instead"), "Actual behaviour"),
            (("environment", "operating system", "os:", "python version", "version:"), "Environment and version details"),
        )
        for phrases, description in checks:
            if not any(phrase in body for phrase in phrases):
                missing.append(description)
        if not any(marker in body for marker in ("```", "traceback", "error:", "exception")):
            missing.append("A relevant error message, log, or minimal example (when available)")
    elif category == "feature":
        if not any(p in body for p in ("use case", "i want", "i need", "user story", "problem")):
            missing.append("The user problem or use case")
        if not any(p in body for p in ("proposed solution", "solution", "it would", "should allow", "would like")):
            missing.append("A proposed outcome or expected behaviour")
    elif category == "documentation":
        if not any(p in body for p in ("http://", "https://", "file:", "section", "line ", "page ")):
            missing.append("The affected page, file, section, or URL")
        if not any(p in body for p in ("incorrect", "unclear", "missing", "outdated", "should say", "typo")):
            missing.append("What is incorrect, unclear, or missing")
    elif category == "question":
        if len(body.split()) < 12:
            missing.append("More context about the goal and what has already been tried")
    else:
        if len(body.split()) < 12:
            missing.append("More context describing the request and its impact")

    return missing


def _suggest_labels(category: str, priority: str, missing: Iterable[str]) -> list[str]:
    labels = [f"type: {category}", f"priority: {priority.casefold()}"]
    if list(missing):
        labels.append("needs-triage")
    return labels


def analyse_issue(issue: Issue) -> TriageResult:
    category, confidence, category_reasons = classify_category(issue)
    priority, priority_reasons = assign_priority(issue, category)
    missing = check_missing_information(issue, category)
    rationale = category_reasons + priority_reasons
    return TriageResult(
        issue=issue,
        category=category,
        priority=priority,
        confidence=confidence,
        rationale=rationale,
        suggested_labels=_suggest_labels(category, priority, missing),
        missing_information=missing,
        needs_attention=bool(missing) or confidence == "low" or priority in {"P0", "P1"},
    )
