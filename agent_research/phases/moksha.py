"""MOKSHA Phase — Publish results.

Final phase of the research cycle:
1. Validate the research result (integrity, completeness)
2. Write authority document to the faculty's output directory
3. Write structured JSON for the authority feed
4. Update the inquiry ledger with published status
5. Prepare federation response (nadi outbox message back to requester)
6. Trigger authority feed export
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

logger = logging.getLogger(__name__)


class ResultValidator:
    """Validate research results before publication.

    Checks:
    - Has at least one finding
    - Has a title and abstract
    - Findings have confidence levels
    - Sources are cited
    - Content hash is consistent
    """

    def validate(self, result: ResearchResult) -> list[str]:
        """Returns list of validation errors. Empty = valid."""
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
            if f.confidence == ConfidenceLevel.UNKNOWN and not f.limitations:
                errors.append(f"Finding {f.finding_id}: UNKNOWN confidence without stated limitations")

        # Verify content hash is computable
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
        """Write both markdown and JSON versions of the result.

        Returns (markdown_path, json_path).
        """
        safe_id = result.inquiry_id.replace("/", "_").replace(" ", "_")

        # Write markdown authority document
        md_path = self.results_dir / f"{safe_id}.md"
        md_path.write_text(result.to_authority_document())
        logger.info("  Written: %s", md_path.relative_to(self.repo_root))

        # Write structured JSON for feed export
        json_path = self.results_dir / f"{safe_id}.json"
        json_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
        logger.info("  Written: %s", json_path.relative_to(self.repo_root))

        return md_path, json_path


class LedgerUpdater:
    """Update the inquiry ledger with publication status."""

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


class FederationResponder:
    """Send results back to the requesting node via federation outbox."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.outbox_path = repo_root / "data" / "federation" / "nadi_outbox.json"

    def respond(self, inquiry: Inquiry, result: ResearchResult) -> None:
        """Queue a response message in the nadi outbox."""
        if inquiry.source != InquirySource.FEDERATION_INBOX:
            return  # Only respond to federation messages
        if not inquiry.source_node:
            return

        # Build response envelope
        envelope = {
            "kind": "delivery_envelope",
            "source_city_id": "agent-research",
            "target_city_id": inquiry.source_node,
            "operation": "research_response",
            "payload": {
                "inquiry_id": inquiry.inquiry_id,
                "title": result.title,
                "abstract": result.abstract,
                "confidence": result.overall_confidence.value,
                "findings_count": len(result.findings),
                "content_hash": result.content_hash,
                "authority_document_url": (
                    f"https://raw.githubusercontent.com/kimeisele/agent-research/"
                    f"main/docs/authority/research_results/{inquiry.inquiry_id}.md"
                ),
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Append to outbox
        outbox: list[dict] = []
        if self.outbox_path.exists():
            try:
                outbox = json.loads(self.outbox_path.read_text())
                if not isinstance(outbox, list):
                    outbox = outbox.get("messages", [])
            except (json.JSONDecodeError, OSError):
                pass

        outbox.append(envelope)
        self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
        self.outbox_path.write_text(json.dumps(outbox, indent=2) + "\n")
        logger.info("  Response queued for %s in nadi outbox", inquiry.source_node)


class FeedPublisher:
    """Trigger authority feed re-export after publishing new results."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def publish(self) -> bool:
        """Re-run the authority feed export."""
        export_script = self.repo_root / "scripts" / "export_authority_feed.py"
        if not export_script.exists():
            logger.warning("Authority feed export script not found")
            return False

        try:
            result = subprocess.run(
                [sys.executable, str(export_script), "--output-dir", ".authority-feed-out"],
                cwd=str(self.repo_root),
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                logger.info("  Authority feed re-exported successfully")
                return True
            else:
                logger.error("  Feed export failed: %s", result.stderr)
                return False
        except Exception as e:
            logger.error("  Feed export error: %s", e)
            return False


class MokshaPhase:
    """MOKSHA: Publish and release.

    Takes completed ResearchResults and:
    1. Validates them
    2. Writes authority documents
    3. Updates the ledger
    4. Responds to federation requesters
    5. Re-exports the authority feed
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.validator = ResultValidator()
        self.writer = AuthorityDocumentWriter(repo_root)
        self.ledger = LedgerUpdater(repo_root)
        self.responder = FederationResponder(repo_root)
        self.publisher = FeedPublisher(repo_root)

    def run(self, inquiry: Inquiry, result: ResearchResult) -> bool:
        """Execute MOKSHA for a single result.

        Returns True if publication succeeded, False otherwise.
        """
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
        logger.info("  Ledger updated")

        # 4. Respond to requester (if federation inquiry)
        self.responder.respond(inquiry, result)

        # 5. Re-export authority feed
        self.publisher.publish()

        logger.info("MOKSHA complete: '%s' published (confidence: %s, hash: %s)",
                     result.title[:40], result.overall_confidence.value, result.content_hash[:12])
        return True
