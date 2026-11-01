from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evaluation.benchmark.prepare_benchmark import (
    assign_repository_splits,
    prepare,
    prepare_positive_pairs,
    sample_negative_pairs,
)


def pair_row(
    repo: str,
    primary_num: int,
    duplicate_num: int,
    primary_title: str,
    duplicate_title: str,
    *,
    primary_body: str = "",
    duplicate_body: str = "",
    primary_date: str = "2022-03-01T00:00:00Z",
    duplicate_date: str = "2022-02-01T00:00:00Z",
):
    return {
        "name": repo,
        "owner": repo.split("/")[0],
        "repo": repo.split("/")[1],
        "primary_issue_num": primary_num,
        "primary_title": primary_title,
        "primary_body": primary_body,
        "primary_issue_created_at": primary_date,
        "duplicate_issue_num": duplicate_num,
        "duplicate_title": duplicate_title,
        "duplicate_body": duplicate_body,
        "duplicate_issue_created_at": duplicate_date,
        "duplicate_closing_comment": f"Duplicate of #{primary_num}",
        "comment_created_at": "2022-04-01T00:00:00Z",
    }


def fixture_rows():
    rows = []
    for repo, base in (("org/alpha", 1), ("org/beta", 101), ("org/gamma", 201)):
        rows.extend([
            pair_row(
                repo, base, base + 1,
                "CSV export crashes during download",
                "Downloading CSV causes a crash",
                primary_body="CSV download throws an exception in the export flow.",
                duplicate_body="The export flow throws an exception when downloading CSV.",
            ),
            pair_row(
                repo, base + 2, base + 3,
                "Dark mode setting disappears",
                "Theme preference is not saved",
                primary_body="The dark mode setting resets after restarting.",
                duplicate_body="My theme selection is lost after reopening the application.",
            ),
            pair_row(
                repo, base + 4, base + 5,
                "Login returns HTTP 403",
                "Cannot authenticate with account",
                primary_body="The server returns 403 during login.",
                duplicate_body="Authentication fails and the account cannot sign in.",
            ),
            pair_row(
                repo, base + 6, base + 7,
                "CSV export has wrong decimal separator",
                "CSV output uses unexpected decimal formatting",
                primary_body="The CSV export uses commas where decimal points are expected.",
                duplicate_body="Decimal values in exported CSV files use the wrong separator.",
            ),
        ])
    rows.append(pair_row(
        "org/alpha", 2, 1,
        "Downloading CSV causes a crash",
        "CSV export crashes during download",
        primary_body="The export flow throws an exception when downloading CSV.",
        duplicate_body="CSV download throws an exception in the export flow.",
        primary_date="2022-02-01T00:00:00Z",
        duplicate_date="2022-03-01T00:00:00Z",
    ))
    return rows


def test_positive_pairs_are_deduplicated_and_keep_source_roles():
    positives, _, counts = prepare_positive_pairs(fixture_rows())
    alpha = [p for p in positives if p["repo"] == "org/alpha"]
    first = next(p for p in alpha if {p["issue_1_number"], p["issue_2_number"]} == {1, 2})
    assert len(positives) == 12
    assert first["source_pair_rows"] == 2
    assert first["pair_label"] == 1
    assert first["label_quality"] == "source_annotated_duplicate"
    assert counts["duplicate_source_rows_collapsed"] == 1


def test_chronology_uses_dates_not_source_primary_duplicate_roles():
    rows = [
        pair_row(
            "org/alpha", 99, 8, "Canonical issue opened later", "Older report",
            primary_date="2023-05-01T00:00:00Z",
            duplicate_date="2023-01-01T00:00:00Z",
        )
    ]
    positives, _, _ = prepare_positive_pairs(rows)
    pair = positives[0]
    assert pair["historical_issue_number"] == "8"
    assert pair["incoming_issue_number"] == "99"
    assert pair["chronology_status"] == "ordered"
    assert pair["source_primary_issue_number"] == 99


def test_transitive_duplicate_component_is_never_a_negative():
    rows = [
        pair_row("org/alpha", 1, 2, "Issue one", "Issue two"),
        pair_row("org/alpha", 1, 3, "Issue one", "Issue three"),
        pair_row("org/alpha", 4, 5, "Unrelated subsystem", "Other subsystem"),
    ]
    positives, records, _ = prepare_positive_pairs(rows)
    negatives, _ = sample_negative_pairs(positives, records, seed=7, negative_ratio=10)
    negative_numbers = {
        frozenset((item["issue_1_number"], item["issue_2_number"])) for item in negatives
    }
    assert frozenset((2, 3)) not in negative_numbers
    assert all(item["pair_label"] == 0 for item in negatives)
    assert all(
        item["label_quality"] == "weak_unlinked_candidate_not_human_verified"
        for item in negatives
    )


def test_negative_sampling_is_deterministic_and_has_both_types():
    positives, records, _ = prepare_positive_pairs(fixture_rows())
    first, _ = sample_negative_pairs(
        positives, records, seed=23, negative_ratio=1, hard_negative_fraction=0.5
    )
    second, _ = sample_negative_pairs(
        positives, records, seed=23, negative_ratio=1, hard_negative_fraction=0.5
    )
    assert [(p["pair_id"], p["sample_type"]) for p in first] == [
        (p["pair_id"], p["sample_type"]) for p in second
    ]
    assert any(p["sample_type"] == "hard_lexical" for p in first)
    assert any(p["sample_type"] == "random_same_repo" for p in first)


def test_repository_split_is_deterministic_and_grouped():
    positives, _, _ = prepare_positive_pairs(fixture_rows())
    first = assign_repository_splits(positives, seed=42)
    second = assign_repository_splits(positives, seed=42)
    assert first == second
    assert set(first) == {"org/alpha", "org/beta", "org/gamma"}
    assert len(set(first.values())) == 3


def test_prepare_writes_positive_negative_and_split_files(tmp_path):
    manifest = prepare(
        fixture_rows(),
        output_dir=tmp_path,
        seed=42,
        negative_ratio=1,
        hard_negative_fraction=0.5,
        dataset_revision="fixture-sha",
        dataset_fingerprint="fixture-fingerprint",
    )
    expected = {
        "positive_pairs.csv", "negative_pairs.csv", "repository_splits.csv",
        "train.csv", "validation.csv", "test.csv", "manifest.json", "ATTRIBUTION.md",
    }
    assert expected.issubset({path.name for path in tmp_path.iterdir()})
    assert manifest["repository_split_leakage_free"] is True
    assert manifest["positive_pairs"] == 12

    assignments = {}
    with (tmp_path / "repository_splits.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            assignments[row["repo"]] = row["split"]
    split_repos = {}
    for split in ("train", "validation", "test"):
        with (tmp_path / f"{split}.csv").open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                split_repos.setdefault(row["repo"], set()).add(split)
    assert all(len(value) == 1 for value in split_repos.values())
    assert all(next(iter(split_repos[repo])) == assignments[repo] for repo in split_repos)

    loaded = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert loaded["dataset_revision"] == "fixture-sha"
    assert "weak/unverified" in loaded["negative_label_warning"]


def test_prepare_rejects_missing_schema(tmp_path):
    with pytest.raises(ValueError, match="missing required columns"):
        prepare([{"name": "org/repo"}], output_dir=tmp_path)


def test_prepare_rejects_empty_source(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        prepare([], output_dir=tmp_path)
