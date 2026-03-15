"""MOKSHA Phase — Publish results.

1. Validate the research result
2. Write authority document (markdown + JSON)
3. Update inquiry ledger
4. Send real nadi messages to federation peers via GitHub API
5. Re-export authority feed
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from agent_research.models import (
    ConfidenceLevel,
    Inquiry,
    InquirySource,
    InquiryStatus,
    ResearchResult,
)
from agent_research.nadi import NadiTransport

logger = logging.getLogger(__name__)


class ResultValidator:
    """Validate research results before publication."""

    def validate(self, result: ResearchResult) -> list[str]:
        errors: list[str] = []
        if not result.title:
            errors.append("Missing title")
        if not result.abstract:
            errors.append("Missing abstract")
        if not result.findings:
            errors.append("No findings")
        if not result.faculties_involved:
            errors.append("No faculties listed")
        for f in result.findings:
            if not f.claim:
                errors.append(f"Finding {f.finding_id} has no claim")
        try:
            _ = result.content_hash
        except Exception as e:
            errors.append(f"Cannot compute content hash: {e}")
        return errors


class AuthorityDocumentWriter:
    """Write research results as authority documents."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.results_dir = repo_root / "docs" / "authority" / "research_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def write(self, result: ResearchResult) -> tuple[Path, Path]:
        safe_id = result.inquiry_id.replace("/", "_").replace(" ", "_")
        md_path = self.results_dir / f"{safe_id}.md"
        md_path.write_text(result.to_authority_document())
        logger.info("  Written: %s", md_path.relative_to(self.repo_root))

        json_path = self.results_dir / f"{safe_id}.json"
        json_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
        logger.info("  Written: %s", json_path.relative_to(self.repo_root))

        return md_path, json_path


class LedgerUpdater:
    """Update the inquiry ledger."""

    def __init__(self, repo_root: Path):
        self.ledger_path = repo_root / "data" / "inquiry_ledger.json"

    def update(self, inquiry: Inquiry, result: ResearchResult, md_path: Path, json_path: Path) -> None:
        ledger: dict[str, Any] = {}
        if self.ledger_path.exists():
            try:
                ledger = json.loads(self.ledger_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        ledger[inquiry.inquiry_id] = {
            **inquiry.to_dict(),
            "status": InquiryStatus.PUBLISHED.value,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "result_title": result.title,
            "result_confidence": result.overall_confidence.value,
            "result_content_hash": result.content_hash,
            "result_md_path": str(md_path),
            "result_json_path": str(json_path),
            "findings_count": len(result.findings),
            "faculties_involved": result.faculties_involved,
        }

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")


class FeedPublisher:
    """Re-export authority feed after new publications."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def publish(self) -> bool:
        export_script = self.repo_root / "scripts" / "export_authority_feed.py"
        if not export_script.exists():
            return False
        try:
            result = subprocess.run(
                [sys.executable, str(export_script), "--output-dir", ".authority-feed-out"],
                cwd=str(self.repo_root), capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                logger.info("  Authority feed re-exported")
                return True
            logger.error("  Feed export failed: %s", result.stderr)
            return False
        except Exception as e:
            logger.error("  Feed export error: %s", e)
            return False


class MokshaPhase:
    """MOKSHA: Publish and release.

    Validates, writes, tracks, notifies peers, re-exports feed.
    """

    def __init__(self, repo_root: Path, token: str | None = None):
        self.repo_root = repo_root
        self.validator = ResultValidator()
        self.writer = AuthorityDocumentWriter(repo_root)
        self.ledger = LedgerUpdater(repo_root)
        self.nadi = NadiTransport(token)
        self.publisher = FeedPublisher(repo_root)

    def run(self, inquiry: Inquiry, result: ResearchResult) -> bool:
        logger.info("MOKSHA: Publishing '%s'", result.title[:60])

        # 1. Validate
        errors = self.validator.validate(result)
        if errors:
            logger.error("  Validation failed: %s", errors)
            return False

        # 2. Write authority documents
        md_path, json_path = self.writer.write(result)

        # 3. Update ledger
        self.ledger.update(inquiry, result, md_path, json_path)
        inquiry.status = InquiryStatus.PUBLISHED

        # 4. Nadi: notify source node if this was a federation inquiry
        if inquiry.source == InquirySource.FEDERATION_INBOX and inquiry.source_node:
            doc_url = (f"https://github.com/kimeisele/agent-research/blob/main/"
                       f"docs/authority/research_results/{result.inquiry_id}.md")
            self.nadi.send_research_result(
                target_repo=inquiry.source_node,
                inquiry_id=inquiry.inquiry_id,
                title=result.title,
                abstract=result.abstract,
                confidence=result.overall_confidence.value,
                document_url=doc_url,
            )

        # 5. Re-export authority feed
        self.publisher.publish()

        logger.info("MOKSHA complete: '%s' (confidence: %s, hash: %s)",
                     result.title[:40], result.overall_confidence.value, result.content_hash[:12])
        return True
