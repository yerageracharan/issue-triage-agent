"""Typed data structures used by the triage pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
        labels = payload.get("labels") or []
        return cls(
            number=int(payload.get("number", 0)),
            title=str(payload.get("title") or "Untitled issue"),
            body=str(payload.get("body") or ""),
            state=str(payload.get("state") or "open"),
            html_url=str(payload.get("html_url") or ""),
            labels=[str(item.get("name", "")) for item in labels if isinstance(item, dict)],
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
            comments=int(payload.get("comments") or 0),
            author=str((payload.get("user") or {}).get("login") or "unknown"),
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
        result = asdict(self)
        return result
