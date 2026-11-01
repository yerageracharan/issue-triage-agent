"""Baseline evaluation for the unchanged Issue Triage Agent duplicate heuristic."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from issue_triage_agent.analyzer import analyse_issue
from issue_triage_agent.models import Issue
from issue_triage_agent.similarity import similarity_score

DEFAULT_THRESHOLD = 0.48


def read_pairs(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "pair_id", "repo", "issue_1_number", "issue_1_title", "issue_1_body",
        "issue_2_number", "issue_2_title", "issue_2_body", "pair_label",
        "label_quality", "sample_type",
    }
    if not rows:
        raise ValueError(f"No benchmark pairs found in {path}")
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"Missing benchmark columns: {', '.join(missing)}")
    return rows


def score_pair(row: dict[str, str]) -> tuple[float, str, str]:
    """Reuse the production category rules and similarity function unchanged."""
    left = Issue(int(row["issue_1_number"]), row["issue_1_title"], row["issue_1_body"])
    right = Issue(int(row["issue_2_number"]), row["issue_2_title"], row["issue_2_body"])
    left_result, right_result = analyse_issue(left), analyse_issue(right)
    return similarity_score(left_result, right_result), left_result.category, right_result.category


def divide(a: float, b: float) -> float | None:
    return a / b if b else None


def classification_metrics(labels: list[int], predictions: list[int]) -> dict[str, Any]:
    tp = sum(y == 1 and p == 1 for y, p in zip(labels, predictions))
    fp = sum(y == 0 and p == 1 for y, p in zip(labels, predictions))
    tn = sum(y == 0 and p == 0 for y, p in zip(labels, predictions))
    fn = sum(y == 1 and p == 0 for y, p in zip(labels, predictions))
    precision, recall = divide(tp, tp + fp), divide(tp, tp + fn)
    specificity = divide(tn, tn + fp)
    f1 = divide(2 * precision * recall, precision + recall) if precision is not None and recall is not None else None
    return {
        "counts": {"true_positive": tp, "false_positive": fp, "true_negative": tn, "false_negative": fn},
        "accuracy": divide(tp + tn, len(labels)),
        "precision": precision, "recall": recall, "f1": f1, "specificity": specificity,
        "balanced_accuracy": (recall + specificity) / 2 if recall is not None and specificity is not None else None,
    }


def roc_auc(labels: list[int], scores: list[float]) -> float | None:
    """Mann-Whitney ROC AUC; tied scores receive average ranks."""
    positives, negatives = sum(labels), len(labels) - sum(labels)
    if not positives or not negatives:
        return None
    ordered = sorted(zip(scores, labels))
    rank_sum, rank, i = 0.0, 1, 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        average_rank = (rank + rank + j - i - 1) / 2
        rank_sum += average_rank * sum(y for _, y in ordered[i:j])
        rank += j - i
        i = j
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def average_precision(labels: list[int], scores: list[float]) -> float | None:
    positives = sum(labels)
    if not positives:
        return None
    ordered = sorted(zip(scores, labels), reverse=True)
    seen = found = i = 0
    old_recall = result = 0.0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]:
            j += 1
        group = [y for _, y in ordered[i:j]]
        seen += len(group)
        found += sum(group)
        recall = found / positives
        result += (recall - old_recall) * (found / seen)
        old_recall = recall
        i = j
    return result


def distribution(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"minimum": None, "median": None, "maximum": None, "mean": None}
    return {"minimum": min(values), "median": median(values), "maximum": max(values), "mean": sum(values) / len(values)}


def evaluate_rows(
    rows: list[dict[str, str]], *, threshold: float = DEFAULT_THRESHOLD,
    dataset_manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scored = []
    for row in rows:
        label = int(row["pair_label"])
        if label not in (0, 1):
            raise ValueError(f"Unexpected pair label {label} for {row.get('pair_id')}")
        score, category_1, category_2 = score_pair(row)
        scored.append({
            "pair_id": row["pair_id"], "repo": row["repo"],
            "issue_1_number": row["issue_1_number"], "issue_2_number": row["issue_2_number"],
            "pair_label": label, "label_quality": row["label_quality"], "sample_type": row["sample_type"],
            "similarity_score": score, "predicted_duplicate_at_threshold": int(score >= threshold),
            "issue_1_category": category_1, "issue_2_category": category_2,
        })

    labels = [int(r["pair_label"]) for r in scored]
    scores = [float(r["similarity_score"]) for r in scored]
    predictions = [int(r["predicted_duplicate_at_threshold"]) for r in scored]
    metrics = classification_metrics(labels, predictions)
    negative_breakdown = {}
    for kind in sorted({str(r["sample_type"]) for r in scored if r["pair_label"] == 0}):
        subset = [r for r in scored if r["pair_label"] == 0 and r["sample_type"] == kind]
        flagged = sum(int(r["predicted_duplicate_at_threshold"]) for r in subset)
        negative_breakdown[kind] = {
            "pairs": len(subset), "flagged_as_duplicate": flagged,
            "flagged_rate": divide(flagged, len(subset)),
            "score_distribution": distribution([float(r["similarity_score"]) for r in subset]),
        }

    manifest = dataset_manifest or {}
    metrics.update({
        "evaluation_name": "unchanged_current_heuristic_pairwise_baseline",
        "threshold": threshold, "pairs_evaluated": len(scored),
        "positive_pairs": sum(labels), "weak_negative_pairs": len(labels) - sum(labels),
        "repositories": len({str(r["repo"]).casefold() for r in scored}),
        "label_counts": dict(Counter(str(r["label_quality"]) for r in scored)),
        "roc_auc": roc_auc(labels, scores), "average_precision": average_precision(labels, scores),
        "negative_sample_breakdown": negative_breakdown,
        "score_distribution": {
            "source_annotated_positive": distribution([s for s, y in zip(scores, labels) if y == 1]),
            "weak_unverified_negative": distribution([s for s, y in zip(scores, labels) if y == 0]),
        },
        "dataset": {
            "id": manifest.get("dataset_id"), "revision": manifest.get("dataset_revision"),
            "licence": manifest.get("dataset_license"), "split": "test",
            "repository_split_leakage_free": manifest.get("repository_split_leakage_free"),
        },
        "method": {
            "scoring_function": "issue_triage_agent.similarity.similarity_score",
            "category_function": "issue_triage_agent.analyzer.analyse_issue",
            "threshold_source": "default in attach_duplicate_candidates(..., threshold=0.48)",
            "body_character_limit_in_similarity": 3000,
            "category_labels": "Inferred by current rules because source rows have no GitHub labels.",
            "llm_used": False, "detector_modified": False,
        },
        "interpretation_warnings": [
            "Positive labels are source-annotated duplicates, not independently re-labelled here.",
            "Negative labels are weak unlinked candidates, not human-confirmed non-duplicates; some may be undiscovered duplicates.",
            "Metrics measure agreement with benchmark labels, not definitive real-world accuracy.",
            "This pairwise test does not measure live repository top-three retrieval, latency, or API cost.",
        ],
    })
    return metrics, scored


def write_outputs(directory: Path, metrics: dict[str, Any], scored: list[dict[str, Any]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "baseline_metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    with (directory / "baseline_scores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(scored[0]))
        writer.writeheader()
        writer.writerows(scored)

    pct = lambda value: "n/a" if value is None else f"{value * 100:.2f}%"
    c = metrics["counts"]
    lines = [
        "# Phase 2 baseline evaluation", "",
        f"The unchanged detector scored {metrics['pairs_evaluated']:,} pairs from {metrics['repositories']:,} held-out repositories at threshold {metrics['threshold']:.2f}.",
        "",
        "**Caution:** positives are source-annotated; negatives are weak, unverified unlinked pairs. Results measure agreement with these labels, not definitive real-world accuracy.",
        "", "| Measure | Result |", "|---|---:|",
    ]
    for key, label in [
        ("accuracy", "Accuracy"), ("precision", "Precision"), ("recall", "Recall"), ("f1", "F1"),
        ("specificity", "Specificity"), ("balanced_accuracy", "Balanced accuracy"),
        ("roc_auc", "ROC AUC"), ("average_precision", "Average precision"),
    ]:
        lines.append(f"| {label} | {pct(metrics.get(key))} |")
    lines += [
        "", f"Confusion counts: {c['true_positive']:,} positive pairs flagged; {c['false_positive']:,} weak negatives flagged; "
        f"{c['true_negative']:,} weak negatives not flagged; {c['false_negative']:,} positive pairs missed.",
        "", "## Weak-negative breakdown", "", "| Type | Pairs | Flagged | Flagged rate |", "|---|---:|---:|---:|",
    ]
    for kind, item in metrics["negative_sample_breakdown"].items():
        lines.append(f"| {kind} | {item['pairs']:,} | {item['flagged_as_duplicate']:,} | {pct(item['flagged_rate'])} |")
    lines += [
        "", "## Plain-language explanation", "",
        "For each pair, the program reused the live agent's category analyser and similarity function. The score combines shared title words, character-level title similarity, shared description words, and a small bonus when both issues receive the same category. A score at or above 0.48 is counted as a candidate.",
        "",
        "No model was trained, no paid API was called, no GitHub issue was changed, and the duplicate detector itself was not modified.",
        "", "## Limitations and next steps", "",
        "1. Review selected false positives, false negatives, and hard lexical negatives.",
        "2. A weak negative may itself be an undiscovered duplicate, so apparent false positives need human review.",
        "3. Keep this test split untouched; use validation data for tuning and comparisons.",
        "4. This pairwise test does not measure full live-repository top-three retrieval or speed.",
    ]
    (directory / "baseline_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the current duplicate detector without changing it.")
    parser.add_argument("--test-csv", type=Path, default=Path("evaluation/benchmark/generated/test.csv"))
    parser.add_argument("--manifest", type=Path, default=Path("evaluation/benchmark/generated/manifest.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/benchmark/generated/baseline"))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.threshold) or not 0 <= args.threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        rows = read_pairs(args.test_csv)
        manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.is_file() else {}
        metrics, scored = evaluate_rows(rows, threshold=args.threshold, dataset_manifest=manifest)
        write_outputs(args.output_dir, metrics, scored)
    except Exception as exc:
        print(f"Baseline evaluation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "output_dir": str(args.output_dir), "pairs_evaluated": metrics["pairs_evaluated"],
        "threshold": metrics["threshold"], "accuracy": metrics["accuracy"],
        "precision": metrics["precision"], "recall": metrics["recall"], "f1": metrics["f1"],
        "roc_auc": metrics["roc_auc"], "average_precision": metrics["average_precision"],
        "counts": metrics["counts"],
    }, indent=2))
    print("\nCaution: negative pairs are weak/unverified; metrics are agreement with benchmark labels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
