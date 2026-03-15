"""Tests for Knowledge Graph."""
import json
import tempfile
from pathlib import Path

from agent_research.knowledge import KnowledgeGraph, Concept, Edge, OpenQuestion


def _make_graph() -> tuple[Path, KnowledgeGraph]:
    tmp = tempfile.mkdtemp()
    path = Path(tmp) / "kg.json"
    return path, KnowledgeGraph(path)


def test_empty_graph_stats():
    path, kg = _make_graph()
    stats = kg.stats()
    assert stats["concepts"] == 0
    assert stats["edges"] == 0
    assert stats["open_questions"] == 0


def test_ingest_finding_creates_concepts():
    _, kg = _make_graph()
    new = kg.ingest_finding(
        inquiry_id="inq-1",
        claim="**Federation protocols** enable **multi-agent coordination** across nodes",
        evidence=["Steward uses relay pump for coordination"],
        domains=["computation-intelligence"],
        sources=["steward"],
    )
    assert len(new) > 0
    assert kg.stats()["concepts"] > 0


def test_ingest_finding_creates_edges():
    _, kg = _make_graph()
    kg.ingest_finding(
        inquiry_id="inq-1",
        claim="**consensus** requires **fault tolerance** in distributed systems",
        evidence=[],
        domains=["computation-intelligence"],
        sources=[],
    )
    assert kg.stats()["edges"] > 0


def test_ingest_increments_mention_count():
    _, kg = _make_graph()
    kg.ingest_finding(
        inquiry_id="inq-1",
        claim="**federation** is important",
        evidence=[], domains=[], sources=[],
    )
    kg.ingest_finding(
        inquiry_id="inq-2",
        claim="**federation** grows stronger",
        evidence=[], domains=[], sources=[],
    )
    # federation should have mention_count 2
    concept = kg.get_concept("federation")
    assert concept is not None
    assert concept.mention_count == 2


def test_save_and_reload():
    path, kg = _make_graph()
    kg.ingest_finding(
        inquiry_id="inq-1",
        claim="**Quantum Computing** bridges physics and computation",
        evidence=["Shor's algorithm"],
        domains=["physics-fundamental", "computation-intelligence"],
        sources=["textbook"],
    )
    kg.ingest_open_question("What is quantum advantage?", "inq-1", ["physics-fundamental"])
    kg.save()

    kg2 = KnowledgeGraph(path)
    assert kg2.stats()["concepts"] == kg.stats()["concepts"]
    assert kg2.stats()["edges"] == kg.stats()["edges"]
    assert kg2.stats()["open_questions"] == 1


def test_open_questions():
    _, kg = _make_graph()
    kg.ingest_open_question("Q1?", "inq-1", ["domain-a"])
    kg.ingest_open_question("Q2?", "inq-1", ["domain-b"])
    assert len(kg.get_unanswered_questions()) == 2

    kg.mark_question_addressed("Q1?", "inq-2")
    assert len(kg.get_unanswered_questions()) == 1


def test_dedup_open_questions():
    _, kg = _make_graph()
    kg.ingest_open_question("Same question?", "inq-1", [])
    kg.ingest_open_question("Same question?", "inq-2", [])
    assert len(kg.open_questions) == 1


def test_get_related():
    _, kg = _make_graph()
    kg.ingest_finding(
        inquiry_id="inq-1",
        claim="**Alpha** relates to **Beta** and **Gamma**",
        evidence=[], domains=[], sources=[],
    )
    related = kg.get_related("alpha")
    # Should find beta and gamma
    assert len(related) >= 1
    related_ids = {c.id for c, _ in related}
    assert "beta" in related_ids or "gamma" in related_ids


def test_get_domain_concepts():
    _, kg = _make_graph()
    kg.ingest_finding(
        inquiry_id="inq-1",
        claim="**Energy efficiency** matters in computing",
        evidence=[], domains=["energy-sustainability"], sources=[],
    )
    concepts = kg.get_domain_concepts("energy-sustainability")
    assert len(concepts) > 0


def test_strongest_edges():
    _, kg = _make_graph()
    # Ingest same co-occurrence multiple times to build weight
    for i in range(3):
        kg.ingest_finding(
            inquiry_id=f"inq-{i}",
            claim="**Alpha** and **Beta** co-occur",
            evidence=[], domains=[], sources=[],
        )
    strong = kg.get_strongest_edges(5)
    assert len(strong) > 0
    assert strong[0].weight >= 3.0


def test_concept_model():
    c = Concept(id="test", label="Test Concept", domains=["domain-a"])
    d = c.to_dict()
    c2 = Concept.from_dict(d)
    assert c2.id == "test"
    assert c2.label == "Test Concept"


def test_edge_model():
    e = Edge(source="a", target="b", relation="co_occurs", weight=2.5)
    d = e.to_dict()
    e2 = Edge.from_dict(d)
    assert e2.source == "a"
    assert e2.weight == 2.5
