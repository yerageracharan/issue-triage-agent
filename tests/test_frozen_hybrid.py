from __future__ import annotations

import pytest

from evaluation.frozen_hybrid import (
    check_frozen_threshold,
    rank_candidate_rows,
    validate_inputs,
)


def _config() -> dict:
    return {
        "selected_method": "hybrid",
        "dataset_revision": "rev-123",
        "dataset_fingerprint": "fingerprint",
        "seed": 42,
        "train_pairs": 2,
        "test_pairs": 2,
        "test_repositories": 1,
    }


def _manifest() -> dict:
    return {
        "dataset_revision": "rev-123",
        "dataset_fingerprint": "fingerprint",
        "seed": 42,
    }


def _row(pair_id: str, repo: str, incoming: str, historical: str, label: str) -> dict[str, str]:
    return {
        "pair_id": pair_id,
        "repo": repo,
        "incoming_issue_number": incoming,
        "historical_issue_number": historical,
        "chronology_status": "ordered",
        "pair_label": label,
        "label_quality": "source_annotated_duplicate" if label == "1" else "weak_unlinked_candidate_not_human_verified",
    }


def test_validate_inputs_accepts_disjoint_frozen_splits():
    train = [
        {"pair_id": "t1", "repo": "org/train"},
        {"pair_id": "t2", "repo": "org/train"},
    ]
    test = [
        {"pair_id": "e1", "repo": "org/test"},
        {"pair_id": "e2", "repo": "org/test"},
    ]
    validate_inputs(train, test, _manifest(), _config())


def test_validate_inputs_rejects_repository_leakage():
    train = [{"pair_id": "t1", "repo": "org/shared"}, {"pair_id": "t2", "repo": "org/train"}]
    test = [{"pair_id": "e1", "repo": "org/shared"}, {"pair_id": "e2", "repo": "org/test"}]
    with pytest.raises(ValueError, match="repository leakage"):
        validate_inputs(train, test, _manifest(), _config())


def test_validate_inputs_rejects_pair_id_overlap():
    train = [{"pair_id": "same", "repo": "org/train"}, {"pair_id": "t2", "repo": "org/train"}]
    test = [{"pair_id": "same", "repo": "org/test"}, {"pair_id": "e2", "repo": "org/test"}]
    with pytest.raises(ValueError, match="pair IDs overlap"):
        validate_inputs(train, test, _manifest(), _config())


def test_validate_inputs_rejects_changed_dataset_revision():
    train = [{"pair_id": "t1", "repo": "org/train"}, {"pair_id": "t2", "repo": "org/train"}]
    test = [{"pair_id": "e1", "repo": "org/test"}, {"pair_id": "e2", "repo": "org/test"}]
    manifest = {**_manifest(), "dataset_revision": "different-revision"}
    with pytest.raises(ValueError, match="Dataset does not match frozen config"):
        validate_inputs(train, test, manifest, _config())


def test_frozen_threshold_must_match_training_derived_value():
    check_frozen_threshold(0.41291124292046016, 0.41291124292046016)
    with pytest.raises(ValueError, match="no longer matches the frozen decision"):
        check_frozen_threshold(0.50, 0.41291124292046016)


def test_rank_candidate_rows_sorts_and_keeps_top_three():
    rows = [
        _row("p1", "org/repo", "20", "1", "1"),
        _row("p2", "org/repo", "20", "2", "0"),
        _row("p3", "org/repo", "20", "3", "1"),
        _row("p4", "org/repo", "20", "4", "0"),
        _row("p5", "org/repo", "30", "5", "1"),
    ]
    scores = [0.6, 0.9, 0.8, 0.2, 0.7]
    ranked = rank_candidate_rows(rows, scores, top_k=3)
    assert len(ranked) == 3
    assert [row["pair_id"] for row in ranked] == ["p2", "p3", "p1"]
    assert [row["rank"] for row in ranked] == [1, 2, 3]


def test_rank_candidate_rows_excludes_unordered_and_singleton_groups():
    rows = [
        _row("p1", "org/repo", "20", "1", "1"),
        _row("p2", "org/repo", "20", "2", "0"),
        {**_row("p3", "org/repo", "", "3", "1"), "chronology_status": "unordered"},
        _row("p4", "org/repo", "40", "4", "1"),
    ]
    ranked = rank_candidate_rows(rows, [0.8, 0.7, 0.9, 1.0], top_k=3)
    assert [row["pair_id"] for row in ranked] == ["p1", "p2"]


def test_rank_candidate_rows_rejects_mismatched_input_lengths():
    rows = [_row("p1", "org/repo", "20", "1", "1")]
    with pytest.raises(ValueError, match="same length"):
        rank_candidate_rows(rows, [])
