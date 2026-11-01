from __future__ import annotations

import pytest

from evaluation.benchmark.evaluate_baseline import (
    average_precision, classification_metrics, evaluate_rows, roc_auc, score_pair,
)


def test_classification_metrics():
    result = classification_metrics([1, 0, 1, 0], [1, 1, 0, 0])
    assert result["counts"] == {
        "true_positive": 1, "false_positive": 1,
        "true_negative": 1, "false_negative": 1,
    }
    assert result["accuracy"] == result["precision"] == result["recall"] == 0.5
    assert result["f1"] == result["specificity"] == result["balanced_accuracy"] == 0.5


def test_roc_auc_with_ties_and_perfect_order():
    assert roc_auc([1, 0], [0.5, 0.5]) == 0.5
    assert roc_auc([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2]) == 1.0


def test_average_precision_with_ties():
    assert average_precision([1, 0], [0.5, 0.5]) == 0.5
    assert average_precision([1, 0], [0.9, 0.1]) == 1.0


def test_score_pair_uses_project_category_and_similarity():
    row = {
        "issue_1_number": "1", "issue_1_title": "Application crashes when exporting CSV",
        "issue_1_body": "The export fails with an exception.",
        "issue_2_number": "2", "issue_2_title": "Application crashes when exporting CSV",
        "issue_2_body": "The export fails with an exception.",
    }
    score, category_1, category_2 = score_pair(row)
    assert score == pytest.approx(1.0)
    assert category_1 == category_2 == "bug"


def test_evaluation_keeps_weak_label_warning_and_uses_default_threshold():
    rows = [
        {
            "pair_id": "org/repo#1#2", "repo": "org/repo",
            "issue_1_number": "1", "issue_1_title": "Application crashes when exporting CSV",
            "issue_1_body": "The export fails with an exception.",
            "issue_2_number": "2", "issue_2_title": "Application crashes when exporting CSV",
            "issue_2_body": "The export fails with an exception.",
            "pair_label": "1", "label_quality": "source_annotated_duplicate", "sample_type": "source_positive",
        },
        {
            "pair_id": "org/repo#3#4", "repo": "org/repo",
            "issue_1_number": "3", "issue_1_title": "Change the website background colour", "issue_1_body": "",
            "issue_2_number": "4", "issue_2_title": "Database connection fails",
            "issue_2_body": "The database cannot connect.",
            "pair_label": "0", "label_quality": "weak_unlinked_candidate_not_human_verified",
            "sample_type": "random_same_repo",
        },
    ]
    metrics, scored = evaluate_rows(rows)
    assert metrics["pairs_evaluated"] == 2 and metrics["threshold"] == 0.48
    assert metrics["counts"]["true_positive"] == metrics["counts"]["true_negative"] == 1
    assert metrics["method"]["detector_modified"] is False
    assert len(scored) == 2
    assert any("weak" in note.lower() for note in metrics["interpretation_warnings"])
