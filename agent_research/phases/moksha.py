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
from agent_research.knowledge import KnowledgeGraph
from agent_research.nadi import NadiTransport
from agent_research.peer_review import (
    PeerReviewRequester,
    PeerReviewScanner,
    PeerReviewProcessor,
    ReviewLedger,
)

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
        self.knowledge = KnowledgeGraph(repo_root / "data" / "knowledge_graph.json")
        self.review_requester = PeerReviewRequester(self.nadi)
        self.review_ledger = ReviewLedger(repo_root / "data" / "review_ledger.json")
        self.review_processor = PeerReviewProcessor(repo_root)
        self.review_scanner = PeerReviewScanner(self.nadi)

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

        # 5. Feed findings into knowledge graph
        for finding in result.findings:
            new_concepts = self.knowledge.ingest_finding(
                inquiry_id=result.inquiry_id,
                claim=finding.claim,
                evidence=finding.evidence,
                domains=result.faculties_involved,
                sources=finding.sources,
            )
            if new_concepts:
                logger.info("  Knowledge graph: +%d concepts", len(new_concepts))

        # Feed open questions back for future GENESIS
        for oq in result.open_questions:
            self.knowledge.ingest_open_question(
                question=oq,
                parent_inquiry=result.inquiry_id,
                domains=result.faculties_involved,
            )

        self.knowledge.save()
        kg_stats = self.knowledge.stats()
        logger.info("  Knowledge graph: %d concepts, %d edges, %d open questions",
                     kg_stats["concepts"], kg_stats["edges"], kg_stats["open_questions"])

        # 6. Process any incoming peer reviews from prior publications
        self._process_incoming_reviews()

        # 7. Request peer review from federation nodes
        peer_repos = self._get_review_peers(inquiry)
        if peer_repos:
            issued = self.review_requester.request_reviews(result, peer_repos)
            logger.info("  Peer review requested from %d nodes (%d issued)",
                        len(peer_repos), len(issued))

        self.review_ledger.save()

        # 8. Re-export authority feed
        self.publisher.publish()

        logger.info("MOKSHA complete: '%s' (confidence: %s, hash: %s)",
                     result.title[:40], result.overall_confidence.value, result.content_hash[:12])
        return True

    def _get_review_peers(self, inquiry: Inquiry) -> list[str]:
        """Determine which federation peers should review this result.

        Uses dynamic discovery via GitHub topic search to find all active
        federation nodes, then filters by relevance. Falls back to known
        founding nodes if discovery fails.
        """
        candidates: set[str] = set()

        # Dynamic discovery: find all repos tagged agent-federation-node
        try:
            discovered = self._discover_federation_peers()
            candidates.update(discovered)
        except Exception as e:
            logger.warning("  Peer discovery failed, using founding nodes: %s", e)
            # Fallback: founding nodes that are always part of the federation
            candidates = {"steward", "agent-world", "agent-city"}

        # Don't request review from the source node (they asked the question)
        if inquiry.source_node:
            candidates.discard(inquiry.source_node)

        # Don't request review from ourselves
        candidates.discard("agent-research")

        return list(candidates)

    def _discover_federation_peers(self) -> set[str]:
        """Discover federation peers via GitHub topic search.

        Searches for repos tagged 'agent-federation-node' owned by kimeisele.
        Returns repo names (not full paths) for nadi transport compatibility.
        """
        import urllib.request
        import json as _json

        token = self.nadi.token
        if not token:
            return set()

        url = (
            "https://api.github.com/search/repositories"
            "?q=topic:agent-federation-node+user:kimeisele+archived:false+fork:false"
            "&per_page=50&sort=updated"
        )
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())

        peers: set[str] = set()
        for item in data.get("items", []):
            name = item.get("name", "")
            if name and not item.get("archived"):
                peers.add(name)

        if peers:
            logger.info("  Discovered %d federation peers: %s", len(peers), sorted(peers))

        return peers

    def _process_incoming_reviews(self) -> None:
        """Scan for and process incoming peer reviews."""
        try:
            incoming = self.review_scanner.scan()
        except Exception as e:
            logger.warning("  Peer review scan failed: %s", e)
            return

        for review in incoming:
            # Skip if already in our ledger
            existing = self.review_ledger.get_reviews(review.inquiry_id)
            if any(r.review_id == review.review_id or
                   (r.reviewer_node == review.reviewer_node and
                    r.content_hash == review.content_hash)
                   for r in existing):
                continue

            self.review_ledger.add_review(review)
            result = self.review_processor.process(review)
            logger.info("  Processed peer review %s: %s (%s)",
                        review.review_id, review.verdict.value,
                        result.get("actions_taken", []))
