"""Lightweight duplicate-candidate detection without external dependencies."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import TriageResult

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "i", "in", "is", "it",
    "of", "on", "or", "our", "the", "this", "to", "we", "with", "you", "your", "when", "then",
}


def _normalise_token(token: str) -> str:
    # Small, dependency-free suffix normalisation catches common forms such as
    # "crashes"/"crash" and "exporting"/"export" without claiming semantic understanding.
    if len(token) > 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return token[:-3]
    if len(token) > 4 and token.endswith("ed"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es") and token[-3] in "sxzh":
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    return {
        _normalise_token(token)
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def similarity_score(left: TriageResult, right: TriageResult) -> float:
    left_title = left.issue.title.casefold().strip()
    right_title = right.issue.title.casefold().strip()
    title_score = 0.65 * _jaccard(_tokens(left_title), _tokens(right_title)) + 0.35 * SequenceMatcher(None, left_title, right_title).ratio()

    left_body = _tokens(left.issue.body[:3000])
    right_body = _tokens(right.issue.body[:3000])
    body_score = _jaccard(left_body, right_body)
    same_category_bonus = 0.05 if left.category == right.category else 0.0
    return min(1.0, 0.8 * title_score + 0.2 * body_score + same_category_bonus)


def attach_duplicate_candidates(results: list[TriageResult], threshold: float = 0.48, max_candidates: int = 3) -> None:
    """Attach likely duplicate candidates, keeping scores explicitly heuristic."""
    for index, result in enumerate(results):
        candidates: list[dict[str, object]] = []
        for other_index, other in enumerate(results):
            if index == other_index:
                continue
            score = similarity_score(result, other)
            if score >= threshold:
                candidates.append({
                    "number": other.issue.number,
                    "title": other.issue.title,
                    "url": other.issue.html_url,
                    "similarity": round(score, 3),
                })
        candidates.sort(key=lambda item: float(item["similarity"]), reverse=True)
        result.duplicate_candidates = candidates[:max_candidates]
        if result.duplicate_candidates:
            result.needs_attention = True
