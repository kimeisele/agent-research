"""DHARMA Phase — Select methodology, route to faculty, define scope.

Deterministic routing. Zero LLM. Pure discrimination logic.

Takes raw inquiries from GENESIS and produces scoped research tasks:
1. Classify the question into domain(s)
2. Select the appropriate faculty/faculties
3. Choose research methodology
4. Define scope and constraints
5. Identify cross-domain bridges
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from agent_research.models import (
    Inquiry,
    InquiryStatus,
    MethodologyType,
    ResearchScope,
)

logger = logging.getLogger(__name__)

# Domain keyword mapping — deterministic classification
# Maps keywords to research domains (agent_physics, agent_governance, etc.)
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    # Agent Physics — emergent behavior, load, scaling, failure dynamics
    "emergent": ["agent_physics", "cross_domain"],
    "emergence": ["agent_physics", "cross_domain"],
    "load": ["agent_physics"],
    "scaling": ["agent_physics"],
    "phase transition": ["agent_physics", "cross_domain"],
    "cascading": ["agent_physics", "agent_health"],
    "pressure": ["agent_physics"],
    "entropy": ["agent_physics"],
    "throughput": ["agent_physics"],
    "latency": ["agent_physics"],
    "bottleneck": ["agent_physics"],
    "capacity": ["agent_physics"],
    "behavior": ["agent_physics"],
    "dynamics": ["agent_physics", "cross_domain"],
    "physics": ["agent_physics"],
    "propagation": ["agent_physics"],
    # Agent Governance — trust, voting, authority, protocol evolution
    "governance": ["agent_governance"],
    "voting": ["agent_governance"],
    "trust": ["agent_governance"],
    "authority": ["agent_governance"],
    "consensus": ["agent_governance"],
    "conflict": ["agent_governance"],
    "decision": ["agent_governance"],
    "protocol": ["agent_governance", "agent_physics"],
    "contract": ["agent_governance"],
    "integrity": ["agent_governance"],
    "compliance": ["agent_governance"],
    "legitimacy": ["agent_governance"],
    "accountability": ["agent_governance"],
    "democracy": ["agent_governance", "cross_domain"],
    "decentralized": ["agent_governance"],
    "federation": ["agent_governance", "agent_physics"],
    # Agent Economics — resources, costs, allocation, optimization
    "resource": ["agent_economics"],
    "allocation": ["agent_economics"],
    "cost": ["agent_economics"],
    "budget": ["agent_economics"],
    "efficiency": ["agent_economics"],
    "optimization": ["agent_economics"],
    "redundancy": ["agent_economics", "agent_health"],
    "failover": ["agent_economics", "agent_health"],
    "provider": ["agent_economics"],
    "pricing": ["agent_economics"],
    "scarcity": ["agent_economics"],
    "commons": ["agent_economics", "agent_governance"],
    "trade": ["agent_economics"],
    "market": ["agent_economics", "cross_domain"],
    "llm": ["agent_economics"],
    "api": ["agent_economics"],
    # Agent Health — healing, failure, recovery, monitoring
    "health": ["agent_health"],
    "healing": ["agent_health"],
    "self-healing": ["agent_health"],
    "circuit breaker": ["agent_health"],
    "heartbeat": ["agent_health"],
    "failure": ["agent_health", "agent_physics"],
    "recovery": ["agent_health"],
    "resilience": ["agent_health"],
    "immune": ["agent_health", "cross_domain"],
    "monitoring": ["agent_health"],
    "diagnosis": ["agent_health"],
    "symptom": ["agent_health"],
    "outbreak": ["agent_health", "cross_domain"],
    "quarantine": ["agent_health"],
    "degradation": ["agent_health", "agent_physics"],
    # Cross-Domain — patterns across domains, human parallels
    "cross-domain": ["cross_domain"],
    "interdisciplinary": ["cross_domain"],
    "isomorphism": ["cross_domain"],
    "analogy": ["cross_domain"],
    "pattern": ["cross_domain"],
    "parallel": ["cross_domain"],
    "universal": ["cross_domain"],
    "bridge": ["cross_domain"],
    "transfer": ["cross_domain"],
    # General agent/federation terms route to physics + governance
    "agent": ["agent_physics", "agent_governance"],
    "distributed": ["agent_physics", "agent_governance"],
    "mesh": ["agent_physics"],
    "node": ["agent_physics", "agent_health"],
    "relay": ["agent_physics"],
    "nadi": ["agent_physics"],
}

# Methodology selection heuristics
METHODOLOGY_SIGNALS: dict[str, list[str]] = {
    "synthesis": ["what is", "overview", "summary", "explain", "how does", "describe"],
    "meta_analysis": ["studies show", "evidence for", "aggregate", "quantitative", "statistical"],
    "literature_review": ["review", "survey", "state of", "current research", "what do we know"],
    "cross_domain": ["connection between", "intersection", "bridge", "across", "interdisciplinary"],
    "first_principles": ["why does", "fundamental", "derive", "prove", "first principles"],
    "data_analysis": ["data", "dataset", "analyze", "pattern", "trend", "measurement"],
    "methodology_review": ["methodology", "approach", "how to research", "best practices"],
}


class FacultyRouter:
    """Route inquiries to the appropriate faculty/faculties.

    Deterministic keyword-based classification. No LLM needed.
    """

    def __init__(self, capabilities_path: Path | None = None):
        self.known_faculties: set[str] = set()
        if capabilities_path and capabilities_path.exists():
            try:
                cap = json.loads(capabilities_path.read_text())
                self.known_faculties = {f["id"] for f in cap.get("faculties", [])}
            except (json.JSONDecodeError, OSError):
                pass

    def route(self, inquiry: Inquiry) -> list[str]:
        """Determine which faculties should handle this inquiry."""
        # 1. Explicit domains from the inquiry take priority
        if inquiry.domains:
            valid = [d for d in inquiry.domains if d in self.known_faculties]
            if valid:
                return valid

        # 2. Keyword-based classification
        text = f"{inquiry.question} {inquiry.context}".lower()
        faculty_scores: dict[str, int] = {}
        for keyword, faculties in DOMAIN_KEYWORDS.items():
            if keyword in text:
                for fac in faculties:
                    faculty_scores[fac] = faculty_scores.get(fac, 0) + 1

        if faculty_scores:
            # Return all faculties with score above threshold
            max_score = max(faculty_scores.values())
            threshold = max(1, max_score // 2)
            return sorted(
                [f for f, s in faculty_scores.items() if s >= threshold],
                key=lambda f: -faculty_scores[f],
            )

        # 3. Default to cross-domain if no match
        return ["cross-domain"]


class MethodologySelector:
    """Select the appropriate research methodology.

    Deterministic signal-based selection. Zero LLM.
    """

    def select(self, inquiry: Inquiry) -> MethodologyType:
        text = f"{inquiry.question} {inquiry.context}".lower()

        scores: dict[str, int] = {}
        for method, signals in METHODOLOGY_SIGNALS.items():
            for signal in signals:
                if signal in text:
                    scores[method] = scores.get(method, 0) + 1

        if scores:
            best = max(scores, key=lambda m: scores[m])
            return MethodologyType(best)

        # Default to synthesis
        return MethodologyType.SYNTHESIS


class ScopeDefiner:
    """Define the scope and constraints for a research task."""

    def define(self, inquiry: Inquiry, faculties: list[str], methodology: MethodologyType) -> ResearchScope:
        # Determine depth based on urgency and source
        depth_map = {
            "critical": "quick",      # Fast answer needed
            "elevated": "standard",
            "standard": "standard",
        }
        depth = depth_map.get(inquiry.urgency.value, "standard")

        # If multiple faculties, this is inherently cross-domain
        cross_bridges: list[tuple[str, str]] = []
        if len(faculties) > 1:
            for i, f1 in enumerate(faculties):
                for f2 in faculties[i + 1:]:
                    cross_bridges.append((f1, f2))
            # Cross-domain research deserves deeper investigation
            if depth == "standard":
                depth = "deep"

        # Estimate sources based on methodology
        source_estimates = {
            MethodologyType.SYNTHESIS: 5,
            MethodologyType.META_ANALYSIS: 10,
            MethodologyType.LITERATURE_REVIEW: 15,
            MethodologyType.CROSS_DOMAIN: 8,
            MethodologyType.FIRST_PRINCIPLES: 3,
            MethodologyType.DATA_ANALYSIS: 5,
            MethodologyType.METHODOLOGY_REVIEW: 7,
        }

        return ResearchScope(
            inquiry_id=inquiry.inquiry_id,
            faculties=faculties,
            methodology=methodology,
            depth=depth,
            cross_domain_bridges=cross_bridges,
            estimated_sources=source_estimates.get(methodology, 5),
        )


class DharmaPhase:
    """DHARMA: Discriminate. Route. Scope.

    Takes inquiries from GENESIS, produces scoped research tasks.
    Entirely deterministic. Zero LLM tokens.
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        cap_path = repo_root / "docs" / "authority" / "capabilities.json"
        self.router = FacultyRouter(cap_path)
        self.methodology_selector = MethodologySelector()
        self.scope_definer = ScopeDefiner()

    def run(self, inquiry: Inquiry) -> ResearchScope:
        """Execute DHARMA for a single inquiry.

        Returns a fully scoped research task ready for KARMA.
        """
        logger.info("DHARMA: Processing inquiry '%s'", inquiry.question[:80])

        # 1. Route to faculty
        faculties = self.router.route(inquiry)
        logger.info("  Faculties: %s", faculties)

        # 2. Select methodology
        methodology = self.methodology_selector.select(inquiry)
        logger.info("  Methodology: %s", methodology.value)

        # 3. Define scope
        scope = self.scope_definer.define(inquiry, faculties, methodology)
        logger.info("  Depth: %s, Est. sources: %d, Cross-bridges: %d",
                     scope.depth, scope.estimated_sources, len(scope.cross_domain_bridges))

        # Update inquiry status
        inquiry.status = InquiryStatus.SCOPED

        return scope

    def run_batch(self, inquiries: list[Inquiry]) -> list[tuple[Inquiry, ResearchScope]]:
        """Run DHARMA for a batch of inquiries."""
        results = []
        for inquiry in inquiries:
            try:
                scope = self.run(inquiry)
                results.append((inquiry, scope))
            except Exception as e:
                logger.error("DHARMA failed for inquiry %s: %s", inquiry.inquiry_id, e)
        return results
