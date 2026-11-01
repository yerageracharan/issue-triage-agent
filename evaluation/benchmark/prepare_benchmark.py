"""Prepare a repository-grouped benchmark from Primordic/IssueDupesLite.

The script deliberately creates weak/unverified negatives. An issue pair that is
not linked in the source dataset is not necessarily a true non-duplicate.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

DATASET_ID = "primordic/IssueDupesLite"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
DATASET_LICENSE = "CC-BY-SA-4.0"

REQUIRED_COLUMNS = (
    "name",
    "primary_issue_num",
    "primary_title",
    "primary_body",
    "primary_issue_created_at",
    "duplicate_issue_num",
    "duplicate_title",
    "duplicate_body",
    "duplicate_issue_created_at",
    "duplicate_closing_comment",
    "comment_created_at",
)

PAIR_FIELDS = (
    "pair_id",
    "repo",
    "issue_1_number",
    "issue_1_title",
    "issue_1_body",
    "issue_1_created_at",
    "issue_2_number",
    "issue_2_title",
    "issue_2_body",
    "issue_2_created_at",
    "pair_label",
    "label_quality",
    "sample_type",
    "lexical_overlap_hint",
    "source_primary_issue_number",
    "source_duplicate_issue_number",
    "source_closing_comment",
    "comment_created_at",
    "historical_issue_number",
    "incoming_issue_number",
    "chronology_status",
    "source_pair_rows",
)

DEFAULT_RATIOS = {"train": 0.70, "validation": 0.15, "test": 0.15}
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "i", "in", "is", "it", "of", "on", "or", "our", "the", "this",
    "to", "we", "with", "you", "your", "when", "then", "that",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _issue_number(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid GitHub issue number: {value!r}") from None
    if number <= 0:
        raise ValueError(f"GitHub issue number must be positive: {number}")
    return number


def _parse_date(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _repo_name(row: dict[str, Any]) -> str:
    repo = _text(row.get("name"))
    if repo:
        return repo.strip("/")
    owner = _text(row.get("owner"))
    short_name = _text(row.get("repo"))
    if owner and short_name:
        return f"{owner}/{short_name}"
    raise ValueError("Row has no repository name in 'name' or ('owner', 'repo') fields")


def _issue_record(number: Any, title: Any, body: Any, created_at: Any) -> dict[str, Any]:
    return {
        "number": _issue_number(number),
        "title": _text(title),
        "body": _text(body),
        "created_at": _text(created_at),
    }


def _record_quality(record: dict[str, Any]) -> tuple[int, int, str]:
    return (
        len(record["title"]) + len(record["body"]),
        len(record["body"]),
        record["created_at"],
    )


def collect_issue_records(
    rows: Iterable[dict[str, Any]],
) -> tuple[dict[str, dict[int, dict[str, Any]]], int]:
    """Collect unique issue records; prefer the richest source text for repeated IDs."""
    records: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    skipped = 0
    for row in rows:
        try:
            repo = _repo_name(row)
            for prefix in ("primary", "duplicate"):
                record = _issue_record(
                    row.get(f"{prefix}_issue_num"),
                    row.get(f"{prefix}_title"),
                    row.get(f"{prefix}_body"),
                    row.get(f"{prefix}_issue_created_at"),
                )
                current = records[repo.casefold()].get(record["number"])
                if current is None or _record_quality(record) > _record_quality(current):
                    records[repo.casefold()][record["number"]] = record
        except (TypeError, ValueError, KeyError):
            skipped += 1
    return dict(records), skipped


def _pair_id(repo: str, left: int, right: int) -> str:
    low, high = sorted((int(left), int(right)))
    return f"{repo.casefold()}#{low}#{high}"


def _chronology(
    first: dict[str, Any], second: dict[str, Any]
) -> tuple[str, str, str]:
    first_date = _parse_date(first.get("created_at"))
    second_date = _parse_date(second.get("created_at"))
    if first_date is None or second_date is None:
        return "", "", "missing_or_invalid_date"
    if first_date == second_date:
        return "", "", "same_timestamp_order_unknown"
    earlier, later = (
        (first, second) if first_date < second_date else (second, first)
    )
    return str(earlier["number"]), str(later["number"]), "ordered"


def _make_pair_row(
    repo: str,
    first: dict[str, Any],
    second: dict[str, Any],
    *,
    pair_label: int,
    label_quality: str,
    sample_type: str,
    lexical_overlap_hint: float | str = "",
    source_primary_issue_number: int | str = "",
    source_duplicate_issue_number: int | str = "",
    source_closing_comment: str = "",
    comment_created_at: str = "",
    source_pair_rows: int = 0,
) -> dict[str, Any]:
    issue_1, issue_2 = sorted((first, second), key=lambda item: item["number"])
    historical, incoming, chronology_status = _chronology(issue_1, issue_2)
    return {
        "pair_id": _pair_id(repo, issue_1["number"], issue_2["number"]),
        "repo": repo,
        "issue_1_number": issue_1["number"],
        "issue_1_title": issue_1["title"],
        "issue_1_body": issue_1["body"],
        "issue_1_created_at": issue_1["created_at"],
        "issue_2_number": issue_2["number"],
        "issue_2_title": issue_2["title"],
        "issue_2_body": issue_2["body"],
        "issue_2_created_at": issue_2["created_at"],
        "pair_label": pair_label,
        "label_quality": label_quality,
        "sample_type": sample_type,
        "lexical_overlap_hint": lexical_overlap_hint,
        "source_primary_issue_number": source_primary_issue_number,
        "source_duplicate_issue_number": source_duplicate_issue_number,
        "source_closing_comment": source_closing_comment,
        "comment_created_at": comment_created_at,
        "historical_issue_number": historical,
        "incoming_issue_number": incoming,
        "chronology_status": chronology_status,
        "source_pair_rows": source_pair_rows,
    }


def prepare_positive_pairs(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[int, dict[str, Any]]], dict[str, int]]:
    """Normalize/deduplicate the source's manually identified duplicate pairs."""
    records, skipped_record_rows = collect_issue_records(rows)
    positives: dict[str, dict[str, Any]] = {}
    skipped_pairs = 0

    for row in rows:
        try:
            repo = _repo_name(row)
            primary = _issue_record(
                row.get("primary_issue_num"),
                row.get("primary_title"),
                row.get("primary_body"),
                row.get("primary_issue_created_at"),
            )
            duplicate = _issue_record(
                row.get("duplicate_issue_num"),
                row.get("duplicate_title"),
                row.get("duplicate_body"),
                row.get("duplicate_issue_created_at"),
            )
            if primary["number"] == duplicate["number"]:
                skipped_pairs += 1
                continue
            key = _pair_id(repo, primary["number"], duplicate["number"])
            pair = _make_pair_row(
                repo,
                primary,
                duplicate,
                pair_label=1,
                label_quality="source_annotated_duplicate",
                sample_type="source_positive",
                source_primary_issue_number=primary["number"],
                source_duplicate_issue_number=duplicate["number"],
                source_closing_comment=_text(row.get("duplicate_closing_comment")),
                comment_created_at=_text(row.get("comment_created_at")),
                source_pair_rows=1,
            )
            if key in positives:
                existing = positives[key]
                existing["source_pair_rows"] += 1
                comment = pair["source_closing_comment"]
                if len(comment) > len(existing["source_closing_comment"]):
                    existing["source_closing_comment"] = comment
            else:
                positives[key] = pair
        except (TypeError, ValueError, KeyError):
            skipped_pairs += 1

    counts = {
        "input_rows": len(rows),
        "skipped_record_rows": skipped_record_rows,
        "skipped_positive_rows": skipped_pairs,
        "duplicate_source_rows_collapsed": sum(
            max(0, int(item["source_pair_rows"]) - 1) for item in positives.values()
        ),
    }
    return (
        sorted(positives.values(), key=lambda item: (item["repo"].casefold(), item["pair_id"])),
        records,
        counts,
    )


class _UnionFind:
    def __init__(self, values: Iterable[int]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: int) -> int:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def _tokens(record: dict[str, Any]) -> set[str]:
    text = f"{record.get('title', '')} {record.get('body', '')[:5000]}"
    return {
        token for token in TOKEN_RE.findall(text.casefold())
        if len(token) > 1 and token not in STOPWORDS
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def lexical_overlap_hint(
    first: dict[str, Any],
    second: dict[str, Any],
    token_cache: dict[tuple[str, int], set[str]] | None = None,
    repo: str = "",
) -> float:
    """A sampling heuristic only; this is not the agent's duplicate score."""
    if token_cache is None:
        left_tokens = _tokens(first)
        right_tokens = _tokens(second)
    else:
        left_tokens = token_cache.setdefault((repo, first["number"]), _tokens(first))
        right_tokens = token_cache.setdefault((repo, second["number"]), _tokens(second))
    title_left = set(TOKEN_RE.findall(first["title"].casefold()))
    title_right = set(TOKEN_RE.findall(second["title"].casefold()))
    return round(0.65 * _jaccard(title_left, title_right) + 0.35 * _jaccard(left_tokens, right_tokens), 6)


def sample_negative_pairs(
    positives: list[dict[str, Any]],
    records_by_repo: dict[str, dict[int, dict[str, Any]]],
    *,
    seed: int = 42,
    negative_ratio: float = 1.0,
    hard_negative_fraction: float = 0.5,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Sample same-repository unlinked pairs, excluding known duplicate components.

    These are weak negatives: absence of a source duplicate link is not proof
    that the two reports describe different bugs.
    """
    if negative_ratio < 0:
        raise ValueError("negative_ratio must be >= 0")
    if not 0 <= hard_negative_fraction <= 1:
        raise ValueError("hard_negative_fraction must be between 0 and 1")

    rng = random.Random(seed)
    positives_by_repo: dict[str, list[dict[str, Any]]] = defaultdict(list)
    repo_display: dict[str, str] = {}
    for pair in positives:
        key = pair["repo"].casefold()
        positives_by_repo[key].append(pair)
        repo_display[key] = pair["repo"]

    negatives: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    for repo_key in sorted(positives_by_repo):
        repo_positives = positives_by_repo[repo_key]
        issue_records = records_by_repo.get(repo_key, {})
        if len(issue_records) < 2:
            stats[repo_key] = {"positive_pairs": len(repo_positives), "negative_pairs": 0, "candidate_pairs": 0}
            continue

        union_find = _UnionFind(issue_records)
        for pair in repo_positives:
            union_find.union(int(pair["issue_1_number"]), int(pair["issue_2_number"]))

        # If A-B and A-C are known positives, B-C is not a valid negative.
        candidate_pairs: list[tuple[int, int, float]] = []
        token_cache: dict[tuple[str, int], set[str]] = {}
        numbers = sorted(issue_records)
        for left_num, right_num in combinations(numbers, 2):
            if union_find.find(left_num) == union_find.find(right_num):
                continue
            left = issue_records[left_num]
            right = issue_records[right_num]
            score = lexical_overlap_hint(left, right, token_cache, repo_key)
            candidate_pairs.append((left_num, right_num, score))

        target = int(round(len(repo_positives) * negative_ratio))
        if target <= 0 or not candidate_pairs:
            stats[repo_key] = {
                "positive_pairs": len(repo_positives),
                "negative_pairs": 0,
                "candidate_pairs": len(candidate_pairs),
            }
            continue

        hard_candidates = sorted(
            (item for item in candidate_pairs if item[2] > 0),
            key=lambda item: (-item[2], item[0], item[1]),
        )
        hard_target = int(round(target * hard_negative_fraction))
        selected_hard = hard_candidates[:hard_target]
        selected_keys = {(a, b) for a, b, _ in selected_hard}

        remaining = [
            item for item in candidate_pairs if (item[0], item[1]) not in selected_keys
        ]
        rng.shuffle(remaining)
        random_needed = target - len(selected_hard)
        selected_random = remaining[:random_needed]

        for left_num, right_num, score in selected_hard:
            negatives.append(
                _make_pair_row(
                    repo_display[repo_key],
                    issue_records[left_num],
                    issue_records[right_num],
                    pair_label=0,
                    label_quality="weak_unlinked_candidate_not_human_verified",
                    sample_type="hard_lexical",
                    lexical_overlap_hint=score,
                )
            )
        for left_num, right_num, score in selected_random:
            negatives.append(
                _make_pair_row(
                    repo_display[repo_key],
                    issue_records[left_num],
                    issue_records[right_num],
                    pair_label=0,
                    label_quality="weak_unlinked_candidate_not_human_verified",
                    sample_type="random_same_repo",
                    lexical_overlap_hint=score,
                )
            )

        stats[repo_key] = {
            "positive_pairs": len(repo_positives),
            "negative_pairs": len(selected_hard) + len(selected_random),
            "hard_negative_pairs": len(selected_hard),
            "random_negative_pairs": len(selected_random),
            "candidate_pairs": len(candidate_pairs),
            "undersampled": len(selected_hard) + len(selected_random) < target,
        }

    negatives.sort(key=lambda item: (item["repo"].casefold(), item["pair_id"]))
    return negatives, stats


def assign_repository_splits(
    positives: list[dict[str, Any]],
    *,
    seed: int = 42,
    ratios: dict[str, float] | None = None,
) -> dict[str, str]:
    """Assign each repository to exactly one split using a deterministic greedy balance."""
    ratios = ratios or DEFAULT_RATIOS
    if set(ratios) != {"train", "validation", "test"}:
        raise ValueError("ratios must contain train, validation, and test")
    if any(value <= 0 for value in ratios.values()):
        raise ValueError("all split ratios must be > 0")
    if abs(sum(ratios.values()) - 1.0) > 1e-8:
        raise ValueError("split ratios must add up to 1.0")

    counts = Counter(pair["repo"].casefold() for pair in positives)
    repos = list(counts)
    rng = random.Random(seed)
    rng.shuffle(repos)
    repos.sort(key=lambda item: -counts[item])

    total = sum(counts.values())
    targets = {name: total * ratio for name, ratio in ratios.items()}
    assigned_counts = Counter()
    assigned_repos = Counter()
    split_for_repo: dict[str, str] = {}
    order = {name: index for index, name in enumerate(("train", "validation", "test"))}

    for repo_key in repos:
        split = min(
            ratios,
            key=lambda name: (
                assigned_counts[name] / max(targets[name], 1e-12),
                assigned_repos[name],
                order.get(name, 99),
            ),
        )
        split_for_repo[repo_key] = split
        assigned_counts[split] += counts[repo_key]
        assigned_repos[split] += 1

    return split_for_repo


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIR_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PAIR_FIELDS})


def _write_repo_splits(
    path: Path,
    positives: list[dict[str, Any]],
    split_map: dict[str, str],
) -> None:
    counts = Counter(pair["repo"].casefold() for pair in positives)
    display = {pair["repo"].casefold(): pair["repo"] for pair in positives}
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=("repo", "split", "source_positive_pair_count")
        )
        writer.writeheader()
        for key in sorted(split_map):
            writer.writerow({
                "repo": display[key],
                "split": split_map[key],
                "source_positive_pair_count": counts[key],
            })


def _write_attribution(path: Path, revision: str, counts: dict[str, Any]) -> None:
    content = f"""# Benchmark data attribution

This benchmark preparation uses IssueDupesLite by Primordic.

- Dataset: {DATASET_URL}
- Dataset repository: {DATASET_ID}
- Retrieved revision: {revision}
- Declared dataset licence: {DATASET_LICENSE}
- Source description: 10K primary/duplicate GitHub issue pairs.
- Viewer snapshot: the Hugging Face dataset viewer currently displays 10,000 rows and 992 distinct repository values. The card prose says "10 issue pairs from 1,000 repositories"; preparation reports actual loaded counts and does not rely on that prose summary.

The positive pairs are derived from the source dataset. The negative examples are newly sampled pairs of issue records from the same repositories that are not connected by a known positive duplicate edge in the source. They are weak, unverified negatives, not ground-truth non-duplicates. This distinction matters because the source maintainers warn that true duplicates may not all be labelled.

The generated benchmark data contains excerpts of third-party GitHub issue titles and descriptions. Keep this attribution and the source's share-alike licence with redistributed derivative benchmark files. The main Issue Triage Agent source-code licence does not replace the dataset licence.

## Preparation settings

- Random seed: {counts.get("seed")}
- Negative-to-positive target ratio: {counts.get("negative_ratio")}
- Hard-negative target fraction: {counts.get("hard_negative_fraction")}
- Repository split ratios: {json.dumps(counts.get("split_ratios"), sort_keys=True)}
- Source rows loaded: {counts.get("input_rows")}
- Unique source positive pairs: {counts.get("positive_pairs")}
- Weak negative pairs sampled: {counts.get("negative_pairs")}
- Repositories: {counts.get("repositories")}

See the source dataset card for full terms, attribution details, and limitations. This file is informational and is not legal advice.
"""
    path.write_text(content, encoding="utf-8")


def write_benchmark(
    output_dir: Path,
    positives: list[dict[str, Any]],
    negatives: list[dict[str, Any]],
    split_map: dict[str, str],
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "positive_pairs.csv", positives)
    write_csv(output_dir / "negative_pairs.csv", negatives)
    _write_repo_splits(output_dir / "repository_splits.csv", positives, split_map)

    all_pairs = positives + negatives
    pair_splits = {name: [] for name in ("train", "validation", "test")}
    for pair in all_pairs:
        split = split_map.get(pair["repo"].casefold())
        if split is None:
            raise ValueError(f"Repository missing split assignment: {pair['repo']}")
        pair_splits[split].append(pair)

    for split_name, split_rows in pair_splits.items():
        split_rows.sort(key=lambda item: (item["repo"].casefold(), int(item["pair_label"]), item["pair_id"]))
        write_csv(output_dir / f"{split_name}.csv", split_rows)

    per_split = {}
    for name, items in pair_splits.items():
        per_split[name] = {
            "pairs": len(items),
            "positive_pairs": sum(int(item["pair_label"]) == 1 for item in items),
            "weak_negative_pairs": sum(int(item["pair_label"]) == 0 for item in items),
            "repositories": len({item["repo"].casefold() for item in items}),
        }

    repo_to_split = defaultdict(set)
    for repo, split in split_map.items():
        repo_to_split[repo].add(split)
    leakage_free = all(len(splits) == 1 for splits in repo_to_split.values())

    manifest = {
        **metadata,
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URL,
        "dataset_license": DATASET_LICENSE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "positive_pairs": len(positives),
        "negative_pairs": len(negatives),
        "repositories": len(split_map),
        "repository_split_leakage_free": leakage_free,
        "split_counts": per_split,
        "negative_label_warning": (
            "pair_label=0 means the pair is not connected by a known positive edge "
            "in this source sample. It is a weak/unverified negative, not a human-confirmed "
            "non-duplicate. Audit examples before treating them as gold labels."
        ),
        "chronology_warning": (
            "The dataset explicitly notes that its selected primary issue can be newer "
            "than the duplicate issue. historical_issue_number/incoming_issue_number are "
            "derived from creation timestamps, while source primary/duplicate roles are "
            "preserved separately."
        ),
        "outputs": [
            "positive_pairs.csv", "negative_pairs.csv", "repository_splits.csv",
            "train.csv", "validation.csv", "test.csv", "manifest.json", "ATTRIBUTION.md",
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_attribution(output_dir / "ATTRIBUTION.md", str(metadata.get("dataset_revision", "unknown")), manifest)
    return manifest


def load_huggingface_dataset(
    dataset_id: str = DATASET_ID,
    revision: str = "main",
    cache_dir: str | None = None,
) -> tuple[list[dict[str, Any]], str, str]:
    """Load the dataset and pin the resolved Hub commit SHA in generated metadata."""
    try:
        from datasets import load_dataset
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise RuntimeError(
            "Benchmark download dependencies are missing. Install them with: "
            "python -m pip install -e '.[benchmark]'"
        ) from exc

    info = HfApi().dataset_info(repo_id=dataset_id, repo_type="dataset", revision=revision)
    resolved_revision = str(info.sha)
    kwargs: dict[str, Any] = {
        "path": dataset_id,
        "split": "train",
        "revision": resolved_revision,
    }
    if cache_dir:
        kwargs["cache_dir"] = cache_dir
    dataset = load_dataset(**kwargs)
    rows = [dict(row) for row in dataset]
    fingerprint = str(getattr(dataset, "_fingerprint", ""))
    return rows, resolved_revision, fingerprint


def prepare(
    rows: list[dict[str, Any]],
    *,
    output_dir: Path,
    seed: int = 42,
    negative_ratio: float = 1.0,
    hard_negative_fraction: float = 0.5,
    split_ratios: dict[str, float] | None = None,
    dataset_revision: str = "fixture",
    dataset_fingerprint: str = "",
) -> dict[str, Any]:
    """Prepare all benchmark files from already-loaded source rows."""
    if not rows:
        raise ValueError("The source dataset is empty")
    missing = sorted(set(REQUIRED_COLUMNS) - set(rows[0]))
    if missing:
        raise ValueError(f"Source dataset is missing required columns: {', '.join(missing)}")

    positives, records_by_repo, source_counts = prepare_positive_pairs(rows)
    if not positives:
        raise ValueError("No valid positive pairs were found in the source dataset")
    split_ratios = split_ratios or DEFAULT_RATIOS
    split_map = assign_repository_splits(positives, seed=seed, ratios=split_ratios)
    negatives, negative_stats = sample_negative_pairs(
        positives,
        records_by_repo,
        seed=seed,
        negative_ratio=negative_ratio,
        hard_negative_fraction=hard_negative_fraction,
    )

    metadata = {
        **source_counts,
        "dataset_revision": dataset_revision,
        "dataset_fingerprint": dataset_fingerprint,
        "seed": seed,
        "negative_ratio": negative_ratio,
        "hard_negative_fraction": hard_negative_fraction,
        "split_ratios": split_ratios,
        "negative_sampling_by_repository": negative_stats,
    }
    return write_benchmark(
        output_dir, positives, negatives, split_map, metadata=metadata
    )


def _ratio(value: str) -> float:
    try:
        result = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("ratio must be a number") from None
    if not 0 <= result <= 1:
        raise argparse.ArgumentTypeError("ratio must be between 0 and 1")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download IssueDupesLite and prepare repository-separated duplicate benchmark files."
    )
    parser.add_argument("--dataset-id", default=DATASET_ID)
    parser.add_argument("--revision", default="main", help="Hub branch, tag, or commit; the resolved commit SHA is saved.")
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/benchmark/generated"))
    parser.add_argument("--cache-dir", default="evaluation/benchmark/.cache")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--negative-ratio", type=float, default=1.0, help="Weak negatives per positive pair.")
    parser.add_argument("--hard-negative-fraction", type=_ratio, default=0.5)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ratios = {
        "train": args.train_ratio,
        "validation": args.validation_ratio,
        "test": args.test_ratio,
    }
    try:
        if args.negative_ratio < 0:
            raise ValueError("--negative-ratio must be >= 0")
        if any(value <= 0 for value in ratios.values()) or abs(sum(ratios.values()) - 1.0) > 1e-8:
            raise ValueError("train, validation, and test ratios must all be > 0 and sum to 1.0")
        print(f"Downloading {args.dataset_id} from Hugging Face...", file=sys.stderr)
        rows, revision, fingerprint = load_huggingface_dataset(
            args.dataset_id, args.revision, args.cache_dir
        )
        print(f"Loaded {len(rows):,} rows at revision {revision}.", file=sys.stderr)
        manifest = prepare(
            rows,
            output_dir=args.output_dir,
            seed=args.seed,
            negative_ratio=args.negative_ratio,
            hard_negative_fraction=args.hard_negative_fraction,
            split_ratios=ratios,
            dataset_revision=revision,
            dataset_fingerprint=fingerprint,
        )
    except Exception as exc:
        print(f"Benchmark preparation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "output_dir": str(args.output_dir),
        "source_rows": manifest["input_rows"],
        "positive_pairs": manifest["positive_pairs"],
        "weak_negative_pairs": manifest["negative_pairs"],
        "repositories": manifest["repositories"],
        "repository_split_leakage_free": manifest["repository_split_leakage_free"],
        "split_counts": manifest["split_counts"],
    }, indent=2))
    print("\nReminder: label=0 rows are unverified unlinked candidates, not confirmed true negatives.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
