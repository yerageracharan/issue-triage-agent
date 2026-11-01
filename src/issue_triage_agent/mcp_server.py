"""MCP server exposing Issue Triage Agent tools.

The default transport is stdio for local clients such as Claude Desktop.
Streamable HTTP is available for a separately secured remote deployment.
"""

from __future__ import annotations

import argparse
from typing import Literal

try:
    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations
except ImportError as exc:  # pragma: no cover - exercised in environments without the extra
    raise SystemExit(
        "The MCP integration is optional. Install it with: "
        'python -m pip install -e ".[mcp]"'
    ) from exc

from .github import fetch_issues
from .service import analyse_issues, analyse_single_issue, build_triage_payload, triage_policy


mcp = MCPServer(
    "Issue Triage Agent",
    instructions=(
        "You are connected to a read-only GitHub issue triage service. "
        "Use triage_github_repository to inspect a repository backlog and "
        "triage_issue_text to assess text supplied by the user. Every category, "
        "priority, missing-detail flag, and duplicate candidate is provisional. "
        "Never claim that the service changed GitHub; it has no write tools."
    ),
)

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)


@mcp.tool(annotations=_READ_ONLY)
def triage_github_repository(
    repository: str,
    state: Literal["open", "closed", "all"] = "open",
    limit: int = 50,
) -> dict[str, object]:
    """Read and triage issues in a GitHub repository.

    Args:
        repository: GitHub repository as owner/name or a github.com URL.
        state: Which issue state to inspect: open, closed, or all.
        limit: Maximum number of issues to inspect (1-100). Pull requests are excluded.

    Returns category and priority suggestions, missing report details, and possible
    duplicate candidates. The operation uses GitHub GET requests only.
    """
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100 for MCP calls")
    issues = fetch_issues(repository, state=state, limit=limit)
    results = analyse_issues(issues)
    return build_triage_payload(repository, results)


@mcp.tool(annotations=_READ_ONLY)
def triage_issue_text(
    title: str,
    body: str = "",
    labels: list[str] | None = None,
) -> dict[str, object]:
    """Classify a single issue draft without making a GitHub API request.

    Use this for an issue draft, copied report, or text supplied by the user.
    The tool returns a category, provisional priority, rationale, suggested labels
    (not applied), and missing-information checks.
    """
    return analyse_single_issue(title=title, body=body, labels=labels)


@mcp.tool(annotations=_READ_ONLY)
def explain_triage_rules() -> dict[str, object]:
    """Explain the categories, provisional priorities, duplicate logic, and safety limits."""
    return triage_policy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issue-triage-mcp",
        description="Run the Issue Triage Agent MCP server.",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="stdio for local desktop clients; streamable-http for a secured remote host.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind address (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000).")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        if not 1 <= args.port <= 65535:
            raise SystemExit("--port must be between 1 and 65535")
        mcp.run(transport="streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
