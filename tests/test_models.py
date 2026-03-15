"""Tests for core data models."""
import json
from agent_research.models import (
    ConfidenceLevel,
    Finding,
    Inquiry,
    InquirySource,
    InquiryUrgency,
    MethodologyType,
    ResearchResult,
)


def test_inquiry_roundtrip():
    inq = Inquiry(
        inquiry_id="test-001",
        question="How do agents coordinate?",
        context="Federation research",
        source=InquirySource.CURIOSITY,
        domains=["computation-intelligence"],
        urgency=InquiryUrgency.STANDARD,
    )
    d = inq.to_dict()
    restored = Inquiry.from_dict(d)
    assert restored.inquiry_id == "test-001"
    assert restored.question == "How do agents coordinate?"
    assert restored.source == InquirySource.CURIOSITY
    assert restored.domains == ["computation-intelligence"]


def test_finding_to_dict():
    f = Finding(
        claim="Agents can coordinate without central authority",
        evidence=["Swarm intelligence in nature", "Byzantine fault tolerance"],
        confidence=ConfidenceLevel.SUPPORTED,
        sources=["faculty-brief"],
        limitations=["Based on theory, not empirical"],
    )
    d = f.to_dict()
    assert d["claim"] == "Agents can coordinate without central authority"
    assert d["confidence"] == "supported"
    assert len(d["evidence"]) == 2


def test_research_result_content_hash_stable():
    r = ResearchResult(
        inquiry_id="hash-test",
        title="Test",
        abstract="Abstract",
        findings=[Finding(claim="X", confidence=ConfidenceLevel.PRELIMINARY)],
        faculties_involved=["cross-domain"],
        completed_at="2026-01-01T00:00:00Z",
    )
    h1 = r.content_hash
    h2 = r.content_hash
    assert h1 == h2
    assert len(h1) == 64  # SHA256


def test_research_result_content_hash_changes():
    r1 = ResearchResult(inquiry_id="a", title="A", abstract="X", completed_at="2026-01-01T00:00:00Z")
    r2 = ResearchResult(inquiry_id="b", title="B", abstract="X", completed_at="2026-01-01T00:00:00Z")
    assert r1.content_hash != r2.content_hash


def test_overall_confidence_weakest_link():
    r = ResearchResult(
        findings=[
            Finding(confidence=ConfidenceLevel.ESTABLISHED),
            Finding(confidence=ConfidenceLevel.PRELIMINARY),
            Finding(confidence=ConfidenceLevel.SUPPORTED),
        ]
    )
    # Weakest = highest index in enum order
    assert r.overall_confidence == ConfidenceLevel.PRELIMINARY


def test_to_authority_document_has_structure():
    r = ResearchResult(
        inquiry_id="doc-test",
        title="Test Research",
        abstract="Test abstract.",
        findings=[
            Finding(
                claim="Test claim",
                evidence=["Evidence A"],
                confidence=ConfidenceLevel.SUPPORTED,
                sources=["source-1"],
            )
        ],
        methodology_used=MethodologyType.SYNTHESIS,
        faculties_involved=["physics-fundamental"],
        open_questions=["What next?"],
        sources=["source-1"],
    )
    md = r.to_authority_document()
    assert "# Test Research" in md
    assert "## Abstract" in md
    assert "## Findings" in md
    assert "Test claim" in md
    assert "Evidence A" in md
    assert "## Metadata" in md
    assert "doc-test" in md
