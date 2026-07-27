"""Tests for PeerReviewRequester dedup integration."""
import tempfile
from pathlib import Path

from agent_research.peer_review import (
    DeliveryLedger,
    PeerReviewRequester,
    ReviewVerdict,
)
from agent_research.models import (
    ConfidenceLevel,
    Finding,
    ResearchResult,
    MethodologyType,
)


def _make_result(inquiry_id: str = "inq-001", title: str = "Test Inquiry") -> ResearchResult:
    return ResearchResult(
        inquiry_id=inquiry_id,
        title=title,
        abstract="A test abstract.",
        findings=[
            Finding(
                claim="Test claim",
                evidence=["some evidence"],
                confidence=ConfidenceLevel.SUPPORTED,
            )
        ],
        methodology_used=MethodologyType.DATA_ANALYSIS,
        faculties_involved=["computation-intelligence"],
    )


class _FakeNadi:
    """Fake NadiTransport that records calls instead of creating real issues."""

    def __init__(self):
        self.created_issues: list[dict] = []

    def _create_issue(self, repo, title, body, labels=None):
        self.created_issues.append({
            "repo": repo,
            "title": title,
            "labels": labels or [],
        })
        return {"number": len(self.created_issues)}


class TestPeerReviewRequesterDedup:
    def test_first_send_creates_issue(self):
        nadi = _FakeNadi()
        requester = PeerReviewRequester(nadi)
        result = _make_result()

        results = requester.request_reviews(result, ["hermes-sankhya-25"])
        assert len(results) == 1
        assert len(nadi.created_issues) == 1

    def test_send_with_ledger_records_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "delivery.json"
            ledger = DeliveryLedger(ledger_path)

            nadi = _FakeNadi()
            requester = PeerReviewRequester(nadi, delivery_ledger=ledger)
            result = _make_result()

            requester.request_reviews(result, ["hermes-sankhya-25"])
            assert ledger.has_been_delivered("hermes-sankhya-25", "inq-001")

    def test_second_send_is_noop(self):
        """Repeated heartbeat runs must not create duplicate issues."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "delivery.json"
            ledger = DeliveryLedger(ledger_path)

            nadi = _FakeNadi()
            requester = PeerReviewRequester(nadi, delivery_ledger=ledger)
            result = _make_result()

            # First call — should create
            results1 = requester.request_reviews(result, ["hermes-sankhya-25"])
            assert len(results1) == 1
            assert len(nadi.created_issues) == 1

            # Second call — should be skipped (NOOP)
            results2 = requester.request_reviews(result, ["hermes-sankhya-25"])
            assert len(results2) == 0
            assert len(nadi.created_issues) == 1  # No new issue

    def test_different_inquiry_still_creates(self):
        """A new inquiry must still create an issue."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "delivery.json"
            ledger = DeliveryLedger(ledger_path)

            nadi = _FakeNadi()
            requester = PeerReviewRequester(nadi, delivery_ledger=ledger)

            requester.request_reviews(_make_result("inq-001"), ["hermes-sankhya-25"])
            results = requester.request_reviews(_make_result("inq-002"), ["hermes-sankhya-25"])
            assert len(results) == 1
            assert len(nadi.created_issues) == 2

    def test_different_repo_still_creates(self):
        """Same inquiry to a different repo must still create an issue."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "delivery.json"
            ledger = DeliveryLedger(ledger_path)

            nadi = _FakeNadi()
            requester = PeerReviewRequester(nadi, delivery_ledger=ledger)
            result = _make_result()

            requester.request_reviews(result, ["hermes-sankhya-25"])
            results = requester.request_reviews(result, ["steward-federation"])
            assert len(results) == 1
            assert len(nadi.created_issues) == 2

    def test_without_ledger_behaves_as_before(self):
        """Without a ledger, dedup is not applied (backward compatible)."""
        nadi = _FakeNadi()
        requester = PeerReviewRequester(nadi)
        result = _make_result()

        requester.request_reviews(result, ["hermes-sankhya-25"])
        requester.request_reviews(result, ["hermes-sankhya-25"])
        requester.request_reviews(result, ["hermes-sankhya-25"])
        assert len(nadi.created_issues) == 3

    def test_persisted_ledger_survives_heartbeat_reruns(self):
        """A ledger saved to disk survives between heartbeat runs."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "delivery.json"

            # Simulate first heartbeat run
            ledger1 = DeliveryLedger(ledger_path)
            nadi1 = _FakeNadi()
            requester1 = PeerReviewRequester(nadi1, delivery_ledger=ledger1)
            requester1.request_reviews(_make_result("inq-001"), ["hermes-sankhya-25"])
            requester1.request_reviews(_make_result("inq-002"), ["hermes-sankhya-25"])
            ledger1.save()

            # Simulate second heartbeat run (fresh DeliveryLedger from disk)
            ledger2 = DeliveryLedger(ledger_path)
            nadi2 = _FakeNadi()
            requester2 = PeerReviewRequester(nadi2, delivery_ledger=ledger2)
            requester2.request_reviews(_make_result("inq-001"), ["hermes-sankhya-25"])
            requester2.request_reviews(_make_result("inq-002"), ["hermes-sankhya-25"])

            # No new issues created — both were already delivered
            assert len(nadi2.created_issues) == 0
