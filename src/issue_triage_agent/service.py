"""Reusable application service shared by the CLI and MCP adapters."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .analyzer import analyse_issue
from .models import Issue, TriageResult
from .similarity import attach_duplicate_candidates


def analyse_issues(issues: list[Issue]) -> list[TriageResult]:
    """Analyse issues and attach possible duplicate candidates."""
    results = [analyse_issue(issue) for issue in issues]
    attach_duplicate_candidates(results)
    return results


def result_for_tool(result: TriageResult) -> dict[str, Any]:
    """Return a compact issue result suitable for an MCP tool response."""
    issue = result.issue
    return {
        "number": issue.number,
        "title": issue.title,
        "url": issue.html_url,
        "state": issue.state,
        "author": issue.author,
        "labels_already_on_issue": issue.labels,
        "category": result.category,
        "priority": result.priority,
        "confidence": result.confidence,
        "rationale": result.rationale,
        "suggested_labels_not_applied": result.suggested_labels,
        "missing_information": result.missing_information,
        "possible_duplicates": result.duplicate_candidates,
        "needs_human_attention": result.needs_attention,
        "local_model_summary": result.llm_summary or None,
        "possible_follow_up_question": result.llm_follow_up or None,
    }


def build_triage_payload(repository: str, results: list[TriageResult]) -> dict[str, Any]:
    """Build a compact, structured response for MCP clients and local agents."""
    category_counts = Counter(item.category for item in results)
    priority_counts = Counter(item.priority for item in results)
    attention_count = sum(item.needs_attention for item in results)
    return {
        "repository": repository,
        "read_only": True,
        "issue_count": len(results),
        "needs_human_attention_count": attention_count,
        "category_counts": dict(sorted(category_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "issues": [result_for_tool(item) for item in sorted(results, key=lambda r: (r.priority, r.issue.number))],
        "important_note": (
            "All categories, priorities, completeness checks, and duplicate matches are suggestions. "
            "A human maintainer must verify them. No GitHub data was changed."
        ),
    }


def analyse_single_issue(
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    number: int = 1,
) -> dict[str, Any]:
    """Analyse user-supplied issue text without contacting GitHub."""
    if not title.strip():
        raise ValueError("title must not be empty")
    if number < 0:
        raise ValueError("number must be zero or a positive integer")
    issue = Issue(number=number, title=title.strip(), body=body, labels=labels or [])
    return result_for_tool(analyse_issue(issue))


def triage_policy() -> dict[str, Any]:
    """Describe the rules and the limits of their interpretation."""
    return {
        "categories": {
            "bug": "A crash, error, regression, broken workflow, or incorrect result.",
            "feature": "A requested capability or enhancement.",
            "documentation": "A documentation, README, wording, or typo issue.",
            "question": "A how-to or help request.",
            "other": "No strong category signal was detected.",
        },
        "priorities": {
            "P0": "Potential critical impact signal; investigate immediately, but do not treat as a confirmed incident.",
            "P1": "Potential major workflow, availability, or release impact.",
            "P2": "Default for bugs and unclear reports without a stronger severity signal.",
            "P3": "Default for features, questions, and documentation requests.",
        },
        "confidence": "A heuristic confidence label based on matched repository labels and wording, not a calibrated probability.",
        "duplicates": "Lexical similarity candidates only. A score is not proof that two issues are duplicates.",
        "read_only_boundary": "The agent only reads issue data. It does not post comments, edit issues, apply labels, assign people, or close issues.",
    }
