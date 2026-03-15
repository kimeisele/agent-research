"""Peer Review — federation-based research validation.

When agent-research publishes a result, it SHOULD be challenged.
This module enables:

1. Requesting reviews from federation peers (via GitHub Issues)
2. Processing incoming review challenges
3. Tracking review state per publication
4. Incorporating feedback into the knowledge graph

A peer review is a GitHub issue on agent-research created by another
federation node (or by a human). It references a published result and
contains structured feedback: endorsement, challenge, or extension.

Protocol:
- MOKSHA publishes result → creates review-request issues on peer repos
- Peer reads result, posts review issue on agent-research
- GENESIS picks up review issues (source=PEER_CHALLENGE)
- Review is processed: knowledge graph updated, result confidence adjusted

This is how the network keeps itself honest.
"""
from __future__ import annotations

import enum
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_research.models import ConfidenceLevel, ResearchResult
from agent_research.nadi import NadiTransport

logger = logging.getLogger(__name__)


class ReviewVerdict(enum.Enum):
    """What the reviewer concluded."""
    ENDORSE = "endorse"          # Findings confirmed / well-supported
    CHALLENGE = "challenge"      # Specific findings disputed
    EXTEND = "extend"            # Findings accepted but additional insight offered
    REFUTE = "refute"            # Core claim rejected with counter-evidence
    ABSTAIN = "abstain"          # Unable to evaluate (outside expertise)


class ReviewStatus(enum.Enum):
    """Lifecycle of a peer review."""
    REQUESTED = "requested"      # Review request sent to peer
    PENDING = "pending"          # Awaiting peer response
    RECEIVED = "received"        # Review received, not yet processed
    PROCESSED = "processed"      # Review incorporated
    DISMISSED = "dismissed"      # Review rejected (insufficient basis)


@dataclass
class PeerReview:
    """A single peer review of a published result."""
    review_id: str = field(default_factory=lambda: f"rv-{uuid.uuid4().hex[:10]}")
    inquiry_id: str = ""                    # Which result this reviews
    content_hash: str = ""                  # Hash of the result being reviewed
    reviewer_node: str = ""                 # Which federation node reviewed
    reviewer_identity: str = ""             # GitHub user or node identifier
    verdict: ReviewVerdict = ReviewVerdict.ABSTAIN
    summary: str = ""                       # Reviewer's summary
    challenges: list[str] = field(default_factory=list)   # Specific challenged claims
    supporting_evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    confidence_adjustment: int = 0          # -2 to +2 suggested adjustment
    status: ReviewStatus = ReviewStatus.RECEIVED
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "inquiry_id": self.inquiry_id,
            "content_hash": self.content_hash,
            "reviewer_node": self.reviewer_node,
            "reviewer_identity": self.reviewer_identity,
            "verdict": self.verdict.value,
            "summary": self.summary,
            "challenges": self.challenges,
            "supporting_evidence": self.supporting_evidence,
            "counter_evidence": self.counter_evidence,
            "suggestions": self.suggestions,
            "confidence_adjustment": self.confidence_adjustment,
            "status": self.status.value,
            "received_at": self.received_at,
            "processed_at": self.processed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PeerReview:
        return cls(
            review_id=d.get("review_id", f"rv-{uuid.uuid4().hex[:10]}"),
            inquiry_id=d.get("inquiry_id", ""),
            content_hash=d.get("content_hash", ""),
            reviewer_node=d.get("reviewer_node", ""),
            reviewer_identity=d.get("reviewer_identity", ""),
            verdict=ReviewVerdict(d.get("verdict", "abstain")),
            summary=d.get("summary", ""),
            challenges=d.get("challenges", []),
            supporting_evidence=d.get("supporting_evidence", []),
            counter_evidence=d.get("counter_evidence", []),
            suggestions=d.get("suggestions", []),
            confidence_adjustment=d.get("confidence_adjustment", 0),
            status=ReviewStatus(d.get("status", "received")),
            received_at=d.get("received_at", ""),
            processed_at=d.get("processed_at", ""),
            metadata=d.get("metadata", {}),
        )


class ReviewLedger:
    """Persistent store for peer reviews.

    Tracks all reviews received and requested, keyed by inquiry_id.
    """

    def __init__(self, path: Path):
        self.path = path
        self.reviews: dict[str, list[PeerReview]] = {}  # inquiry_id → reviews
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            for inquiry_id, review_list in data.get("reviews", {}).items():
                self.reviews[inquiry_id] = [PeerReview.from_dict(r) for r in review_list]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Review ledger load failed: %s", e)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "reviews": {
                iid: [r.to_dict() for r in reviews]
                for iid, reviews in self.reviews.items()
            },
            "meta": {
                "total_reviews": sum(len(v) for v in self.reviews.values()),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        }
        self.path.write_text(json.dumps(data, indent=2) + "\n")

    def add_review(self, review: PeerReview) -> None:
        self.reviews.setdefault(review.inquiry_id, []).append(review)

    def get_reviews(self, inquiry_id: str) -> list[PeerReview]:
        return self.reviews.get(inquiry_id, [])

    def get_unprocessed(self) -> list[PeerReview]:
        unprocessed = []
        for reviews in self.reviews.values():
            for r in reviews:
                if r.status == ReviewStatus.RECEIVED:
                    unprocessed.append(r)
        return unprocessed

    def get_review_summary(self, inquiry_id: str) -> dict[str, Any]:
        """Aggregate review state for a published result."""
        reviews = self.get_reviews(inquiry_id)
        if not reviews:
            return {"status": "unreviewed", "review_count": 0}

        verdicts = [r.verdict for r in reviews if r.status == ReviewStatus.PROCESSED]
        endorsements = sum(1 for v in verdicts if v == ReviewVerdict.ENDORSE)
        challenges = sum(1 for v in verdicts if v in (ReviewVerdict.CHALLENGE, ReviewVerdict.REFUTE))
        extensions = sum(1 for v in verdicts if v == ReviewVerdict.EXTEND)

        avg_adjustment = 0.0
        adjustments = [r.confidence_adjustment for r in reviews if r.status == ReviewStatus.PROCESSED]
        if adjustments:
            avg_adjustment = sum(adjustments) / len(adjustments)

        return {
            "status": "reviewed",
            "review_count": len(reviews),
            "processed": sum(1 for r in reviews if r.status == ReviewStatus.PROCESSED),
            "endorsements": endorsements,
            "challenges": challenges,
            "extensions": extensions,
            "avg_confidence_adjustment": round(avg_adjustment, 2),
            "all_challenges": [c for r in reviews for c in r.challenges],
            "all_suggestions": [s for r in reviews for s in r.suggestions],
        }


class PeerReviewRequester:
    """Request peer review from federation nodes.

    After MOKSHA publishes, this creates review-request issues on
    peer repos. The peer's agent reads the result and posts a review
    back on agent-research.
    """

    def __init__(self, nadi: NadiTransport):
        self.nadi = nadi

    def request_reviews(self, result: ResearchResult, peer_repos: list[str]) -> list[dict]:
        """Send review requests to peer nodes.

        Creates an issue on each peer repo with the result summary
        and a link to the full document.
        """
        doc_url = (
            f"https://github.com/kimeisele/agent-research/blob/main/"
            f"docs/authority/research_results/{result.inquiry_id}.md"
        )
        json_url = (
            f"https://github.com/kimeisele/agent-research/blob/main/"
            f"docs/authority/research_results/{result.inquiry_id}.json"
        )

        body = (
            f"## Peer Review Request from agent-research\n\n"
            f"**Inquiry ID:** {result.inquiry_id}\n"
            f"**Title:** {result.title}\n"
            f"**Confidence:** {result.overall_confidence.value}\n"
            f"**Content Hash:** `{result.content_hash}`\n"
            f"**Faculties:** {', '.join(result.faculties_involved)}\n\n"
            f"### Abstract\n{result.abstract}\n\n"
            f"### Key Findings ({len(result.findings)})\n"
        )

        for f in result.findings[:5]:
            body += f"- **[{f.confidence.value}]** {f.claim}\n"

        if result.open_questions:
            body += f"\n### Open Questions\n"
            for q in result.open_questions[:3]:
                body += f"- {q}\n"

        body += (
            f"\n### Review Protocol\n"
            f"To review this result, create an issue on "
            f"[agent-research](https://github.com/kimeisele/agent-research/issues/new) "
            f"with the label `peer-review` and include:\n\n"
            f"```json\n"
            f'{{\n'
            f'  "inquiry_id": "{result.inquiry_id}",\n'
            f'  "content_hash": "{result.content_hash}",\n'
            f'  "verdict": "endorse|challenge|extend|refute|abstain",\n'
            f'  "summary": "Your review summary",\n'
            f'  "challenges": ["specific claims you dispute"],\n'
            f'  "counter_evidence": ["evidence against findings"],\n'
            f'  "supporting_evidence": ["evidence supporting findings"],\n'
            f'  "suggestions": ["improvements or extensions"],\n'
            f'  "confidence_adjustment": 0\n'
            f'}}\n'
            f"```\n\n"
            f"**Full document:** {doc_url}\n"
            f"**Machine-readable:** {json_url}\n\n"
            f"---\n"
            f"*Sent by Research Engine & Faculty via Nadi Transport*\n"
            f"*{datetime.now(timezone.utc).isoformat()}*"
        )

        results = []
        for repo in peer_repos:
            result_data = self.nadi._create_issue(
                repo=f"kimeisele/{repo}",
                title=f"[review-request] {result.title[:70]}",
                body=body,
                labels=["review-request", "federation-nadi"],
            )
            if result_data:
                results.append(result_data)
                logger.info("  Review requested from %s (issue #%s)",
                           repo, result_data.get("number", "?"))
        return results


class PeerReviewScanner:
    """Scan for incoming peer reviews on our repo.

    Reads GitHub issues labeled 'peer-review' on agent-research.
    Parses the structured review data and creates PeerReview objects.
    Used by GENESIS to pick up incoming challenges.
    """

    def __init__(self, nadi: NadiTransport):
        self.nadi = nadi

    def scan(self) -> list[PeerReview]:
        """Fetch and parse peer review issues."""
        issues = self.nadi._api(
            "/repos/kimeisele/agent-research/issues?labels=peer-review&state=open&per_page=50"
        )
        if not isinstance(issues, list):
            return []

        reviews = []
        for issue in issues:
            review = self._parse_review_issue(issue)
            if review:
                reviews.append(review)
        return reviews

    def _parse_review_issue(self, issue: dict) -> PeerReview | None:
        """Extract structured review data from a GitHub issue."""
        body = issue.get("body", "") or ""

        # Try to find JSON block in the issue body
        review_data = _extract_json_from_body(body)
        if not review_data:
            return None

        inquiry_id = review_data.get("inquiry_id", "")
        if not inquiry_id:
            return None

        try:
            verdict = ReviewVerdict(review_data.get("verdict", "abstain"))
        except ValueError:
            verdict = ReviewVerdict.ABSTAIN

        return PeerReview(
            inquiry_id=inquiry_id,
            content_hash=review_data.get("content_hash", ""),
            reviewer_node=issue.get("user", {}).get("login", ""),
            reviewer_identity=issue.get("user", {}).get("login", ""),
            verdict=verdict,
            summary=review_data.get("summary", issue.get("title", "")),
            challenges=review_data.get("challenges", []),
            supporting_evidence=review_data.get("supporting_evidence", []),
            counter_evidence=review_data.get("counter_evidence", []),
            suggestions=review_data.get("suggestions", []),
            confidence_adjustment=int(review_data.get("confidence_adjustment", 0)),
            metadata={
                "issue_number": issue.get("number"),
                "issue_url": issue.get("html_url", ""),
            },
        )


class PeerReviewProcessor:
    """Process received peer reviews.

    Takes a review, validates it against the published result,
    and updates the knowledge graph accordingly.

    Processing rules:
    - ENDORSE: Boost confidence of confirmed findings
    - CHALLENGE: Flag challenged claims, record counter-evidence
    - EXTEND: Add new edges/concepts from extensions
    - REFUTE: Record counter-evidence, lower confidence
    - ABSTAIN: No action
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.results_dir = repo_root / "docs" / "authority" / "research_results"

    def process(self, review: PeerReview) -> dict[str, Any]:
        """Process a single peer review.

        Returns a summary of actions taken.
        """
        actions: dict[str, Any] = {
            "review_id": review.review_id,
            "verdict": review.verdict.value,
            "actions_taken": [],
        }

        # Validate: does the reviewed result exist?
        result_path = self.results_dir / f"{review.inquiry_id}.json"
        if not result_path.exists():
            actions["error"] = f"Result {review.inquiry_id} not found"
            review.status = ReviewStatus.DISMISSED
            return actions

        try:
            result_data = json.loads(result_path.read_text())
        except (json.JSONDecodeError, OSError):
            actions["error"] = f"Cannot read result {review.inquiry_id}"
            review.status = ReviewStatus.DISMISSED
            return actions

        # Validate content hash if provided
        if review.content_hash and review.content_hash != result_data.get("content_hash", ""):
            actions["warning"] = "Content hash mismatch — result may have been updated since review"

        # Process based on verdict
        if review.verdict == ReviewVerdict.ENDORSE:
            actions["actions_taken"].append("Endorsement recorded")
            actions["confidence_impact"] = "positive"

        elif review.verdict == ReviewVerdict.CHALLENGE:
            actions["actions_taken"].append(f"Challenges recorded: {len(review.challenges)}")
            actions["challenged_claims"] = review.challenges
            actions["confidence_impact"] = "negative"

        elif review.verdict == ReviewVerdict.EXTEND:
            actions["actions_taken"].append("Extension recorded")
            actions["new_evidence"] = review.supporting_evidence
            actions["confidence_impact"] = "neutral"

        elif review.verdict == ReviewVerdict.REFUTE:
            actions["actions_taken"].append("Refutation recorded")
            actions["counter_evidence"] = review.counter_evidence
            actions["confidence_impact"] = "strongly_negative"

        else:
            actions["actions_taken"].append("Abstention — no action taken")
            actions["confidence_impact"] = "none"

        # Write review annotation to the result
        annotations = result_data.get("peer_reviews", [])
        annotations.append({
            "review_id": review.review_id,
            "reviewer": review.reviewer_node,
            "verdict": review.verdict.value,
            "summary": review.summary,
            "confidence_adjustment": review.confidence_adjustment,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        })
        result_data["peer_reviews"] = annotations

        # Update aggregate review score
        all_adjustments = [a["confidence_adjustment"] for a in annotations]
        result_data["review_score"] = {
            "total_reviews": len(annotations),
            "avg_adjustment": round(sum(all_adjustments) / len(all_adjustments), 2) if all_adjustments else 0,
            "endorsements": sum(1 for a in annotations if a["verdict"] == "endorse"),
            "challenges": sum(1 for a in annotations if a["verdict"] in ("challenge", "refute")),
        }

        # Write back
        result_path.write_text(json.dumps(result_data, indent=2) + "\n")
        actions["actions_taken"].append("Result annotated with review")

        review.status = ReviewStatus.PROCESSED
        review.processed_at = datetime.now(timezone.utc).isoformat()
        return actions


def _extract_json_from_body(body: str) -> dict | None:
    """Extract a JSON block from a GitHub issue body."""
    import re

    # Try code block first
    match = re.search(r'```(?:json)?\s*\n(.*?)\n```', body, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try raw JSON
    start = body.find("{")
    end = body.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(body[start:end])
        except json.JSONDecodeError:
            pass

    return None
