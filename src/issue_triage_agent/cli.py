"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import analyse_issue
from .github import GitHubAPIError, fetch_issues
from .llm import LocalLLM, LocalLLMError
from .models import Issue
from .report import write_reports
from .similarity import attach_duplicate_candidates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issue-triage",
        description="Analyse GitHub issues and generate a human-review triage report (read-only).",
    )
    parser.add_argument("repository", help="GitHub repository as owner/name or https://github.com/owner/name")
    parser.add_argument("--state", choices=("open", "closed", "all"), default="open", help="Issue state to analyse (default: open)")
    parser.add_argument("--limit", type=int, default=100, help="Maximum number of issues to fetch (1–500; default: 100)")
    parser.add_argument("--output", default="reports", help="Output directory (default: reports)")
    parser.add_argument("--input-json", help="Analyse a saved GitHub issues API JSON response instead of making a network request")
    parser.add_argument("--no-llm", action="store_true", help="Disable optional local LLM enrichment")
    return parser


def _load_fixture(path: str) -> list[Issue]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Input JSON must contain a list of GitHub issue objects.")
    return [Issue.from_github_payload(item) for item in data if isinstance(item, dict) and "pull_request" not in item]


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.limit <= 500:
        print("Error: --limit must be between 1 and 500.", file=sys.stderr)
        return 2

    try:
        issues = _load_fixture(args.input_json) if args.input_json else fetch_issues(
            args.repository, state=args.state, limit=args.limit
        )
        results = [analyse_issue(issue) for issue in issues]
        attach_duplicate_candidates(results)

        llm = None if args.no_llm else LocalLLM.from_environment()
        if llm:
            for result in results:
                try:
                    llm.enrich(result)
                except LocalLLMError as exc:
                    print(f"Warning: {exc}. Continuing without model enrichment.", file=sys.stderr)
                    break

        markdown_path, json_path = write_reports(args.repository, results, args.output)
    except (GitHubAPIError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    flagged = sum(item.needs_attention for item in results)
    print(f"Analysed {len(results)} issue(s) from {args.repository}.")
    print(f"Flagged for human attention: {flagged}")
    print(f"Markdown report: {markdown_path}")
    print(f"JSON report:     {json_path}")
    if not issues:
        print("No matching issues were returned.")
    return 0


def main() -> None:
    raise SystemExit(run())
