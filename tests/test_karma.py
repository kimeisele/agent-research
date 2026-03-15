"""Tests for KARMA phase."""
import tempfile
from pathlib import Path

from agent_research.models import (
    ConfidenceLevel,
    Inquiry,
    InquiryStatus,
    MethodologyType,
    ResearchScope,
)
from agent_research.phases.karma import KarmaPhase, ResearchContext, _extract_terms, _find_relevant_sections


def _make_repo(tmp: Path) -> Path:
    fac = tmp / "docs" / "authority" / "faculties" / "computation-intelligence"
    fac.mkdir(parents=True)
    (fac / "00-faculty-brief.md").write_text(
        "# Computation & Intelligence\n\n"
        "## Core Questions\n\n"
        "1. **How do autonomous agents coordinate without central authority?**\n"
        "   Federation protocols, consensus mechanisms, mesh architectures.\n\n"
        "## Research Priorities\n\n"
        "- Agent federation protocol design\n"
        "- Multi-agent coordination theory\n"
        "- AI safety research\n"
        "- Distributed knowledge systems\n"
    )
    (tmp / "data").mkdir(parents=True)
    return tmp


def test_extract_terms():
    terms = _extract_terms("How do quantum mechanics and biology interact?")
    assert "quantum" in terms
    assert "mechanics" in terms
    assert "biology" in terms
    assert "how" not in terms  # stop word


def test_find_relevant_sections():
    content = "# Energy\n\nSolar panels work.\n\n# Health\n\nNutrition matters.\n"
    sections = _find_relevant_sections(content, {"solar", "panels", "energy"})
    assert len(sections) >= 1
    assert sections[0][0] == "Energy"


def test_research_context_add_finding():
    inq = Inquiry(question="Test?")
    scope = ResearchScope(faculties=["cross-domain"])
    ctx = ResearchContext(inq, scope)
    f = ctx.add_finding(
        claim="Test claim",
        evidence=["Evidence"],
        confidence=ConfidenceLevel.PRELIMINARY,
    )
    assert len(ctx.findings) == 1
    assert f.claim == "Test claim"


def test_karma_builds_context():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        karma = KarmaPhase(repo, token=None)  # No GitHub token = no federation sources
        inq = Inquiry(question="How do agents coordinate?")
        scope = ResearchScope(faculties=["computation-intelligence"])
        ctx = karma.build_context(inq, scope)
        assert len(ctx.local_sources) >= 1
        assert ctx.local_sources[0]["type"] == "faculty_document"


def test_karma_run_produces_result():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        karma = KarmaPhase(repo, token=None)
        inq = Inquiry(question="How do agents coordinate without central authority?")
        scope = ResearchScope(
            inquiry_id=inq.inquiry_id,
            faculties=["computation-intelligence"],
            methodology=MethodologyType.SYNTHESIS,
        )
        result = karma.run(inq, scope)
        assert result.title == inq.question
        assert len(result.findings) >= 1
        assert result.faculties_involved == ["computation-intelligence"]
        assert inq.status == InquiryStatus.IN_REVIEW
        # Findings should have actual evidence, not just file counts
        for f in result.findings:
            assert f.evidence, f"Finding '{f.claim}' has no evidence"


def test_karma_gap_detection():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        karma = KarmaPhase(repo, token=None)
        inq = Inquiry(question="Test")
        scope = ResearchScope(faculties=["computation-intelligence"])
        result = karma.run(inq, scope)
        # Should always report gaps/limitations honestly
        gap_findings = [f for f in result.findings if "gap" in f.claim.lower() or "limitation" in f.claim.lower()]
        assert len(gap_findings) >= 1
