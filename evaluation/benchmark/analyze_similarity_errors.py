"""Create a human-review pack for the Phase 3 similarity comparison.

This script does not decide whether two GitHub issues are genuine duplicates.
It highlights validation pairs whose model scores disagree with the dataset's
source labels, while preserving the fact that unlinked pairs are weak negatives.
It uses only the Python standard library and makes no network or model calls.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

METHODS = ("lexical", "bm25", "semantic", "hybrid")
REQUIRED_VALIDATION = {
    "pair_id", "repo", "issue_1_number", "issue_1_title", "issue_1_body",
    "issue_2_number", "issue_2_title", "issue_2_body", "pair_label",
    "label_quality", "sample_type",
}
REQUIRED_SCORES = {
    "split", "pair_id", "repo", "pair_label", "label_quality", "sample_type",
    *(f"{method}_score" for method in METHODS),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"CSV contains no rows: {path}")
    return rows


def _required_columns(rows: list[dict[str, str]], required: set[str], name: str) -> None:
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")


def _number(value: Any, description: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric value for {description}: {value!r}") from exc
    if not math.isfinite(result):
        raise ValueError(f"Non-finite numeric value for {description}: {value!r}")
    return result


def _label(row: dict[str, str]) -> int:
    try:
        label = int(row["pair_label"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid pair_label for {row.get('pair_id', '<unknown>')}") from exc
    if label not in (0, 1):
        raise ValueError(f"pair_label must be 0 or 1 for {row.get('pair_id')}")
    return label


def _thresholds(comparison: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    methods = comparison.get("methods")
    if not isinstance(methods, list):
        raise ValueError("Comparison JSON must contain a 'methods' list")
    for item in methods:
        name = item.get("method")
        if name in METHODS:
            training = item.get("training") or {}
            result[name] = _number(
                training.get("threshold_selected_by_max_training_f1"),
                f"{name} training-selected threshold",
            )
    missing = set(METHODS) - set(result)
    if missing:
        raise ValueError(f"Comparison JSON is missing methods: {sorted(missing)}")
    return result


def _confusion(rows: list[dict[str, str]], method: str, threshold: float) -> dict[str, Any]:
    counts = Counter()
    by_type: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        label = _label(row)
        predicted = _number(row[f"{method}_score"], f"{method}_score") >= threshold
        kind = "TP" if label and predicted else "FN" if label else "FP" if predicted else "TN"
        counts[kind] += 1
        by_type[row.get("sample_type") or "unknown"][kind] += 1

    tp, fp, tn, fn = (counts[key] for key in ("TP", "FP", "TN", "FN"))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and precision + recall else None)
    weak_negative_rates = {}
    for sample_type, group in by_type.items():
        if sample_type in {"hard_lexical", "random_same_repo"}:
            total = group["FP"] + group["TN"]
            weak_negative_rates[sample_type] = {
                "flagged": group["FP"], "not_flagged": group["TN"],
                "total": total, "alert_rate": group["FP"] / total if total else None,
            }
    return {
        "threshold": threshold,
        "pairs": len(rows),
        "confusion_counts": {key: counts[key] for key in ("TP", "FP", "TN", "FN")},
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "weak_negative_breakdown": weak_negative_rates,
        "source_positive_pairs_missed": fn,
        "weak_negative_pairs_flagged_for_review": fp,
    }


def _body_excerpt(value: str, limit: int = 320) -> str:
    text = " ".join((value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _issue_url(repo: str, issue_number: str) -> str:
    """Build a canonical GitHub issue URL from validated dataset identifiers."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"Invalid repository identifier for issue URL: {repo!r}")
    if not re.fullmatch(r"\d+", issue_number):
        raise ValueError(f"Invalid issue number for issue URL: {issue_number!r}")
    return f"https://github.com/{repo}/issues/{issue_number}"


def analyze(
    validation_rows: list[dict[str, str]],
    score_rows: list[dict[str, str]],
    comparison: dict[str, Any],
    top_n: int = 10,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    _required_columns(validation_rows, REQUIRED_VALIDATION, "validation CSV")
    _required_columns(score_rows, REQUIRED_SCORES, "similarity scores CSV")

    validation_by_id: dict[str, dict[str, str]] = {}
    for row in validation_rows:
        pair_id = row["pair_id"]
        if pair_id in validation_by_id:
            raise ValueError(f"Duplicate pair_id in validation CSV: {pair_id}")
        validation_by_id[pair_id] = row
        _label(row)

    validation_scores: dict[str, dict[str, str]] = {}
    for row in score_rows:
        if row["split"] != "validation":
            continue
        pair_id = row["pair_id"]
        if pair_id in validation_scores:
            raise ValueError(f"Duplicate validation score pair_id: {pair_id}")
        validation_scores[pair_id] = row
        _label(row)

    missing_scores = set(validation_by_id) - set(validation_scores)
    extra_scores = set(validation_scores) - set(validation_by_id)
    if missing_scores or extra_scores:
        raise ValueError(
            "Validation/score pair IDs do not match "
            f"(missing scores: {len(missing_scores)}, extra scores: {len(extra_scores)})"
        )

    for pair_id, source in validation_by_id.items():
        scored = validation_scores[pair_id]
        if _label(source) != _label(scored):
            raise ValueError(f"Label mismatch between validation and score rows: {pair_id}")
        if source["repo"].casefold() != scored["repo"].casefold():
            raise ValueError(f"Repository mismatch between validation and score rows: {pair_id}")

    rows = [validation_scores[pair_id] for pair_id in validation_by_id]
    thresholds = _thresholds(comparison)
    per_method = {
        method: _confusion(rows, method, thresholds[method]) for method in METHODS
    }

    prediction_patterns = Counter()
    for row in rows:
        pattern = "".join(
            "1" if _number(row[f"{method}_score"], f"{method}_score") >= thresholds[method] else "0"
            for method in METHODS
        )
        prediction_patterns[pattern] += 1

    # A weak-negative alert is not assumed to be a true false positive.
    # A source-positive miss is not assumed to be a confirmed product failure.
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for method in METHODS:
        flagged = sorted(
            (r for r in rows if _label(r) == 0 and
             _number(r[f"{method}_score"], f"{method}_score") >= thresholds[method]),
            key=lambda r: _number(r[f"{method}_score"], f"{method}_score"), reverse=True,
        )[:top_n]
        missed = sorted(
            (r for r in rows if _label(r) == 1 and
             _number(r[f"{method}_score"], f"{method}_score") < thresholds[method]),
            key=lambda r: _number(r[f"{method}_score"], f"{method}_score"),
        )[:top_n]
        for reason, group in (("weak_negative_alert", flagged), ("source_positive_low_score", missed)):
            for score_row in group:
                pair_id = score_row["pair_id"]
                key = (reason, pair_id)
                item = selected.setdefault(key, {
                    "review_reason": reason,
                    "pair_id": pair_id,
                    "triggered_by": set(),
                })
                item["triggered_by"].add(method)

    review_rows: list[dict[str, str]] = []
    for (reason, pair_id), selected_item in sorted(selected.items()):
        source = validation_by_id[pair_id]
        scores = validation_scores[pair_id]
        result: dict[str, str] = {
            "review_reason": reason,
            "triggered_by": ";".join(m for m in METHODS if m in selected_item["triggered_by"]),
            "pair_id": pair_id,
            "repo": source["repo"],
            "issue_1_number": source["issue_1_number"],
            "issue_1_url": _issue_url(source["repo"], source["issue_1_number"]),
            "issue_1_title": source["issue_1_title"],
            "issue_1_body_excerpt": _body_excerpt(source["issue_1_body"]),
            "issue_2_number": source["issue_2_number"],
            "issue_2_url": _issue_url(source["repo"], source["issue_2_number"]),
            "issue_2_title": source["issue_2_title"],
            "issue_2_body_excerpt": _body_excerpt(source["issue_2_body"]),
            "pair_label": source["pair_label"],
            "label_quality": source["label_quality"],
            "sample_type": source["sample_type"],
            "human_adjudication": "",
            "reviewer_notes": "",
            "reviewer_confidence": "",
        }
        for method in METHODS:
            result[f"{method}_score"] = f"{_number(scores[f'{method}_score'], method):.8f}"
            result[f"{method}_threshold"] = f"{thresholds[method]:.8f}"
            result[f"{method}_predicted_match"] = str(
                _number(scores[f"{method}_score"], method) >= thresholds[method]
            ).lower()
        review_rows.append(result)

    summary = {
        "experiment": "phase_4_validation_error_analysis",
        "split": "validation",
        "pairs": len(rows),
        "repositories": len({row["repo"].casefold() for row in validation_rows}),
        "thresholds_selected_on_training": thresholds,
        "methods": per_method,
        "prediction_pattern_order": list(METHODS),
        "prediction_patterns": dict(sorted(prediction_patterns.items())),
        "review_pack_rows": len(review_rows),
        "review_pack_rules": {
            "weak_negative_alert": f"Top {top_n} highest-scoring weak-negative pairs at each method's training-selected threshold.",
            "source_positive_low_score": f"Bottom {top_n} scoring source-positive pairs below each method's training-selected threshold.",
            "deduplication": "Same pair and review reason are included once; triggered_by lists every method that selected the pair.",
            "human_adjudication": "Blank field for a reviewer. The script does not decide whether the pair is a true duplicate.",
        },
        "warnings": [
            "Source-positive pairs are recorded duplicate links, not independent human re-labelling.",
            "Unlinked weak negatives are not verified non-duplicates; an alerted pair may be a missing source annotation.",
            "A source-positive pair below a threshold is a low-scoring pair in this benchmark, not proof of a live product miss.",
            "All thresholds were selected on training data and applied unchanged to validation.",
            "This analysis does not use the held-out test split or change the production detector.",
        ],
    }
    return summary, review_rows


def _fmt(value: Any) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def write_outputs(output_dir: Path, summary: dict[str, Any], review_rows: list[dict[str, str]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "error_analysis_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )

    review_fields = list(review_rows[0]) if review_rows else [
        "review_reason", "triggered_by", "pair_id", "repo",
        "issue_1_number", "issue_1_url", "issue_1_title", "issue_1_body_excerpt",
        "issue_2_number", "issue_2_url", "issue_2_title", "issue_2_body_excerpt",
        "pair_label", "label_quality", "sample_type",
        "lexical_score", "lexical_threshold", "lexical_predicted_match",
        "bm25_score", "bm25_threshold", "bm25_predicted_match",
        "semantic_score", "semantic_threshold", "semantic_predicted_match",
        "hybrid_score", "hybrid_threshold", "hybrid_predicted_match",
        "human_adjudication", "reviewer_notes", "reviewer_confidence",
    ]
    with (output_dir / "review_examples.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=review_fields)
        writer.writeheader()
        writer.writerows(review_rows)

    # This is the file to give to reviewers. It intentionally omits source labels,
    # model scores, threshold decisions, and the reason a row was selected.
    blind_fields = [
        "pair_id", "repo",
        "issue_1_number", "issue_1_url", "issue_1_title", "issue_1_body_excerpt",
        "issue_2_number", "issue_2_url", "issue_2_title", "issue_2_body_excerpt",
        "human_adjudication", "reviewer_confidence", "reviewer_notes",
    ]
    blind_rows = [
        {field: row.get(field, "") for field in blind_fields}
        for row in review_rows
    ]
    with (output_dir / "reviewer_blind.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=blind_fields)
        writer.writeheader()
        writer.writerows(blind_rows)

    guide = """# Human review guide

## Use this file for independent review

Open reviewer_blind.csv. It contains issue links, titles and shortened descriptions, but intentionally hides:
- Whether the source dataset marked the pair as a duplicate.
- Which model selected the pair.
- Model similarity scores and thresholds.
- Whether it was selected as a weak-negative alert or a source-positive low-score case.

This reduces the chance that the dataset label or model scores influence the reviewer's judgement.

## Review each pair

1. Open both GitHub issue links. Read the complete descriptions and, where available, the discussion and linked pull requests.
2. Decide whether the two reports describe the same underlying defect or request, not merely the same project, feature area, error family, or component.
3. Record one value in human_adjudication:
   - same_underlying_issue — substantially the same bug, failure, or feature request.
   - related_but_distinct — connected topic or component, but a different underlying problem or request.
   - different_issues — unrelated problems.
   - insufficient_context — the available reports do not support a confident decision.
4. Set reviewer_confidence to high, medium, or low.
5. Explain the evidence in reviewer_notes. Mention shared reproduction steps, root cause, environment, stack trace, or requested behaviour where relevant.

## Important judgement rules

- Do not call two issues duplicates only because their titles or error messages are identical. Repeated templates and boilerplate can describe different failures.
- Do not call two issues duplicates only because they mention the same subsystem or feature.
- A follow-up, documentation request, workaround, or feature request can be related without being a duplicate.
- A source-linked pair is not automatically correct; the original dataset relationship can be noisy.
- An unlinked pair is not automatically distinct; it may be a duplicate that the source dataset failed to link.
- Use insufficient_context rather than guessing from a short excerpt.

## After review

Keep the blind CSV unchanged as the original reviewer input. Store completed copies separately and preserve the original pair_id values so decisions can be merged back to review_examples.csv. For stronger evidence, have two reviewers independently label a subset and resolve disagreements before using these judgements in metrics.

The review set comes from the validation split. Do not use these judgements to tune repeatedly on the held-out test split. The benchmark is based on source annotations and weak unlinked negatives, so even human review of 56 selected pairs does not establish production accuracy by itself.
"""
    (output_dir / "HUMAN_REVIEW_GUIDE.md").write_text(guide, encoding="utf-8")

    lines = [
        "# Phase 4 validation error analysis", "",
        f"This report examines **{summary['pairs']:,} validation pairs** across **{summary['repositories']} repositories**.",
        "It does not use the held-out test split and does not change the production detector.", "",
        "## Results at training-selected thresholds", "",
        "| Method | Threshold | TP | Weak-negative alerts | TN | Source-positive low scores | Precision | Recall | F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method in METHODS:
        data = summary["methods"][method]
        counts = data["confusion_counts"]
        lines.append(
            f"| {method} | {data['threshold']:.4f} | {counts['TP']} | {counts['FP']} | "
            f"{counts['TN']} | {counts['FN']} | {_fmt(data['precision'])} | "
            f"{_fmt(data['recall'])} | {_fmt(data['f1'])} |"
        )
    lines += ["", "## Weak-negative breakdown", "",
              "The alert rate below is the share of sampled unlinked pairs that crossed a method's threshold. "
              "It is **not a verified false-positive rate** because these negatives were not independently checked.", "",
              "| Method | Sample type | Flagged for review | Not flagged | Total | Alert rate |",
              "|---|---|---:|---:|---:|---:|"]
    for method in METHODS:
        breakdown = summary["methods"][method]["weak_negative_breakdown"]
        for sample_type in ("hard_lexical", "random_same_repo"):
            if sample_type in breakdown:
                item = breakdown[sample_type]
                lines.append(
                    f"| {method} | {sample_type} | {item['flagged']} | {item['not_flagged']} | "
                    f"{item['total']} | {_fmt(item['alert_rate'])} |"
                )
    lines += ["", "## Where methods disagree", "",
              "The following four-character patterns show whether each method crossed its own threshold. "
              "The order is lexical, BM25, semantic, hybrid; 1 means the pair was flagged for review.", "",
              "| Pattern | Pairs |", "|---|---:|"]
    for pattern, count in summary["prediction_patterns"].items():
        lines.append(f"| {pattern} | {count} |")
    lines += ["", "## Human review pack", "",
              f"review_examples.csv contains {len(review_rows)} examples plus all four model scores, source labels and threshold decisions for analysis.",
              "reviewer_blind.csv contains the same issue pairs with canonical GitHub links, but hides source labels and model information so a reviewer can judge independently.",
              "HUMAN_REVIEW_GUIDE.md defines the labels, confidence scale and review procedure.", "",
              "## Interpretation limits", ""]
    lines.extend(f"- {warning}" for warning in summary["warnings"])
    (output_dir / "error_analysis_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-csv", type=Path, required=True)
    parser.add_argument("--scores-csv", type=Path, required=True)
    parser.add_argument("--comparison-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/benchmark/generated/phase4"))
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()
    try:
        validation = read_csv(args.validation_csv)
        scores = read_csv(args.scores_csv)
        comparison = json.loads(args.comparison_json.read_text(encoding="utf-8"))
        summary, review_rows = analyze(validation, scores, comparison, args.top_n)
        write_outputs(args.output_dir, summary, review_rows)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error analysis failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "output_dir": str(args.output_dir),
        "validation_pairs": summary["pairs"],
        "review_pack_rows": summary["review_pack_rows"],
        "methods": {
            method: {
                "weak_negative_alerts": summary["methods"][method]["weak_negative_pairs_flagged_for_review"],
                "source_positive_low_scores": summary["methods"][method]["source_positive_pairs_missed"],
                "precision": summary["methods"][method]["precision"],
                "recall": summary["methods"][method]["recall"],
                "f1": summary["methods"][method]["f1"],
            }
            for method in METHODS
        },
    }, indent=2))
    print("Caution: weak negatives are not human-confirmed non-duplicates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
