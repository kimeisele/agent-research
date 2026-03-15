"""Knowledge Graph — accumulated research memory.

A Faculty that forgets is not a Faculty. This module provides:
1. Persistent graph of concepts, findings, and their relationships
2. Accumulation across research cycles
3. Query by concept, domain, or relationship type
4. Tracks provenance — every edge traces back to its source inquiry

Storage: JSON file at data/knowledge_graph.json
Not a real graph database — but it's persistent, queryable, and grows.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Concept:
    """A node in the knowledge graph."""
    id: str                          # Normalized slug
    label: str                       # Human-readable name
    domains: list[str] = field(default_factory=list)
    description: str = ""
    first_seen: str = ""             # When this concept first appeared
    mention_count: int = 0           # How many findings reference this
    source_inquiries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "label": self.label, "domains": self.domains,
            "description": self.description, "first_seen": self.first_seen,
            "mention_count": self.mention_count, "source_inquiries": self.source_inquiries,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Concept:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Edge:
    """A relationship between two concepts."""
    source: str                      # Concept ID
    target: str                      # Concept ID
    relation: str                    # "relates_to", "supports", "contradicts", "enables", "requires"
    weight: float = 1.0              # Strength of relationship
    evidence: str = ""               # Why this edge exists
    source_inquiry: str = ""         # Which inquiry produced this
    created_at: str = ""

    def to_dict(self) -> dict:
        return {
            "source": self.source, "target": self.target, "relation": self.relation,
            "weight": self.weight, "evidence": self.evidence,
            "source_inquiry": self.source_inquiry, "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Edge:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class OpenQuestion:
    """A question that emerged from research — fuel for future GENESIS."""
    question: str
    parent_inquiry: str              # Which research produced this question
    domains: list[str] = field(default_factory=list)
    created_at: str = ""
    addressed_by: str = ""           # Inquiry ID that addressed this, if any

    def to_dict(self) -> dict:
        return {
            "question": self.question, "parent_inquiry": self.parent_inquiry,
            "domains": self.domains, "created_at": self.created_at,
            "addressed_by": self.addressed_by,
        }

    @classmethod
    def from_dict(cls, d: dict) -> OpenQuestion:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class KnowledgeGraph:
    """Persistent, accumulating knowledge graph.

    Every research cycle adds to this graph. Nothing is deleted —
    knowledge accumulates. The graph is the Faculty's memory.
    """

    def __init__(self, path: Path):
        self.path = path
        self.concepts: dict[str, Concept] = {}
        self.edges: list[Edge] = []
        self.open_questions: list[OpenQuestion] = []
        self.meta: dict[str, Any] = {"version": 1, "total_ingestions": 0}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
            self.meta = data.get("meta", self.meta)
            for cd in data.get("concepts", []):
                c = Concept.from_dict(cd)
                self.concepts[c.id] = c
            self.edges = [Edge.from_dict(ed) for ed in data.get("edges", [])]
            self.open_questions = [OpenQuestion.from_dict(oq) for oq in data.get("open_questions", [])]
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Knowledge graph load failed: %s", e)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "meta": self.meta,
            "concepts": [c.to_dict() for c in self.concepts.values()],
            "edges": [e.to_dict() for e in self.edges],
            "open_questions": [oq.to_dict() for oq in self.open_questions],
        }
        self.path.write_text(json.dumps(data, indent=2) + "\n")

    # ── Ingestion ────────────────────────────────────────────────

    def ingest_finding(self, inquiry_id: str, claim: str, evidence: list[str],
                       domains: list[str], sources: list[str]) -> list[str]:
        """Ingest a research finding into the graph.

        Extracts concepts, creates edges, returns list of new concept IDs.
        """
        now = datetime.now(timezone.utc).isoformat()
        new_concepts: list[str] = []

        # Extract concept terms from claim and evidence
        terms = _extract_concept_terms(claim)
        for ev in evidence:
            terms.update(_extract_concept_terms(ev))

        for term in terms:
            cid = _slugify(term)
            if cid not in self.concepts:
                self.concepts[cid] = Concept(
                    id=cid, label=term, domains=domains,
                    first_seen=now, mention_count=1,
                    source_inquiries=[inquiry_id],
                )
                new_concepts.append(cid)
            else:
                c = self.concepts[cid]
                c.mention_count += 1
                if inquiry_id not in c.source_inquiries:
                    c.source_inquiries.append(inquiry_id)
                for d in domains:
                    if d not in c.domains:
                        c.domains.append(d)

        # Create edges between co-occurring concepts
        term_ids = [_slugify(t) for t in terms]
        for i, a in enumerate(term_ids):
            for b in term_ids[i + 1:]:
                if a != b:
                    existing = self._find_edge(a, b, "co_occurs")
                    if existing:
                        existing.weight += 1.0
                    else:
                        self.edges.append(Edge(
                            source=a, target=b, relation="co_occurs",
                            weight=1.0, evidence=claim[:200],
                            source_inquiry=inquiry_id, created_at=now,
                        ))

        self.meta["total_ingestions"] = self.meta.get("total_ingestions", 0) + 1
        return new_concepts

    def ingest_open_question(self, question: str, parent_inquiry: str,
                              domains: list[str]) -> None:
        """Record an open question for future research."""
        # Check if we already have this question
        for oq in self.open_questions:
            if oq.question.lower().strip() == question.lower().strip():
                return
        self.open_questions.append(OpenQuestion(
            question=question, parent_inquiry=parent_inquiry,
            domains=domains, created_at=datetime.now(timezone.utc).isoformat(),
        ))

    def mark_question_addressed(self, question: str, inquiry_id: str) -> None:
        """Mark an open question as addressed by a new inquiry."""
        for oq in self.open_questions:
            if oq.question.lower().strip() == question.lower().strip():
                oq.addressed_by = inquiry_id

    # ── Query ────────────────────────────────────────────────────

    def get_concept(self, concept_id: str) -> Concept | None:
        return self.concepts.get(concept_id)

    def get_related(self, concept_id: str) -> list[tuple[Concept, Edge]]:
        """Get all concepts related to a given concept."""
        related = []
        for edge in self.edges:
            if edge.source == concept_id and edge.target in self.concepts:
                related.append((self.concepts[edge.target], edge))
            elif edge.target == concept_id and edge.source in self.concepts:
                related.append((self.concepts[edge.source], edge))
        return sorted(related, key=lambda x: -x[1].weight)

    def get_domain_concepts(self, domain: str) -> list[Concept]:
        """Get all concepts in a domain, sorted by mention count."""
        return sorted(
            [c for c in self.concepts.values() if domain in c.domains],
            key=lambda c: -c.mention_count,
        )

    def get_unanswered_questions(self) -> list[OpenQuestion]:
        """Get open questions not yet addressed."""
        return [oq for oq in self.open_questions if not oq.addressed_by]

    def get_strongest_edges(self, n: int = 20) -> list[Edge]:
        """Get the N strongest relationships in the graph."""
        return sorted(self.edges, key=lambda e: -e.weight)[:n]

    def get_most_connected(self, n: int = 20) -> list[Concept]:
        """Get the N most connected concepts."""
        connection_count: dict[str, int] = {}
        for edge in self.edges:
            connection_count[edge.source] = connection_count.get(edge.source, 0) + 1
            connection_count[edge.target] = connection_count.get(edge.target, 0) + 1
        top_ids = sorted(connection_count, key=lambda x: -connection_count[x])[:n]
        return [self.concepts[cid] for cid in top_ids if cid in self.concepts]

    # ── Stats ────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return {
            "concepts": len(self.concepts),
            "edges": len(self.edges),
            "open_questions": len(self.open_questions),
            "unanswered_questions": len(self.get_unanswered_questions()),
            "total_ingestions": self.meta.get("total_ingestions", 0),
            "domains": list({d for c in self.concepts.values() for d in c.domains}),
        }

    def _find_edge(self, source: str, target: str, relation: str) -> Edge | None:
        for e in self.edges:
            if (e.source == source and e.target == target and e.relation == relation) or \
               (e.source == target and e.target == source and e.relation == relation):
                return e
        return None


def _slugify(text: str) -> str:
    """Convert text to a concept ID."""
    import re
    return re.sub(r'[^a-z0-9]+', '-', text.lower().strip()).strip('-')


def _extract_concept_terms(text: str) -> set[str]:
    """Extract meaningful multi-word and single-word concept terms."""
    import re
    terms: set[str] = set()

    # Extract multi-word terms in bold (**term**)
    for match in re.finditer(r'\*\*([^*]+)\*\*', text):
        term = match.group(1).strip()
        if len(term) > 3:
            terms.add(term.lower())

    # Extract capitalized phrases (likely proper nouns or concepts)
    for match in re.finditer(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', text):
        term = match.group(0).strip()
        if len(term) > 5:
            terms.add(term.lower())

    # Extract meaningful single words (4+ chars, not common)
    for word in re.findall(r'\b[a-zA-Z]{5,}\b', text):
        w = word.lower()
        if w not in _GRAPH_STOP_WORDS:
            terms.add(w)

    return terms


_GRAPH_STOP_WORDS = frozenset({
    "about", "above", "after", "again", "against", "these", "those",
    "being", "below", "between", "could", "would", "should", "might",
    "their", "there", "where", "which", "while", "before", "during",
    "other", "every", "first", "found", "given", "makes", "might",
    "never", "often", "point", "quite", "right", "since", "still",
    "thing", "think", "three", "under", "until", "using", "where",
    "words", "world", "years", "based", "cases", "clear", "could",
    "field", "great", "group", "known", "large", "level", "local",
    "major", "means", "needs", "noted", "order", "place", "power",
    "range", "shows", "small", "south", "state", "study", "taken",
    "terms", "value", "water", "works", "areas", "along", "among",
    "apply", "approach", "available", "become", "called", "change",
    "common", "consider", "current", "different", "example", "evidence",
    "following", "general", "however", "include", "important", "information",
    "knowledge", "number", "particular", "possible", "present", "provide",
    "public", "result", "results", "several", "similar", "simple",
    "single", "source", "sources", "specific", "support", "system",
    "systems", "through", "understanding", "within", "without",
    "research", "analysis", "document", "documents", "faculty",
    "finding", "findings", "limitation", "limitations",
})
