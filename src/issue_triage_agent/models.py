"""Typed data structures used by the triage pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a non-negative integer") from exc
    if parsed < 0 or str(parsed) != str(value).strip():
        raise ValueError(f"{field_name} must be a non-negative integer")
    return parsed


@dataclass(slots=True)
class Issue:
    number: int
    title: str
    body: str = ""
    state: str = "open"
    html_url: str = ""
    labels: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    comments: int = 0
    author: str = "unknown"

    @classmethod
    def from_github_payload(cls, payload: dict[str, Any]) -> "Issue":
        """Convert GitHub's issue JSON into a safe, typed model.

        Unexpected nested payload shapes are handled conservatively. Numeric
        identifiers/counters are validated because silent coercion can corrupt
        sorting and reporting.
        """
        if not isinstance(payload, dict):
            raise TypeError("GitHub issue payload must be an object")

        number = _non_negative_int(payload.get("number", 0), "issue number")
        comments = _non_negative_int(payload.get("comments", 0) or 0, "comment count")

        raw_labels = payload.get("labels")
        labels: list[str] = []
        if isinstance(raw_labels, list):
            for item in raw_labels:
                label = item.get("name") if isinstance(item, dict) else item if isinstance(item, str) else None
                if isinstance(label, str) and label.strip() and label.strip() not in labels:
                    labels.append(label.strip())

        raw_user = payload.get("user")
        author = _text(raw_user.get("login"), "unknown") if isinstance(raw_user, dict) else "unknown"

        return cls(
            number=number,
            title=_text(payload.get("title"), "Untitled issue").strip() or "Untitled issue",
            body=_text(payload.get("body"), ""),
            state=_text(payload.get("state"), "open") or "open",
            html_url=_text(payload.get("html_url"), ""),
            labels=labels,
            created_at=_text(payload.get("created_at"), ""),
            updated_at=_text(payload.get("updated_at"), ""),
            comments=comments,
            author=author or "unknown",
        )


@dataclass(slots=True)
class TriageResult:
    issue: Issue
    category: str
    priority: str
    confidence: str
    rationale: list[str]
    suggested_labels: list[str]
    missing_information: list[str]
    duplicate_candidates: list[dict[str, Any]] = field(default_factory=list)
    needs_attention: bool = False
    llm_summary: str = ""
    llm_follow_up: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
