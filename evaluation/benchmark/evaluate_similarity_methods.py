"""Compare the existing lexical detector with BM25, local embeddings and a hybrid."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev

from issue_triage_agent.analyzer import analyse_issue
from issue_triage_agent.models import Issue
from issue_triage_agent.similarity import similarity_score

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
STOPWORDS = {"a","an","and","are","as","at","be","by","for","from","i","in","is","it","of","on","or","our","the","this","to","we","with","you","your","when","then"}
TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokens(text):
    result = []
    for word in TOKEN_RE.findall((text or "").casefold()):
        if len(word) <= 1 or word in STOPWORDS:
            continue
        if len(word) > 5 and word.endswith("ies"): word = word[:-3] + "y"
        elif len(word) > 5 and word.endswith("ing"): word = word[:-3]
        elif len(word) > 4 and word.endswith("ed"): word = word[:-2]
        elif len(word) > 4 and word.endswith("es") and word[-3] in "sxzh": word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"): word = word[:-1]
        result.append(word)
    return result


def read_pairs(path):
    csv.field_size_limit(sys.maxsize)
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"No pairs in {path}")
    required = {"pair_id","repo","issue_1_number","issue_1_title","issue_1_body","issue_2_number","issue_2_title","issue_2_body","pair_label","label_quality","sample_type","historical_issue_number","incoming_issue_number","chronology_status"}
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    return rows


def documents(rows):
    grouped = defaultdict(dict)
    for row in rows:
        repo = row["repo"].casefold()
        for prefix in ("issue_1", "issue_2"):
            number = str(row[f"{prefix}_number"])
            item = {"number": number, "title": row.get(f"{prefix}_title") or "", "body": row.get(f"{prefix}_body") or ""}
            old = grouped[repo].get(number)
            if old is None or len(item["title"]) + len(item["body"]) > len(old["title"]) + len(old["body"]):
                grouped[repo][number] = item
    return grouped


class RepoBM25:
    """BM25Okapi-style index built from issue records in one repository split."""
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs
        self.words = [tokens(d["title"] + "\n" + d["body"][:3000]) for d in docs]
        self.counts = [Counter(x) for x in self.words]
        self.lengths = [len(x) for x in self.words]
        self.avgdl = mean(self.lengths) if self.lengths else 0
        self.k1, self.b, self.n = k1, b, len(docs)
        df = Counter()
        for words in self.words: df.update(set(words))
        raw = {w: math.log((self.n - n + 0.5) / (n + 0.5)) for w, n in df.items()}
        avg_idf = mean(raw.values()) if raw else 0
        self.idf = {w: (v if v >= 0 else 0.25 * avg_idf) for w, v in raw.items()}
        self.lookup = {d["number"]: i for i, d in enumerate(docs)}

    def score(self, query, index):
        if not self.n or not self.avgdl: return 0.0
        tf, dl = self.counts[index], self.lengths[index]
        norm = self.k1 * (1 - self.b + self.b * dl / self.avgdl)
        return sum(self.idf.get(w, 0) * (tf[w] * (self.k1 + 1)) / (tf[w] + norm)
                   for w in set(query) if tf.get(w, 0))


def bm25_scores(rows):
    corpora = documents(rows)
    indexes = {repo: RepoBM25(sorted(items.values(), key=lambda d: int(d["number"])))
               for repo, items in corpora.items()}
    values = []
    for r in rows:
        ix = indexes[r["repo"].casefold()]
        a, b = ix.lookup[str(r["issue_1_number"])], ix.lookup[str(r["issue_2_number"])]
        values.append((ix.score(ix.words[a], b) + ix.score(ix.words[b], a)) / 2)
    return values


def embedding_scores(rows, model_name):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("Install local embedding support with: python -m pip install -e '.[similarity-experiments]'") from exc
    import numpy as np
    corpus = documents(rows)
    keys, texts = [], []
    for repo in sorted(corpus):
        for number in sorted(corpus[repo], key=int):
            d = corpus[repo][number]
            keys.append((repo, number))
            texts.append((d["title"] + "\n" + d["body"][:3000]).strip())
    model = SentenceTransformer(model_name, device="cpu")
    model.max_seq_length = min(int(model.max_seq_length), 256)
    vectors = model.encode(texts, batch_size=64, show_progress_bar=True,
                           convert_to_numpy=True, normalize_embeddings=True)
    by_key = {key: vectors[i] for i, key in enumerate(keys)}
    return [float(np.dot(by_key[(r["repo"].casefold(), str(r["issue_1_number"]))],
                         by_key[(r["repo"].casefold(), str(r["issue_2_number"]))])) for r in rows]


def auc(labels, scores):
    pos, neg = sum(labels), len(labels) - sum(labels)
    if not pos or not neg: return None
    ordered = sorted(zip(scores, labels))
    rank_sum, rank, i = 0.0, 1, 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]: j += 1
        avg_rank = (rank + rank + j - i - 1) / 2
        rank_sum += avg_rank * sum(y for _, y in ordered[i:j])
        rank += j - i
        i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def average_precision(labels, scores):
    pos = sum(labels)
    if not pos: return None
    ordered = sorted(zip(scores, labels), reverse=True)
    seen = found = i = 0
    previous = total = 0.0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][0] == ordered[i][0]: j += 1
        group = [y for _, y in ordered[i:j]]
        seen += len(group); found += sum(group)
        recall = found / pos
        total += (recall - previous) * found / seen
        previous = recall; i = j
    return total


def best_threshold(labels, scores):
    ordered = sorted(zip(scores, labels), reverse=True)
    pos = sum(labels); tp = fp = i = 0
    best_t, best = ordered[0][0] + 1e-12, {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    while i < len(ordered):
        threshold = ordered[i][0]; j = i
        while j < len(ordered) and ordered[j][0] == threshold:
            if ordered[j][1]: tp += 1
            else: fp += 1
            j += 1
        fn = pos - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / pos if pos else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        if (f1, precision, threshold) > (best["f1"], best["precision"], best_t):
            best_t, best = threshold, {"precision": precision, "recall": recall, "f1": f1}
        i = j
    return best_t, best


def at_threshold(labels, scores, threshold):
    tp = sum(y == 1 and s >= threshold for y, s in zip(labels, scores))
    fp = sum(y == 0 and s >= threshold for y, s in zip(labels, scores))
    tn = sum(y == 0 and s < threshold for y, s in zip(labels, scores))
    fn = sum(y == 1 and s < threshold for y, s in zip(labels, scores))
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2*p*r/(p+r) if p is not None and r is not None and p+r else None
    return {"threshold": threshold, "tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": p, "recall": r, "f1": f}


def retrieval(rows, scores):
    groups = defaultdict(list)
    for row, score in zip(rows, scores):
        if row["chronology_status"] == "ordered" and row["incoming_issue_number"]:
            groups[(row["repo"].casefold(), row["incoming_issue_number"])].append((score, int(row["pair_label"])))
    eligible = [items for items in groups.values() if len(items) >= 2 and any(y == 1 for _, y in items)]
    if not eligible: return {"queries_evaluated": 0, "mrr_at_3": None, "recall_at_3": None, "success_at_3": None}
    rr, recalls, success = [], [], []
    for items in eligible:
        ranked = sorted(items, key=lambda x: x[0], reverse=True)
        ranks = [i for i, (_, y) in enumerate(ranked, 1) if y == 1]
        hits = sum(i <= 3 for i in ranks)
        rr.append(1 / ranks[0] if ranks[0] <= 3 else 0.0)
        recalls.append(hits / len(ranks))
        success.append(float(hits > 0))
    return {"queries_evaluated": len(eligible), "mrr_at_3": mean(rr), "recall_at_3": mean(recalls),
            "success_at_3": mean(success),
            "query_rule": "At least two sampled candidate pairs and one source-labelled positive; singleton groups excluded."}


def standardise(train, values):
    center, scale = mean(train), pstdev(train) or 1.0
    return [1 / (1 + math.exp(-max(-30, min(30, (x-center)/scale)))) for x in values]


def run(train_rows, val_rows, model_name):
    train_labels = [int(r["pair_label"]) for r in train_rows]
    val_labels = [int(r["pair_label"]) for r in val_rows]

    def lexical(rows):
        cache, result = {}, []
        for r in rows:
            pair = []
            for prefix in ("issue_1", "issue_2"):
                number, title, body = str(r[f"{prefix}_number"]), r[f"{prefix}_title"], r[f"{prefix}_body"] or ""
                key = (r["repo"].casefold(), number, title, body)
                if key not in cache:
                    cache[key] = analyse_issue(Issue(int(number), title, body))
                pair.append(cache[key])
            result.append(float(similarity_score(pair[0], pair[1])))
        return result

    ts = {"lexical": lexical(train_rows), "bm25": bm25_scores(train_rows)}
    vs = {"lexical": lexical(val_rows), "bm25": bm25_scores(val_rows)}
    ts["semantic"] = embedding_scores(train_rows, model_name)
    vs["semantic"] = embedding_scores(val_rows, model_name)
    tb = standardise(ts["bm25"], ts["bm25"])
    vb = standardise(ts["bm25"], vs["bm25"])
    te = standardise(ts["semantic"], ts["semantic"])
    ve = standardise(ts["semantic"], vs["semantic"])
    ts["hybrid"] = [(x+y)/2 for x,y in zip(tb,te)]
    vs["hybrid"] = [(x+y)/2 for x,y in zip(vb,ve)]

    methods = []
    thresholds = {}
    for name in ("lexical", "bm25", "semantic", "hybrid"):
        threshold, train_f1 = best_threshold(train_labels, ts[name])
        thresholds[name] = threshold
        methods.append({
            "method": name,
            "training": {"pairs": len(train_rows), "roc_auc": auc(train_labels, ts[name]),
                         "average_precision": average_precision(train_labels, ts[name]),
                         "threshold_selected_by_max_training_f1": threshold,
                         "metrics_at_selected_threshold": train_f1},
            "validation": {"pairs": len(val_rows), "roc_auc": auc(val_labels, vs[name]),
                           "average_precision": average_precision(val_labels, vs[name]),
                           "metrics_at_training_selected_threshold": at_threshold(val_labels, vs[name], threshold),
                           "retrieval": retrieval(val_rows, vs[name])}
        })
    methods[0]["validation"]["metrics_at_existing_production_threshold_0_48"] = at_threshold(val_labels, vs["lexical"], 0.48)
    summary = {
        "experiment": "phase_3_similarity_method_comparison",
        "model": model_name,
        "training": {"pairs": len(train_rows), "repositories": len({r["repo"].casefold() for r in train_rows})},
        "validation": {"pairs": len(val_rows), "repositories": len({r["repo"].casefold() for r in val_rows})},
        "methods": methods,
        "methodology": {
            "lexical": "Unchanged production analyser and similarity function; issue analyses cached but scoring logic unchanged.",
            "bm25": "Local BM25Okapi-style index from unique issue records per repository within each split; symmetric average of both query directions.",
            "semantic": "CPU SentenceTransformer embeddings using all-MiniLM-L6-v2 by default, title-first issue text, 256-token maximum, cosine similarity.",
            "hybrid": "Equal average of BM25 and semantic scores after training-only z-score standardisation and logistic mapping.",
            "thresholds": "Each method's F1-maximising threshold is selected on training labels and applied unchanged to validation.",
            "retrieval": "MRR@3, Recall@3, Success@3 only for incoming-issue groups with at least two sampled candidates and one source-positive; singleton groups excluded.",
            "leakage": "Train and validation repository sets are checked for disjointness; hybrid scaling and thresholds use training only."
        },
        "warnings": [
            "Positive pairs are source-annotated, not independently re-labelled.",
            "Negatives are weak/unverified unlinked candidates and may include undiscovered duplicates.",
            "Validation results are for experimentation and model selection, not final unbiased performance claims.",
            "BM25 indexes are built from issues present in the prepared split, not the complete live GitHub history."
        ]
    }
    outputs = []
    for split, rows, scores in (("train", train_rows, ts), ("validation", val_rows, vs)):
        for i, r in enumerate(rows):
            item = {"split": split, "pair_id": r["pair_id"], "repo": r["repo"], "pair_label": int(r["pair_label"]),
                    "label_quality": r["label_quality"], "sample_type": r["sample_type"],
                    "historical_issue_number": r["historical_issue_number"], "incoming_issue_number": r["incoming_issue_number"]}
            for name, vals in scores.items(): item[f"{name}_score"] = vals[i]
            outputs.append(item)
    return summary, outputs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--train-csv", type=Path, required=True)
    p.add_argument("--validation-csv", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=Path("evaluation/benchmark/generated/phase3"))
    p.add_argument("--model", default=DEFAULT_MODEL)
    a = p.parse_args()
    try:
        train, val = read_pairs(a.train_csv), read_pairs(a.validation_csv)
        overlap = {r["repo"].casefold() for r in train} & {r["repo"].casefold() for r in val}
        if overlap: raise ValueError(f"Train/validation repository leakage: {sorted(overlap)[:5]}")
        summary, scores = run(train, val, a.model)
        a.output_dir.mkdir(parents=True, exist_ok=True)
        (a.output_dir / "similarity_comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        with (a.output_dir / "similarity_scores.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(scores[0]))
            writer.writeheader(); writer.writerows(scores)
        lines = ["# Phase 3 similarity-method comparison", "",
                 "Validation results are for experimentation, not final test claims. Positives are source-labelled and negatives are weak/unverified.", "",
                 "| Method | ROC AUC | Average precision | F1 at train-selected threshold | MRR@3 | Recall@3 |", "|---|---:|---:|---:|---:|---:|"]
        for m in summary["methods"]:
            v = m["validation"]
            fmt = lambda x: "n/a" if x is None else f"{x:.4f}"
            lines.append(f"| {m['method']} | {fmt(v['roc_auc'])} | {fmt(v['average_precision'])} | {fmt(v['metrics_at_training_selected_threshold']['f1'])} | {fmt(v['retrieval']['mrr_at_3'])} | {fmt(v['retrieval']['recall_at_3'])} |")
        lines += ["", "## Plain-language guide", "",
                  "- Lexical: the existing detector, based mainly on shared words and title patterns.",
                  "- BM25: a search-engine method that gives more weight to useful, uncommon words.",
                  "- Semantic: a small language model that compares the meaning of descriptions, not only matching words.",
                  "- Hybrid: combines BM25 and semantic scores using scaling learned from training scores only.",
                  "", "## Threshold selection", "",
                  "Each method's decision threshold is selected by maximising F1 on training pairs, then frozen before validation. The existing production lexical threshold of 0.48 is also reported separately. Threshold selection uses weak labels and is not human-verified.",
                  "", "## Limitations", "",
                  "The validation set is for experimentation. Keep the final test split untouched until method and settings are selected. MRR@3/Recall@3 only include incoming-issue groups with at least two sampled candidates and a known positive; singleton groups are excluded. Weak negatives can contain undiscovered duplicates."]
        (a.output_dir / "similarity_comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({"output_dir": str(a.output_dir), "methods": [
            {"method": m["method"], "roc_auc": m["validation"]["roc_auc"],
             "average_precision": m["validation"]["average_precision"],
             "f1": m["validation"]["metrics_at_training_selected_threshold"]["f1"]}
            for m in summary["methods"]]}, indent=2))
    except Exception as exc:
        print(f"Similarity comparison failed: {exc}", file=sys.stderr)
        return 1
    print("Caution: weak negatives are not human-confirmed non-duplicates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
