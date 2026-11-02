"""Evaluate the pre-frozen hybrid duplicate ranker once on the held-out test split.

This script intentionally selects no settings from test labels. It checks that the
training-derived threshold matches the frozen decision, applies that fixed value to
test scores, and compares the result with the unchanged production baseline.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from evaluation.benchmark.evaluate_baseline import evaluate_rows as evaluate_baseline_rows
from evaluation.benchmark.evaluate_similarity_methods import (
    DEFAULT_MODEL,
    at_threshold,
    auc,
    average_precision,
    best_threshold,
    bm25_scores,
    embedding_scores,
    read_pairs,
    retrieval,
    standardise,
)

DEFAULT_CONFIG = Path("evaluation/frozen_hybrid_config.json")
DEFAULT_OUTPUT = Path("evaluation/benchmark/generated/phase6")


def validate_inputs(
    train_rows: list[dict[str, str]],
    test_rows: list[dict[str, str]],
    manifest: dict[str, Any],
    config: dict[str, Any],
) -> None:
    """Fail closed if the held-out split or frozen experiment has changed."""
    train_repos = {row["repo"].casefold() for row in train_rows}
    test_repos = {row["repo"].casefold() for row in test_rows}
    overlap = train_repos & test_repos
    if overlap:
        raise ValueError(f"Training/test repository leakage: {sorted(overlap)[:5]}")

    train_ids = {row["pair_id"] for row in train_rows}
    test_ids = {row["pair_id"] for row in test_rows}
    if train_ids & test_ids:
        raise ValueError("Training and test pair IDs overlap.")

    if config.get("selected_method") != "hybrid":
        raise ValueError("Phase 6 config must freeze the hybrid method.")
    if config.get("frozen_before_test_evaluation") is False:
        raise ValueError("Frozen decision is marked as not frozen.")

    expected = {
        "dataset_revision": config.get("dataset_revision"),
        "dataset_fingerprint": config.get("dataset_fingerprint"),
        "seed": config.get("seed"),
    }
    actual = {
        "dataset_revision": manifest.get("dataset_revision"),
        "dataset_fingerprint": manifest.get("dataset_fingerprint"),
        "seed": manifest.get("seed"),
    }
    if expected != actual:
        raise ValueError(f"Dataset does not match frozen config: expected {expected}, got {actual}")

    if len(train_rows) != int(config["train_pairs"]):
        raise ValueError(f"Training pair count changed: {len(train_rows)}")
    if len(test_rows) != int(config["test_pairs"]):
        raise ValueError(f"Test pair count changed: {len(test_rows)}")
    if len(test_repos) != int(config["test_repositories"]):
        raise ValueError(f"Test repository count changed: {len(test_repos)}")


def check_frozen_threshold(computed: float, frozen: float, tolerance: float = 1e-10) -> None:
    """Verify training still yields the recorded threshold; never retune on test."""
    if not math.isclose(computed, frozen, rel_tol=0.0, abs_tol=tolerance):
        raise ValueError(
            "Training-derived threshold no longer matches the frozen decision: "
            f"computed={computed:.15f}, frozen={frozen:.15f}"
        )


def rank_candidate_rows(
    rows: list[dict[str, str]], scores: list[float], top_k: int = 3
) -> list[dict[str, Any]]:
    """Export top-k historical candidates for each incoming issue with >=2 candidates."""
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if len(rows) != len(scores):
        raise ValueError("rows and scores must have the same length")

    groups: dict[tuple[str, str], list[tuple[dict[str, str], float]]] = defaultdict(list)
    for row, score in zip(rows, scores):
        if row.get("chronology_status") == "ordered" and row.get("incoming_issue_number"):
            key = (row["repo"].casefold(), str(row["incoming_issue_number"]))
            groups[key].append((row, float(score)))

    ranked_rows: list[dict[str, Any]] = []
    for (repo, incoming_number), candidates in sorted(groups.items()):
        if len(candidates) < 2:
            continue
        ranked = sorted(candidates, key=lambda item: item[1], reverse=True)
        for rank, (row, score) in enumerate(ranked[:top_k], start=1):
            ranked_rows.append({
                "repo": row["repo"],
                "incoming_issue_number": incoming_number,
                "rank": rank,
                "historical_issue_number": row["historical_issue_number"],
                "pair_id": row["pair_id"],
                "hybrid_score": score,
                "pair_label_for_offline_evaluation_only": int(row["pair_label"]),
                "label_quality": row["label_quality"],
            })
    return ranked_rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def evaluate(
    train_rows: list[dict[str, str]],
    test_rows: list[dict[str, str]],
    manifest: dict[str, Any],
    config: dict[str, Any],
    model_name: str = DEFAULT_MODEL,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    validate_inputs(train_rows, test_rows, manifest, config)

    train_labels = [int(row["pair_label"]) for row in train_rows]
    test_labels = [int(row["pair_label"]) for row in test_rows]

    # Component scores are calibrated using training statistics only.
    train_bm25 = bm25_scores(train_rows)
    test_bm25 = bm25_scores(test_rows)
    train_semantic = embedding_scores(train_rows, model_name)
    test_semantic = embedding_scores(test_rows, model_name)

    train_bm25_scaled = standardise(train_bm25, train_bm25)
    test_bm25_scaled = standardise(train_bm25, test_bm25)
    train_semantic_scaled = standardise(train_semantic, train_semantic)
    test_semantic_scaled = standardise(train_semantic, test_semantic)

    weights = config["hybrid_weights"]
    train_hybrid = [
        weights["bm25"] * bm25 + weights["semantic"] * semantic
        for bm25, semantic in zip(train_bm25_scaled, train_semantic_scaled)
    ]
    test_hybrid = [
        weights["bm25"] * bm25 + weights["semantic"] * semantic
        for bm25, semantic in zip(test_bm25_scaled, test_semantic_scaled)
    ]

    # Recalculate from TRAIN only as an integrity check; do not optimise on test.
    train_threshold, train_threshold_metrics = best_threshold(train_labels, train_hybrid)
    frozen_threshold = float(config["threshold"])
    check_frozen_threshold(train_threshold, frozen_threshold)

    hybrid_at_threshold = at_threshold(test_labels, test_hybrid, frozen_threshold)
    hybrid_retrieval = retrieval(test_rows, test_hybrid)

    # The comparison baseline is the unchanged production heuristic on these same test rows.
    baseline_metrics, baseline_scores = evaluate_baseline_rows(test_rows, threshold=0.48, dataset_manifest=manifest)
    baseline_values = [float(item["similarity_score"]) for item in baseline_scores]
    baseline_retrieval = retrieval(test_rows, baseline_values)

    test_score_rows: list[dict[str, Any]] = []
    for row, hybrid_score, baseline in zip(test_rows, test_hybrid, baseline_scores):
        test_score_rows.append({
            "pair_id": row["pair_id"],
            "repo": row["repo"],
            "historical_issue_number": row["historical_issue_number"],
            "incoming_issue_number": row["incoming_issue_number"],
            "pair_label": int(row["pair_label"]),
            "label_quality": row["label_quality"],
            "sample_type": row["sample_type"],
            "hybrid_score": hybrid_score,
            "hybrid_prediction_at_frozen_threshold": int(hybrid_score >= frozen_threshold),
            "baseline_score": float(baseline["similarity_score"]),
            "baseline_prediction_at_0_48": int(baseline["predicted_duplicate_at_threshold"]),
        })

    ranked_rows = rank_candidate_rows(
        test_rows, test_hybrid, top_k=int(config["retrieval_k"])
    )

    hybrid_metrics = {
        "method": "hybrid",
        "threshold": frozen_threshold,
        "threshold_source": "frozen training-only threshold",
        "threshold_recomputed_from_training_for_integrity_check": train_threshold,
        "training_metrics_at_threshold": train_threshold_metrics,
        "pairs_evaluated": len(test_rows),
        "repositories": len({row["repo"].casefold() for row in test_rows}),
        "roc_auc": auc(test_labels, test_hybrid),
        "average_precision": average_precision(test_labels, test_hybrid),
        "classification_at_frozen_threshold": hybrid_at_threshold,
        "retrieval_at_3": hybrid_retrieval,
        "flagged_candidates": sum(score >= frozen_threshold for score in test_hybrid),
        "weak_negative_alerts": sum(
            int(row["pair_label"]) == 0 and score >= frozen_threshold
            for row, score in zip(test_rows, test_hybrid)
        ),
        "negative_sample_breakdown": {},
    }
    for sample_type in sorted({row["sample_type"] for row in test_rows if row["pair_label"] == "0"}):
        subset = [
            score for row, score in zip(test_rows, test_hybrid)
            if row["pair_label"] == "0" and row["sample_type"] == sample_type
        ]
        hybrid_metrics["negative_sample_breakdown"][sample_type] = {
            "pairs": len(subset),
            "flagged": sum(score >= frozen_threshold for score in subset),
        }

    summary = {
        "experiment": "phase_6_frozen_hybrid_held_out_test",
        "decision_id": config["decision_id"],
        "dataset": {
            "id": manifest["dataset_id"],
            "revision": manifest["dataset_revision"],
            "fingerprint": manifest["dataset_fingerprint"],
            "seed": manifest["seed"],
            "train_pairs": len(train_rows),
            "test_pairs": len(test_rows),
            "train_repositories": len({row["repo"].casefold() for row in train_rows}),
            "test_repositories": len({row["repo"].casefold() for row in test_rows}),
            "repository_split_leakage_free": len(
                {row["repo"].casefold() for row in train_rows}
                & {row["repo"].casefold() for row in test_rows}
            ) == 0,
        },
        "frozen_configuration": config,
        "hybrid_test": hybrid_metrics,
        "baseline_test": {
            "threshold": baseline_metrics["threshold"],
            "pairs_evaluated": baseline_metrics["pairs_evaluated"],
            "accuracy": baseline_metrics["accuracy"],
            "precision": baseline_metrics["precision"],
            "recall": baseline_metrics["recall"],
            "f1": baseline_metrics["f1"],
            "specificity": baseline_metrics["specificity"],
            "balanced_accuracy": baseline_metrics["balanced_accuracy"],
            "roc_auc": baseline_metrics["roc_auc"],
            "average_precision": baseline_metrics["average_precision"],
            "counts": baseline_metrics["counts"],
            "retrieval_at_3": baseline_retrieval,
        },
        "comparison": {
            "f1_change_vs_baseline": (
                hybrid_at_threshold["f1"] - baseline_metrics["f1"]
                if hybrid_at_threshold["f1"] is not None and baseline_metrics["f1"] is not None
                else None
            ),
            "recall_at_3_change_vs_baseline": (
                hybrid_retrieval["recall_at_3"] - baseline_retrieval["recall_at_3"]
                if hybrid_retrieval["recall_at_3"] is not None and baseline_retrieval["recall_at_3"] is not None
                else None
            ),
            "mrr_at_3_change_vs_baseline": (
                hybrid_retrieval["mrr_at_3"] - baseline_retrieval["mrr_at_3"]
                if hybrid_retrieval["mrr_at_3"] is not None and baseline_retrieval["mrr_at_3"] is not None
                else None
            ),
        },
        "interpretation_warnings": [
            "This is one held-out test evaluation of the frozen method; do not tune against these results.",
            "Positive pairs are source-annotated, not independently human-relabelled.",
            "Negative pairs are weak unlinked candidates, not confirmed non-duplicates.",
            "The top-three retrieval metric excludes incoming-issue groups with fewer than two sampled candidates or no known positive.",
            "Results measure agreement with this benchmark sample, not production accuracy on all live GitHub issues.",
            "Phase 5 evidence notes were AI-assisted and were not substituted for independent human adjudications.",
        ],
    }
    return summary, test_score_rows, ranked_rows


def write_outputs(
    output_dir: Path,
    summary: dict[str, Any],
    test_score_rows: list[dict[str, Any]],
    ranked_rows: list[dict[str, Any]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "phase6_final_test.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "frozen_configuration_snapshot.json").write_text(
        json.dumps(summary["frozen_configuration"], indent=2) + "\n", encoding="utf-8"
    )
    if test_score_rows:
        _write_csv(output_dir / "test_pair_scores.csv", test_score_rows, list(test_score_rows[0]))
    else:
        raise ValueError("No per-pair test scores were produced.")
    candidate_fields = [
        "repo", "incoming_issue_number", "rank", "historical_issue_number",
        "pair_id", "hybrid_score", "pair_label_for_offline_evaluation_only", "label_quality",
    ]
    _write_csv(output_dir / "top3_ranked_candidates.csv", ranked_rows, candidate_fields)

    hybrid = summary["hybrid_test"]
    baseline = summary["baseline_test"]
    retrieval_h = hybrid["retrieval_at_3"]
    retrieval_b = baseline["retrieval_at_3"]
    cls = hybrid["classification_at_frozen_threshold"]
    lines = [
        "# Phase 6 — Frozen hybrid evaluation on held-out test data", "",
        "**Method and settings were frozen before this run.** The test labels were used only to calculate final metrics, never to choose a threshold or model setting.", "",
        f"- Decision: `{summary['decision_id']}`",
        f"- Dataset revision: `{summary['dataset']['revision']}`",
        f"- Training pairs: **{summary['dataset']['train_pairs']:,}** across {summary['dataset']['train_repositories']} repositories",
        f"- Held-out test pairs: **{summary['dataset']['test_pairs']:,}** across {summary['dataset']['test_repositories']} repositories",
        f"- Hybrid threshold: **{hybrid['threshold']:.15f}** (selected from training only)",
        f"- Embedding model: `{summary['frozen_configuration']['embedding_model']}`",
        "", "## Main result", "",
        "| Metric | Existing detector | Frozen hybrid |",
        "|---|---:|---:|",
        f"| Precision | {_pct(baseline['precision'])} | {_pct(cls['precision'])} |",
        f"| Recall | {_pct(baseline['recall'])} | {_pct(cls['recall'])} |",
        f"| F1 | {_pct(baseline['f1'])} | {_pct(cls['f1'])} |",
        f"| ROC AUC | {_pct(baseline['roc_auc'])} | {_pct(hybrid['roc_auc'])} |",
        f"| Average precision | {_pct(baseline['average_precision'])} | {_pct(hybrid['average_precision'])} |",
        f"| MRR@3 | {_pct(retrieval_b['mrr_at_3'])} | {_pct(retrieval_h['mrr_at_3'])} |",
        f"| Recall@3 | {_pct(retrieval_b['recall_at_3'])} | {_pct(retrieval_h['recall_at_3'])} |",
        "", "## Plain-language interpretation", "",
        "Precision asks: of the pairs the detector flagged, how many carry a source-positive label?",
        "Recall asks: of the source-positive pairs, how many did it find?",
        "F1 balances precision and recall. MRR@3 rewards putting a known duplicate near the top of the first three suggestions. Recall@3 asks whether at least one known duplicate appears among those three candidates.",
        "",
        "The current detector uses its unchanged threshold of 0.48. The hybrid uses the frozen threshold selected on training data. Neither threshold was selected from test results.",
        "",
        "## Confusion counts", "",
        "| Method | True positives | Weak-negative alerts | True negatives | Positive pairs missed |",
        "|---|---:|---:|---:|---:|",
        f"| Existing detector | {baseline['counts']['true_positive']} | {baseline['counts']['false_positive']} | {baseline['counts']['true_negative']} | {baseline['counts']['false_negative']} |",
        f"| Frozen hybrid | {cls['tp']} | {cls['fp']} | {cls['tn']} | {cls['fn']} |",
        "",
        "A weak-negative alert is not automatically a confirmed false positive. Some unlinked pairs may be genuine duplicates absent from the source links.",
        "", "## What must not happen next", "",
        "- Do not adjust the hybrid threshold after seeing this test result.",
        "- Do not change embedding model, hybrid weights, preprocessing or top-k based on this result.",
        "- New tuning requires a new validation set; a fresh independent test set is needed for another unbiased final claim.",
        "", "## Human-review status", "",
        summary["frozen_configuration"]["human_review_status"],
    ]
    (output_dir / "phase6_final_test_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-csv", type=Path, required=True)
    parser.add_argument("--test-csv", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        train_rows = read_pairs(args.train_csv)
        test_rows = read_pairs(args.test_csv)
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        config = json.loads(args.config.read_text(encoding="utf-8"))
        if args.model != config["embedding_model"]:
            raise ValueError(
                f"Model differs from frozen decision: {args.model!r} != {config['embedding_model']!r}"
            )
        summary, test_scores, ranked = evaluate(
            train_rows, test_rows, manifest, config, model_name=args.model
        )
        write_outputs(args.output_dir, summary, test_scores, ranked)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Frozen hybrid test evaluation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "output_dir": str(args.output_dir),
        "test_pairs": summary["dataset"]["test_pairs"],
        "test_repositories": summary["dataset"]["test_repositories"],
        "threshold": summary["hybrid_test"]["threshold"],
        "hybrid_metrics": summary["hybrid_test"]["classification_at_frozen_threshold"],
        "hybrid_retrieval_at_3": summary["hybrid_test"]["retrieval_at_3"],
        "baseline_metrics": summary["baseline_test"],
    }, indent=2))
    print("Warning: test labels were used for metrics only; the configuration was frozen before evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
