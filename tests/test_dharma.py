"""Tests for DHARMA phase."""
import json
import tempfile
from pathlib import Path

from agent_research.models import (
    Inquiry,
    InquirySource,
    InquiryStatus,
    InquiryUrgency,
    MethodologyType,
)
from agent_research.phases.dharma import DharmaPhase, FacultyRouter, MethodologySelector


def _make_repo(tmp: Path) -> Path:
    cap = {
        "faculties": [
            {"id": "agent_physics", "domains": ["physics", "emergence"]},
            {"id": "agent_governance", "domains": ["governance", "trust"]},
            {"id": "agent_economics", "domains": ["resources", "cost"]},
            {"id": "agent_health", "domains": ["healing", "resilience"]},
            {"id": "cross_domain", "domains": ["interdisciplinary"]},
        ]
    }
    (tmp / "docs" / "authority").mkdir(parents=True)
    (tmp / "docs" / "authority" / "capabilities.json").write_text(json.dumps(cap))
    return tmp


def test_faculty_router_governance():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="How does trust propagate in decentralized governance?")
        faculties = router.route(inq)
        assert "agent_governance" in faculties


def test_faculty_router_health():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="How does self-healing work when a circuit breaker fails?")
        faculties = router.route(inq)
        assert "agent_health" in faculties


def test_faculty_router_explicit_domains():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="Random question", domains=["agent_physics"])
        faculties = router.route(inq)
        assert faculties == ["agent_physics"]


def test_faculty_router_default_cross_domain():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="Xyzzy foobar blorp")
        faculties = router.route(inq)
        assert faculties == ["cross-domain"]


def test_methodology_selector():
    sel = MethodologySelector()
    assert sel.select(Inquiry(question="What is the state of agent coordination?")) == MethodologyType.SYNTHESIS
    assert sel.select(Inquiry(question="Review of current research on federation protocols")) == MethodologyType.LITERATURE_REVIEW
    assert sel.select(Inquiry(question="Connection between governance and health in agents")) == MethodologyType.CROSS_DOMAIN


def test_dharma_produces_scope():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        dharma = DharmaPhase(repo)
        inq = Inquiry(question="How does trust affect federation governance?")
        scope = dharma.run(inq)
        assert scope.inquiry_id == inq.inquiry_id
        assert len(scope.faculties) >= 1
        assert scope.methodology is not None
        assert inq.status == InquiryStatus.SCOPED


def test_dharma_cross_domain_deeper():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        dharma = DharmaPhase(repo)
        # Question that hits multiple domains
        inq = Inquiry(question="How does governance integrity affect recovery and healing efficiency?")
        scope = dharma.run(inq)
        assert len(scope.faculties) >= 2
        assert len(scope.cross_domain_bridges) >= 1
