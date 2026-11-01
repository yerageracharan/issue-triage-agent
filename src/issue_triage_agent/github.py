"""Read-only GitHub REST API client."""

from __future__ import annotations

import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import Issue


class GitHubAPIError(RuntimeError):
    """Raised when the GitHub API cannot supply the requested issue data."""


def parse_repository(value: str) -> tuple[str, str]:
    value = value.strip().rstrip("/")
    if value.startswith(("https://", "http://")):
        parsed = urlparse(value)
        if parsed.netloc.casefold() not in {"github.com", "www.github.com"}:
            raise ValueError("Only github.com repository URLs are supported.")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("Repository URL must look like https://github.com/owner/repo.")
        owner, repo = parts[:2]
    else:
        parts = value.split("/")
        if len(parts) != 2:
            raise ValueError("Repository must be written as owner/repo or a GitHub URL.")
        owner, repo = parts
    owner = re.sub(r"\.git$", "", owner)
    repo = re.sub(r"\.git$", "", repo)
    if not owner or not repo or any(char in owner + repo for char in "?#"):
        raise ValueError("The repository owner or name is invalid.")
    return owner, repo


def fetch_issues(repository: str, *, state: str = "open", limit: int = 100, timeout: int = 20) -> list[Issue]:
    if state not in {"open", "closed", "all"}:
        raise ValueError("state must be one of: open, closed, all")
    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    owner, repo = parse_repository(repository)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    issues: list[Issue] = []
    page = 1

    while len(issues) < limit:
        page_size = min(100, limit - len(issues))
        url = f"https://api.github.com/repos/{owner}/{repo}/issues?state={state}&per_page={page_size}&page={page}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "issue-triage-agent/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(url, headers=headers, method="GET")

        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            if exc.code == 404:
                raise GitHubAPIError(f"Repository not found or not public: {owner}/{repo}") from exc
            if exc.code == 403 and "rate limit" in detail.casefold():
                raise GitHubAPIError("GitHub API rate limit reached. Set GITHUB_TOKEN to increase the available rate limit.") from exc
            raise GitHubAPIError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise GitHubAPIError(f"Could not reach GitHub: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise GitHubAPIError("GitHub returned an invalid JSON response.") from exc

        if not isinstance(payload, list):
            raise GitHubAPIError("Unexpected GitHub API response: expected an issue list.")
        if not payload:
            break

        for item in payload:
            # GitHub's issues endpoint also includes pull requests.
            if isinstance(item, dict) and "pull_request" not in item:
                issues.append(Issue.from_github_payload(item))
                if len(issues) >= limit:
                    break
        if len(payload) < page_size:
            break
        page += 1
        time.sleep(0.05)

    return issues
