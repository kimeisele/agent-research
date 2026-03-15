"""Tests for Peer Review mechanism."""
import json
import tempfile
from pathlib import Path

from agent_research.peer_review import (
    PeerReview,
    PeerReviewProcessor,
    ReviewLedger,
    ReviewStatus,
    ReviewVerdict,
    _extract_json_from_body,
)
from agent_research.models import (
    ConfidenceLevel,
    Finding,
    ResearchResult,
    MethodologyType,
)


def _make_review(**kwargs) -> PeerReview:
    defaults = dict(
        review_id="rv-test001",
        inquiry_id="test-inq-001",
        content_hash="abc123",
        reviewer_node="steward",
        reviewer_identity="kimeisele",
        verdict=ReviewVerdict.ENDORSE,
        summary="Findings well-supported",
    )
    defaults.update(kwargs)
    return PeerReview(**defaults)


def _make_published_result(results_dir: Path) -> None:
    """Write a fake published result for the processor to find."""
    result = {
        "inquiry_id": "test-inq-001",
        "title": "Test Result",
        "abstract": "Test abstract.",
        "findings": [{"claim": "Test claim", "evidence": ["evidence"], "confidence": "supported"}],
        "content_hash": "abc123",
        "overall_confidence": "supported",
        "faculties_involved": ["computation-intelligence"],
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "test-inq-001.json").write_text(json.dumps(result, indent=2))


# ── PeerReview Model ──


def test_review_to_dict_roundtrip():
    review = _make_review(
        challenges=["claim A is wrong"],
        counter_evidence=["evidence X"],
    )
    d = review.to_dict()
    restored = PeerReview.from_dict(d)
    assert restored.review_id == review.review_id
    assert restored.verdict == ReviewVerdict.ENDORSE
    assert restored.challenges == ["claim A is wrong"]


def test_review_verdict_values():
    assert ReviewVerdict.ENDORSE.value == "endorse"
    assert ReviewVerdict.CHALLENGE.value == "challenge"
    assert ReviewVerdict.REFUTE.value == "refute"
    assert ReviewVerdict.EXTEND.value == "extend"
    assert ReviewVerdict.ABSTAIN.value == "abstain"


# ── ReviewLedger ──


def test_ledger_save_load():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "review_ledger.json"
        ledger = ReviewLedger(path)
        assert len(ledger.reviews) == 0

        review = _make_review()
        ledger.add_review(review)
        assert len(ledger.get_reviews("test-inq-001")) == 1

        ledger.save()
        assert path.exists()

        # Reload
        ledger2 = ReviewLedger(path)
        assert len(ledger2.get_reviews("test-inq-001")) == 1
        restored = ledger2.get_reviews("test-inq-001")[0]
        assert restored.reviewer_node == "steward"


def test_ledger_unprocessed():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "review_ledger.json"
        ledger = ReviewLedger(path)

        r1 = _make_review(review_id="rv-1", status=ReviewStatus.RECEIVED)
        r2 = _make_review(review_id="rv-2", status=ReviewStatus.PROCESSED)
        ledger.add_review(r1)
        ledger.add_review(r2)

        unprocessed = ledger.get_unprocessed()
        assert len(unprocessed) == 1
        assert unprocessed[0].review_id == "rv-1"


def test_ledger_review_summary():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "review_ledger.json"
        ledger = ReviewLedger(path)

        ledger.add_review(_make_review(
            review_id="rv-1", verdict=ReviewVerdict.ENDORSE,
            status=ReviewStatus.PROCESSED, confidence_adjustment=1,
        ))
        ledger.add_review(_make_review(
            review_id="rv-2", verdict=ReviewVerdict.CHALLENGE,
            status=ReviewStatus.PROCESSED, confidence_adjustment=-1,
            challenges=["claim A dubious"],
        ))

        summary = ledger.get_review_summary("test-inq-001")
        assert summary["review_count"] == 2
        assert summary["endorsements"] == 1
        assert summary["challenges"] == 1
        assert summary["avg_confidence_adjustment"] == 0.0
        assert "claim A dubious" in summary["all_challenges"]


def test_ledger_summary_unreviewed():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "review_ledger.json"
        ledger = ReviewLedger(path)
        summary = ledger.get_review_summary("nonexistent")
        assert summary["status"] == "unreviewed"
        assert summary["review_count"] == 0


# ── PeerReviewProcessor ──


def test_processor_endorsement():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        results_dir = repo / "docs" / "authority" / "research_results"
        _make_published_result(results_dir)

        processor = PeerReviewProcessor(repo)
        review = _make_review(verdict=ReviewVerdict.ENDORSE)
        actions = processor.process(review)

        assert review.status == ReviewStatus.PROCESSED
        assert "Endorsement recorded" in actions["actions_taken"]

        # Check result was annotated
        result_data = json.loads((results_dir / "test-inq-001.json").read_text())
        assert len(result_data["peer_reviews"]) == 1
        assert result_data["peer_reviews"][0]["verdict"] == "endorse"


def test_processor_challenge():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        results_dir = repo / "docs" / "authority" / "research_results"
        _make_published_result(results_dir)

        processor = PeerReviewProcessor(repo)
        review = _make_review(
            verdict=ReviewVerdict.CHALLENGE,
            challenges=["claim A is unsupported", "evidence B is outdated"],
        )
        actions = processor.process(review)

        assert review.status == ReviewStatus.PROCESSED
        assert actions["confidence_impact"] == "negative"
        assert "claim A is unsupported" in actions["challenged_claims"]


def test_processor_refutation():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        results_dir = repo / "docs" / "authority" / "research_results"
        _make_published_result(results_dir)

        processor = PeerReviewProcessor(repo)
        review = _make_review(
            verdict=ReviewVerdict.REFUTE,
            counter_evidence=["study X contradicts claim"],
        )
        actions = processor.process(review)

        assert actions["confidence_impact"] == "strongly_negative"

        result_data = json.loads((results_dir / "test-inq-001.json").read_text())
        assert result_data["review_score"]["challenges"] == 1


def test_processor_missing_result():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "docs" / "authority" / "research_results").mkdir(parents=True)

        processor = PeerReviewProcessor(repo)
        review = _make_review(inquiry_id="nonexistent")
        actions = processor.process(review)

        assert "error" in actions
        assert review.status == ReviewStatus.DISMISSED


def test_processor_hash_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        results_dir = repo / "docs" / "authority" / "research_results"
        _make_published_result(results_dir)

        processor = PeerReviewProcessor(repo)
        review = _make_review(content_hash="wrong_hash")
        actions = processor.process(review)

        assert "warning" in actions
        # Still processes despite mismatch
        assert review.status == ReviewStatus.PROCESSED


# ── JSON Extraction ──


def test_extract_json_from_code_block():
    body = """Some text before

```json
{"inquiry_id": "test-1", "verdict": "endorse", "summary": "Good work"}
```

Some text after"""
    data = _extract_json_from_body(body)
    assert data is not None
    assert data["inquiry_id"] == "test-1"
    assert data["verdict"] == "endorse"


def test_extract_json_from_raw():
    body = 'Here is my review: {"inquiry_id": "test-2", "verdict": "challenge"}'
    data = _extract_json_from_body(body)
    assert data is not None
    assert data["inquiry_id"] == "test-2"


def test_extract_json_returns_none_for_no_json():
    body = "This is just text with no JSON at all."
    data = _extract_json_from_body(body)
    assert data is None
