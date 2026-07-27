"""Nadi Transport — real federation messaging via GitHub API.

Instead of writing to a local file nobody reads, this creates actual
GitHub issues/discussions on peer repos or dispatches workflows.

Nadi = channel/nerve in the federation mesh.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

REPO_OWNER = "kimeisele"


class NadiTransport:
    """Send and receive messages across the federation mesh via GitHub API."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    def send_research_result(self, target_repo: str, inquiry_id: str,
                              title: str, abstract: str, confidence: str,
                              document_url: str) -> dict[str, Any] | None:
        """Notify a peer node about a completed research result.

        Creates an issue on the target repo (or dispatches a workflow).
        """
        body = (
            f"## Research Result from agent-research\n\n"
            f"**Inquiry:** {inquiry_id}\n"
            f"**Confidence:** {confidence}\n\n"
            f"### Abstract\n{abstract}\n\n"
            f"**Full document:** {document_url}\n\n"
            f"---\n"
            f"*Sent by Research Engine & Faculty via Nadi Transport*\n"
            f"*{datetime.now(timezone.utc).isoformat()}*"
        )

        return self._create_issue(
            repo=f"{REPO_OWNER}/{target_repo}",
            title=f"[research-result] {title[:80]}",
            body=body,
            labels=["research-result", "federation-nadi"],
        )

    def send_inquiry(self, target_repo: str, question: str, context: str,
                      domains: list[str], urgency: str = "standard") -> dict[str, Any] | None:
        """Send a research inquiry to a peer node."""
        body = (
            f"## Research Inquiry from agent-research\n\n"
            f"**Question:** {question}\n\n"
            f"**Context:** {context}\n\n"
            f"**Domains:** {', '.join(domains)}\n"
            f"**Urgency:** {urgency}\n\n"
            f"---\n"
            f"*Sent by Research Engine & Faculty via Nadi Transport*"
        )

        return self._create_issue(
            repo=f"{REPO_OWNER}/{target_repo}",
            title=f"[research-inquiry] {question[:80]}",
            body=body,
            labels=["research-inquiry", "federation-nadi"],
        )

    def dispatch_workflow(self, target_repo: str, workflow: str,
                           inputs: dict[str, str] | None = None) -> bool:
        """Trigger a workflow on a peer repo."""
        data: dict[str, Any] = {"ref": "main"}
        if inputs:
            data["inputs"] = inputs
        result = self._api(
            f"/repos/{REPO_OWNER}/{target_repo}/actions/workflows/{workflow}/dispatches",
            method="POST", data=data,
        )
        return result is not None

    def read_inbox(self, labels: str = "federation-nadi") -> list[dict[str, Any]]:
        """Read incoming nadi messages (issues on our repo)."""
        issues = self._api(
            f"/repos/{REPO_OWNER}/agent-research/issues?labels={labels}&state=open&per_page=50"
        )
        if not isinstance(issues, list):
            return []
        return issues

    def _build_search_query(self, repo: str, body_contains: str) -> str:
        """Build a GitHub search query for dedup.  Exposed for testing."""
        return f'repo:{repo} "{body_contains}" in:body type:issue'

    def search_issues(self, repo: str, body_contains: str) -> list[dict[str, Any]] | None:
        """Search open and closed issues in a repo for a body substring.

        Omits ``state:`` so both open and closed issues are searched.
        Applies *local* body verification on every returned item —
        GitHub search may produce approximate results that must be
        rejected when they do not contain the exact marker.

        Returns a list of locally-verified matching issues, or None
        on API failure.
        """
        from urllib.parse import quote
        q = self._build_search_query(repo, body_contains)
        path = f"/search/issues?q={quote(q)}&per_page=10&sort=created&order=desc"
        result = self._api(path)
        if result is None:
            return None
        if isinstance(result, dict) and "items" in result:
            return [item for item in result["items"]
                    if body_contains in (item.get("body") or "")]
        return []

    def _create_issue(self, repo: str, title: str, body: str,
                       labels: list[str] | None = None) -> dict[str, Any] | None:
        data: dict[str, Any] = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        result = self._api(f"/repos/{repo}/issues", method="POST", data=data)
        if result and "number" in result:
            logger.info("  Nadi: created issue #%d on %s", result["number"], repo)
        return result

    def _api(self, path: str, method: str = "GET", data: dict | None = None) -> Any:
        if not self.token:
            logger.warning("No GITHUB_TOKEN — nadi transport disabled")
            return None
        url = f"https://api.github.com{path}"
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read()
                return json.loads(resp_body) if resp_body else {}
        except urllib.error.HTTPError as e:
            logger.warning("Nadi API error %d for %s %s", e.code, method, path)
            return None
        except Exception as e:
            logger.warning("Nadi transport error: %s", e)
            return None
