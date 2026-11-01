from __future__ import annotations

from evaluation.benchmark.evaluate_similarity_methods import (
    RepoBM25, tokens, auc, average_precision, best_threshold,
    at_threshold, retrieval,
)


def test_tokenizer_removes_common_stopwords_and_normalises_suffixes():
    assert tokens("The crashes are happening after exporting CSVs") == [
        "crash", "happen", "after", "export", "csv"
    ]


def test_bm25_prefers_a_document_with_matching_terms():
    docs = [
        {"number": "1", "title": "CSV export crash", "body": "download fails"},
        {"number": "2", "title": "CSV export crash", "body": "download exception"},
        {"number": "3", "title": "theme colour option", "body": "settings panel"},
    ]
    index = RepoBM25(docs)
    query = tokens("CSV export crashes during download")
    assert index.score(query, 1) > index.score(query, 2)


def test_auc_and_average_precision_handle_tied_scores():
    assert auc([1, 0], [0.5, 0.5]) == 0.5
    assert average_precision([1, 0], [0.5, 0.5]) == 0.5
    assert auc([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2]) == 1.0


def test_threshold_is_selected_on_training_and_can_be_applied():
    threshold, train_metrics = best_threshold([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1])
    assert 0.8 <= threshold <= 0.9
    result = at_threshold([1, 0], [0.85, 0.15], threshold)
    assert result["tp"] == result["tn"] == 1
    assert train_metrics["f1"] == 1.0


def test_retrieval_at_three_excludes_single_candidate_queries():
    rows = [
        {"repo": "org/r", "incoming_issue_number": "10", "chronology_status": "ordered", "pair_label": "1"},
        {"repo": "org/r", "incoming_issue_number": "10", "chronology_status": "ordered", "pair_label": "0"},
        {"repo": "org/r", "incoming_issue_number": "11", "chronology_status": "ordered", "pair_label": "1"},
    ]
    result = retrieval(rows, [0.9, 0.2, 0.4])
    assert result["queries_evaluated"] == 1
    assert result["mrr_at_3"] == result["recall_at_3"] == result["success_at_3"] == 1.0
