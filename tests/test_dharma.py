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
            {"id": "energy-sustainability", "domains": ["energy"]},
            {"id": "health-medicine", "domains": ["health"]},
            {"id": "computation-intelligence", "domains": ["ai"]},
            {"id": "cross-domain", "domains": ["interdisciplinary"]},
        ]
    }
    (tmp / "docs" / "authority").mkdir(parents=True)
    (tmp / "docs" / "authority" / "capabilities.json").write_text(json.dumps(cap))
    return tmp


def test_faculty_router_energy():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="How do we improve solar panel efficiency?")
        faculties = router.route(inq)
        assert "energy-sustainability" in faculties


def test_faculty_router_health():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="What is the effect of nutrition on disease prevention?")
        faculties = router.route(inq)
        assert "health-medicine" in faculties


def test_faculty_router_explicit_domains():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="Random question", domains=["computation-intelligence"])
        faculties = router.route(inq)
        assert faculties == ["computation-intelligence"]


def test_faculty_router_default_cross_domain():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        router = FacultyRouter(repo / "docs" / "authority" / "capabilities.json")
        inq = Inquiry(question="Xyzzy foobar blorp")
        faculties = router.route(inq)
        assert faculties == ["cross-domain"]


def test_methodology_selector():
    sel = MethodologySelector()
    assert sel.select(Inquiry(question="What is the state of quantum computing?")) == MethodologyType.SYNTHESIS
    assert sel.select(Inquiry(question="Review of current research on biodiversity")) == MethodologyType.LITERATURE_REVIEW
    assert sel.select(Inquiry(question="Connection between physics and biology")) == MethodologyType.CROSS_DOMAIN


def test_dharma_produces_scope():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        dharma = DharmaPhase(repo)
        inq = Inquiry(question="How does quantum mechanics apply to computing?")
        scope = dharma.run(inq)
        assert scope.inquiry_id == inq.inquiry_id
        assert len(scope.faculties) >= 1
        assert scope.methodology is not None
        assert inq.status == InquiryStatus.SCOPED


def test_dharma_cross_domain_deeper():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        dharma = DharmaPhase(repo)
        # Question that hits multiple faculties
        inq = Inquiry(question="How does energy efficiency affect health outcomes in medicine?")
        scope = dharma.run(inq)
        assert len(scope.faculties) >= 2
        assert len(scope.cross_domain_bridges) >= 1
