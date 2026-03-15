"""GENESIS Phase — Discover questions.

Sources:
1. Federation Inbox (nadi relay messages from other nodes)
2. GitHub Issues (labeled research-inquiry)
3. Mesh Observation (gaps/patterns detected in federation traffic)
4. Curiosity Engine (self-generated from cross-domain analysis)
5. Peer Challenges (challenges to existing published research)
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

from agent_research.knowledge import KnowledgeGraph
from agent_research.models import Inquiry, InquirySource, InquiryUrgency
from agent_research.peer_review import PeerReviewScanner, ReviewVerdict
from agent_research.nadi import NadiTransport

logger = logging.getLogger(__name__)

REPO_OWNER = "kimeisele"
REPO_NAME = "agent-research"


class InboxScanner:
    """Scan federation nadi inbox for research requests."""

    def __init__(self, data_dir: Path):
        self.inbox_path = data_dir / "federation" / "nadi_inbox.json"

    def scan(self) -> list[Inquiry]:
        if not self.inbox_path.exists():
            return []

        try:
            messages = json.loads(self.inbox_path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Cannot read nadi inbox at %s", self.inbox_path)
            return []

        inquiries = []
        for msg in messages if isinstance(messages, list) else messages.get("messages", []):
            if msg.get("operation") not in ("research_inquiry", "inquiry_request", "research_question"):
                continue
            payload = msg.get("payload", {})
            inquiry = Inquiry(
                question=payload.get("question", ""),
                context=payload.get("context", ""),
                source=InquirySource.FEDERATION_INBOX,
                source_node=msg.get("source_city_id", msg.get("source", "")),
                domains=payload.get("domains", []),
                urgency=InquiryUrgency(payload.get("urgency", "standard")),
                metadata={"envelope_id": msg.get("envelope_id", ""), "raw": msg},
            )
            if inquiry.question:
                inquiries.append(inquiry)

        return inquiries


class IssueScanner:
    """Scan GitHub issues for research inquiries."""

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    def _github_api(self, path: str) -> Any:
        if not self.token:
            return []
        req = urllib.request.Request(
            f"https://api.github.com{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("GitHub API error: %s", e)
            return []

    def scan(self) -> list[Inquiry]:
        issues = self._github_api(
            f"/repos/{REPO_OWNER}/{REPO_NAME}/issues?labels=research-inquiry&state=open&per_page=50"
        )
        if not isinstance(issues, list):
            return []

        inquiries = []
        for issue in issues:
            body = issue.get("body", "") or ""
            # Parse structured inquiry from issue body
            question = issue.get("title", "")
            domains = [
                label["name"].removeprefix("faculty:")
                for label in issue.get("labels", [])
                if label.get("name", "").startswith("faculty:")
            ]
            urgency = InquiryUrgency.STANDARD
            for label in issue.get("labels", []):
                name = label.get("name", "")
                if name == "urgency:elevated":
                    urgency = InquiryUrgency.ELEVATED
                elif name == "urgency:critical":
                    urgency = InquiryUrgency.CRITICAL

            inquiry = Inquiry(
                inquiry_id=f"gh-{issue['number']}",
                question=question,
                context=body,
                source=InquirySource.GITHUB_ISSUE,
                source_node=issue.get("user", {}).get("login", ""),
                domains=domains,
                urgency=urgency,
                metadata={"issue_number": issue["number"], "issue_url": issue.get("html_url", "")},
            )
            inquiries.append(inquiry)

        return inquiries


class MeshObserver:
    """Observe federation mesh for implicit research opportunities.

    Detects:
    - Authority documents from other nodes that reference unknown concepts
    - Gaps between what nodes produce and what they consume
    - Failed relay messages that indicate missing capabilities
    - Patterns across node descriptors suggesting unserved needs
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.observations_path = data_dir / "mesh_observations.json"

    def scan(self) -> list[Inquiry]:
        # Read federation state for gap analysis
        state_path = self.data_dir / "federation" / "state.json"
        if not state_path.exists():
            return []

        try:
            state = json.loads(state_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []

        inquiries = []

        # Detect capability gaps: things nodes consume but nobody produces
        all_produces: set[str] = set()
        all_consumes: set[str] = set()
        for feed in state.get("source_authority_feeds", []):
            labels = feed.get("labels", {})
            # Accumulate what the network offers vs needs
            all_produces.update(labels.get("produces", []))
            all_consumes.update(labels.get("consumes", []))

        gaps = all_consumes - all_produces
        for gap in gaps:
            inquiries.append(Inquiry(
                question=f"What is '{gap}' and how should the federation provide it?",
                context=f"Detected capability gap: '{gap}' is consumed by federation nodes but no node produces it.",
                source=InquirySource.MESH_OBSERVATION,
                domains=["computation-intelligence"],
                metadata={"gap_type": "capability", "capability": gap},
            ))

        return inquiries


class KnowledgeGraphScanner:
    """Scan the knowledge graph for unanswered questions from prior research.

    This is how the Faculty REMEMBERS: questions that emerged from previous
    research become new inquiries. The research feeds itself.
    """

    def __init__(self, knowledge: KnowledgeGraph):
        self.knowledge = knowledge

    def scan(self) -> list[Inquiry]:
        inquiries = []
        for oq in self.knowledge.get_unanswered_questions():
            inquiries.append(Inquiry(
                question=oq.question,
                context=f"Emerged from prior research (inquiry {oq.parent_inquiry})",
                source=InquirySource.CURIOSITY,
                domains=oq.domains,
                urgency=InquiryUrgency.STANDARD,
                metadata={"origin": "knowledge_graph", "parent_inquiry": oq.parent_inquiry},
            ))
        return inquiries


class CuriosityEngine:
    """Generate research questions from cross-domain analysis.

    Reads existing authority documents and identifies:
    - Claims that could be tested across domains
    - Analogies between different faculty areas
    - Open questions from published research
    - Emerging patterns that deserve deeper investigation
    """

    def __init__(self, docs_dir: Path):
        self.docs_dir = docs_dir

    def scan(self) -> list[Inquiry]:
        inquiries = []

        # Read published research results for open questions
        results_dir = self.docs_dir / "authority" / "research_results"
        if results_dir.exists():
            for result_file in results_dir.glob("*.json"):
                try:
                    result = json.loads(result_file.read_text())
                except (json.JSONDecodeError, OSError):
                    continue

                for oq in result.get("open_questions", []):
                    inquiries.append(Inquiry(
                        question=oq,
                        context=f"Open question from prior research: {result.get('title', result_file.stem)}",
                        source=InquirySource.CURIOSITY,
                        domains=result.get("faculties_involved", []),
                        metadata={"parent_inquiry": result.get("inquiry_id", ""), "origin": "open_question"},
                    ))

        # Read faculty briefs for explicit research priorities
        faculties_dir = self.docs_dir / "authority" / "faculties"
        if faculties_dir.exists():
            for faculty_dir in faculties_dir.iterdir():
                if not faculty_dir.is_dir():
                    continue
                brief_path = faculty_dir / "00-faculty-brief.md"
                if not brief_path.exists():
                    continue
                body = brief_path.read_text()
                # Extract questions from "Core Questions" section
                in_questions = False
                for line in body.splitlines():
                    if "Core Questions" in line:
                        in_questions = True
                        continue
                    if in_questions and line.startswith("## "):
                        break
                    if in_questions and line.startswith("1. **") or (in_questions and line.startswith("2. **")) or (in_questions and line.startswith("3. **")) or (in_questions and line.startswith("4. **")):
                        q = line.split("**")[1] if "**" in line else line
                        inquiries.append(Inquiry(
                            question=q.strip("*").strip(),
                            context=f"Core question from {faculty_dir.name} faculty brief",
                            source=InquirySource.CURIOSITY,
                            domains=[faculty_dir.name],
                            metadata={"origin": "faculty_brief", "faculty": faculty_dir.name},
                        ))

        return inquiries


class PeerChallengeScanner:
    """Scan incoming peer reviews for research challenges.

    When a peer challenges or refutes our findings, that becomes
    a new research inquiry. The challenged claim needs re-investigation.
    """

    def __init__(self, token: str | None = None):
        self.scanner = PeerReviewScanner(NadiTransport(token))

    def scan(self) -> list[Inquiry]:
        try:
            reviews = self.scanner.scan()
        except Exception as e:
            logger.warning("Peer challenge scan failed: %s", e)
            return []

        inquiries = []
        for review in reviews:
            # Only challenges and refutations generate new inquiries
            if review.verdict not in (ReviewVerdict.CHALLENGE, ReviewVerdict.REFUTE):
                continue

            for challenge in review.challenges:
                inquiries.append(Inquiry(
                    question=f"Re-examine: {challenge}",
                    context=(
                        f"Peer review from {review.reviewer_node} "
                        f"({review.verdict.value}) of inquiry {review.inquiry_id}: "
                        f"{review.summary}"
                    ),
                    source=InquirySource.PEER_CHALLENGE,
                    source_node=review.reviewer_node,
                    domains=[],
                    urgency=InquiryUrgency.ELEVATED,
                    metadata={
                        "review_id": review.review_id,
                        "original_inquiry": review.inquiry_id,
                        "verdict": review.verdict.value,
                        "counter_evidence": review.counter_evidence,
                    },
                ))

            # If refutation but no specific challenges, create one general inquiry
            if review.verdict == ReviewVerdict.REFUTE and not review.challenges:
                inquiries.append(Inquiry(
                    question=f"Re-examine findings of {review.inquiry_id}: {review.summary}",
                    context=(
                        f"Peer refutation from {review.reviewer_node}. "
                        f"Counter-evidence: {'; '.join(review.counter_evidence)}"
                    ),
                    source=InquirySource.PEER_CHALLENGE,
                    source_node=review.reviewer_node,
                    urgency=InquiryUrgency.ELEVATED,
                    metadata={
                        "review_id": review.review_id,
                        "original_inquiry": review.inquiry_id,
                    },
                ))

        return inquiries


class GenesisPhase:
    """GENESIS: Discover all pending research questions.

    Scans all sources, deduplicates, and returns a prioritized queue.
    Zero LLM. Pure observation and collection.
    """

    def __init__(self, repo_root: Path, token: str | None = None):
        self.repo_root = repo_root
        self.data_dir = repo_root / "data"
        self.docs_dir = repo_root / "docs"
        self.knowledge = KnowledgeGraph(self.data_dir / "knowledge_graph.json")
        self.scanners = [
            InboxScanner(self.data_dir),
            IssueScanner(token),
            MeshObserver(self.data_dir),
            PeerChallengeScanner(token),
            KnowledgeGraphScanner(self.knowledge),
            CuriosityEngine(self.docs_dir),
        ]
        self.ledger_path = self.data_dir / "inquiry_ledger.json"

    def _load_ledger(self) -> dict[str, dict]:
        """Load the inquiry ledger — tracks what we've already seen."""
        if self.ledger_path.exists():
            try:
                return json.loads(self.ledger_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_ledger(self, ledger: dict[str, dict]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(ledger, indent=2) + "\n")

    def _deduplicate(self, inquiries: list[Inquiry], ledger: dict[str, dict]) -> list[Inquiry]:
        """Remove already-processed or duplicate inquiries."""
        seen_questions: set[str] = set()
        unique: list[Inquiry] = []
        for inq in inquiries:
            # Skip if already in ledger and not re-opened
            if inq.inquiry_id in ledger:
                existing = ledger[inq.inquiry_id]
                if existing.get("status") in ("published", "archived"):
                    continue
            # Skip duplicate questions within this batch
            q_norm = inq.question.lower().strip()
            if q_norm in seen_questions:
                continue
            seen_questions.add(q_norm)
            unique.append(inq)
        return unique

    def _prioritize(self, inquiries: list[Inquiry]) -> list[Inquiry]:
        """Sort by urgency, then by source priority."""
        source_priority = {
            InquirySource.FEDERATION_INBOX: 0,
            InquirySource.PEER_CHALLENGE: 1,
            InquirySource.GITHUB_ISSUE: 2,
            InquirySource.MESH_OBSERVATION: 3,
            InquirySource.CURIOSITY: 4,
        }
        urgency_priority = {
            InquiryUrgency.CRITICAL: 0,
            InquiryUrgency.ELEVATED: 1,
            InquiryUrgency.STANDARD: 2,
        }
        return sorted(inquiries, key=lambda i: (
            urgency_priority.get(i.urgency, 9),
            source_priority.get(i.source, 9),
        ))

    def run(self) -> list[Inquiry]:
        """Execute GENESIS: scan all sources, deduplicate, prioritize.

        Returns prioritized list of new inquiries ready for DHARMA.
        """
        logger.info("GENESIS: Scanning for research inquiries...")
        ledger = self._load_ledger()

        all_inquiries: list[Inquiry] = []
        for scanner in self.scanners:
            name = type(scanner).__name__
            try:
                found = scanner.scan()
                logger.info("  %s: %d inquiries", name, len(found))
                all_inquiries.extend(found)
            except Exception as e:
                logger.error("  %s: scan failed: %s", name, e)

        # Deduplicate and prioritize
        unique = self._deduplicate(all_inquiries, ledger)
        prioritized = self._prioritize(unique)

        # Register new inquiries in ledger
        for inq in prioritized:
            if inq.inquiry_id not in ledger:
                ledger[inq.inquiry_id] = inq.to_dict()
        self._save_ledger(ledger)

        logger.info("GENESIS complete: %d new inquiries (from %d total scanned)",
                     len(prioritized), len(all_inquiries))
        return prioritized
