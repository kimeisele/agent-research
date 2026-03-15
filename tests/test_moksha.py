"""Tests for MOKSHA phase."""
import json
import tempfile
from pathlib import Path

from agent_research.models import (
    ConfidenceLevel,
    Finding,
    Inquiry,
    InquirySource,
    InquiryStatus,
    MethodologyType,
    ResearchResult,
)
from agent_research.phases.moksha import MokshaPhase, ResultValidator


def _make_result() -> tuple[Inquiry, ResearchResult]:
    inq = Inquiry(inquiry_id="test-pub", question="Test question?", source=InquirySource.CURIOSITY)
    result = ResearchResult(
        inquiry_id="test-pub",
        title="Test Research Result",
        abstract="A test abstract.",
        findings=[
            Finding(
                claim="Test finding",
                evidence=["Test evidence"],
                confidence=ConfidenceLevel.PRELIMINARY,
                sources=["test-source"],
            )
        ],
        methodology_used=MethodologyType.SYNTHESIS,
        faculties_involved=["cross-domain"],
        sources=["test-source"],
    )
    return inq, result


def test_validator_passes_valid():
    _, result = _make_result()
    errors = ResultValidator().validate(result)
    assert errors == []


def test_validator_catches_missing_title():
    _, result = _make_result()
    result.title = ""
    errors = ResultValidator().validate(result)
    assert any("title" in e.lower() for e in errors)


def test_validator_catches_no_findings():
    _, result = _make_result()
    result.findings = []
    errors = ResultValidator().validate(result)
    assert any("findings" in e.lower() for e in errors)


def test_moksha_writes_documents():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "docs" / "authority").mkdir(parents=True)
        (repo / "data").mkdir(parents=True)
        # No export script — feed publish will fail gracefully
        moksha = MokshaPhase(repo, token=None)
        inq, result = _make_result()
        success = moksha.run(inq, result)
        assert success
        assert inq.status == InquiryStatus.PUBLISHED

        # Check files were written
        results_dir = repo / "docs" / "authority" / "research_results"
        assert (results_dir / "test-pub.md").exists()
        assert (results_dir / "test-pub.json").exists()

        # Check ledger was updated
        ledger = json.loads((repo / "data" / "inquiry_ledger.json").read_text())
        assert "test-pub" in ledger
        assert ledger["test-pub"]["status"] == "published"


def test_moksha_rejects_invalid():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "docs" / "authority").mkdir(parents=True)
        (repo / "data").mkdir(parents=True)
        moksha = MokshaPhase(repo, token=None)
        inq = Inquiry(inquiry_id="bad")
        result = ResearchResult(inquiry_id="bad", title="", findings=[])  # Invalid
        success = moksha.run(inq, result)
        assert not success
