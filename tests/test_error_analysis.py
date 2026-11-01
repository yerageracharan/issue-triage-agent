from __future__ import annotations

import csv

from evaluation.benchmark.analyze_similarity_errors import analyze, write_outputs


def _row(pair_id: str, label: int, sample_type: str, lexical: float, bm25: float,
         semantic: float, hybrid: float) -> dict[str, str]:
    return {
        "pair_id": pair_id, "repo": "org/repo", "issue_1_number": "1",
        "issue_1_title": "Issue one title", "issue_1_body": "Long explanation one",
        "issue_2_number": "2", "issue_2_title": "Issue two title",
        "issue_2_body": "Long explanation two", "pair_label": str(label),
        "label_quality": "source_annotated_duplicate" if label else "weak_unlinked_candidate_not_human_verified",
        "sample_type": sample_type,
        "lexical_score": str(lexical), "bm25_score": str(bm25),
        "semantic_score": str(semantic), "hybrid_score": str(hybrid),
    }


def _comparison() -> dict:
    return {"methods": [
        {"method": name, "training": {"threshold_selected_by_max_training_f1": 0.5}}
        for name in ("lexical", "bm25", "semantic", "hybrid")
    ]}


def test_analysis_counts_confusion_and_creates_review_candidates():
    validation = [
        {k: v for k, v in _row("p1", 1, "source_positive", 0.9, 0.8, 0.7, 0.6).items()
         if not k.endswith("_score")},
        {k: v for k, v in _row("p2", 0, "hard_lexical", 0.8, 0.4, 0.6, 0.7).items()
         if not k.endswith("_score")},
        {k: v for k, v in _row("p3", 1, "source_positive", 0.1, 0.2, 0.3, 0.4).items()
         if not k.endswith("_score")},
    ]
    scores = [
        {"split": "validation", **_row("p1", 1, "source_positive", 0.9, 0.8, 0.7, 0.6)},
        {"split": "validation", **_row("p2", 0, "hard_lexical", 0.8, 0.4, 0.6, 0.7)},
        {"split": "validation", **_row("p3", 1, "source_positive", 0.1, 0.2, 0.3, 0.4)},
        {"split": "train", **_row("train-only", 1, "source_positive", 0.9, 0.8, 0.7, 0.6)},
    ]
    summary, review = analyze(validation, scores, _comparison(), top_n=1)
    assert summary["pairs"] == 3
    assert summary["methods"]["lexical"]["confusion_counts"] == {
        "TP": 1, "FP": 1, "TN": 0, "FN": 1,
    }
    assert summary["methods"]["lexical"]["weak_negative_breakdown"]["hard_lexical"]["alert_rate"] == 1.0
    assert {row["pair_id"] for row in review} == {"p2", "p3"}
    assert all(row["human_adjudication"] == "" for row in review)
    assert review[0]["issue_1_url"] == "https://github.com/org/repo/issues/1"
    assert review[0]["issue_2_url"] == "https://github.com/org/repo/issues/2"


def test_analysis_rejects_mismatched_pair_ids():
    validation = [{k: v for k, v in _row("p1", 1, "source_positive", 0.9, 0.8, 0.7, 0.6).items()
                   if not k.endswith("_score")}]
    scores = [{"split": "validation", **_row("other", 1, "source_positive", 0.9, 0.8, 0.7, 0.6)}]
    try:
        analyze(validation, scores, _comparison())
    except ValueError as exc:
        assert "pair IDs do not match" in str(exc)
    else:
        raise AssertionError("Expected mismatched pair IDs to be rejected")


def test_write_outputs_creates_report_json_and_csv(tmp_path):
    validation = [{k: v for k, v in _row("p1", 1, "source_positive", 0.9, 0.8, 0.7, 0.6).items()
                   if not k.endswith("_score")}]
    scores = [{"split": "validation", **_row("p1", 1, "source_positive", 0.9, 0.8, 0.7, 0.6)}]
    summary, review = analyze(validation, scores, _comparison(), top_n=1)
    write_outputs(tmp_path, summary, review)
    assert (tmp_path / "error_analysis_summary.json").is_file()
    assert (tmp_path / "error_analysis_report.md").is_file()
    assert (tmp_path / "review_examples.csv").is_file()
    assert (tmp_path / "reviewer_blind.csv").is_file()
    assert (tmp_path / "HUMAN_REVIEW_GUIDE.md").is_file()
    with (tmp_path / "reviewer_blind.csv").open(encoding="utf-8-sig", newline="") as handle:
        blind = list(csv.DictReader(handle))
    assert blind[0]["issue_1_url"] == "https://github.com/org/repo/issues/1"
    assert "pair_label" not in blind[0]
    assert "semantic_score" not in blind[0]
    assert "review_reason" not in blind[0]
