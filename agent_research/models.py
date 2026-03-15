"""Core data models for the Research Engine."""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any


class ResearchPhase(enum.Enum):
    """The 4-phase research cycle."""
    GENESIS = "genesis"   # Discover questions
    DHARMA = "dharma"     # Select method, route faculty, scope
    KARMA = "karma"       # Execute research
    MOKSHA = "moksha"      # Publish results


class InquirySource(enum.Enum):
    """Where a research question originates."""
    FEDERATION_INBOX = "federation_inbox"       # Via nadi relay from another node
    GITHUB_ISSUE = "github_issue"               # Issue labeled research-inquiry
    MESH_OBSERVATION = "mesh_observation"        # Detected from federation traffic
    CURIOSITY = "curiosity"                     # Self-generated from cross-domain gaps
    PEER_CHALLENGE = "peer_challenge"           # Challenge to existing research


class InquiryUrgency(enum.Enum):
    STANDARD = "standard"
    ELEVATED = "elevated"
    CRITICAL = "critical"


class InquiryStatus(enum.Enum):
    RECEIVED = "received"
    TRIAGED = "triaged"
    SCOPED = "scoped"
    IN_RESEARCH = "in_research"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ConfidenceLevel(enum.Enum):
    """How confident we are in a finding."""
    ESTABLISHED = "established"   # Strong consensus, multiple confirmations
    SUPPORTED = "supported"       # Good evidence, some limitations
    PRELIMINARY = "preliminary"   # Early evidence, needs more research
    SPECULATIVE = "speculative"   # Logical inference without direct evidence
    UNKNOWN = "unknown"           # We don't know


class MethodologyType(enum.Enum):
    """Types of research methodology."""
    SYNTHESIS = "synthesis"               # Combine multiple sources
    META_ANALYSIS = "meta_analysis"       # Quantitative aggregation
    LITERATURE_REVIEW = "literature_review"
    CROSS_DOMAIN = "cross_domain"         # Bridge disciplines
    METHODOLOGY_REVIEW = "methodology_review"
    DATA_ANALYSIS = "data_analysis"
    FIRST_PRINCIPLES = "first_principles"  # Derive from fundamentals


@dataclass
class Inquiry:
    """A research question entering the engine."""
    inquiry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    question: str = ""
    context: str = ""
    source: InquirySource = InquirySource.CURIOSITY
    source_node: str = ""
    domains: list[str] = field(default_factory=list)
    urgency: InquiryUrgency = InquiryUrgency.STANDARD
    status: InquiryStatus = InquiryStatus.RECEIVED
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "inquiry_id": self.inquiry_id,
            "question": self.question,
            "context": self.context,
            "source": self.source.value,
            "source_node": self.source_node,
            "domains": self.domains,
            "urgency": self.urgency.value,
            "status": self.status.value,
            "received_at": self.received_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Inquiry:
        return cls(
            inquiry_id=data.get("inquiry_id", uuid.uuid4().hex[:12]),
            question=data.get("question", ""),
            context=data.get("context", ""),
            source=InquirySource(data.get("source", "curiosity")),
            source_node=data.get("source_node", ""),
            domains=data.get("domains", []),
            urgency=InquiryUrgency(data.get("urgency", "standard")),
            status=InquiryStatus(data.get("status", "received")),
            received_at=data.get("received_at", datetime.now(timezone.utc).isoformat()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ResearchScope:
    """Defined scope for a research task (output of DHARMA)."""
    inquiry_id: str = ""
    faculties: list[str] = field(default_factory=list)
    methodology: MethodologyType = MethodologyType.SYNTHESIS
    depth: str = "standard"  # quick | standard | deep | exhaustive
    cross_domain_bridges: list[tuple[str, str]] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    estimated_sources: int = 3


@dataclass
class Finding:
    """A single research finding."""
    finding_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    claim: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.UNKNOWN
    sources: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    related_domains: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "finding_id": self.finding_id,
            "claim": self.claim,
            "evidence": self.evidence,
            "confidence": self.confidence.value,
            "sources": self.sources,
            "limitations": self.limitations,
            "related_domains": self.related_domains,
        }


@dataclass
class ResearchResult:
    """Complete research output (input to MOKSHA)."""
    inquiry_id: str = ""
    title: str = ""
    abstract: str = ""
    findings: list[Finding] = field(default_factory=list)
    methodology_used: MethodologyType = MethodologyType.SYNTHESIS
    faculties_involved: list[str] = field(default_factory=list)
    cross_domain_insights: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    completed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def content_hash(self) -> str:
        import json
        # Hash the core content without including the hash itself
        hashable = {
            "inquiry_id": self.inquiry_id,
            "title": self.title,
            "abstract": self.abstract,
            "findings": [f.to_dict() for f in self.findings],
            "methodology_used": self.methodology_used.value,
            "faculties_involved": self.faculties_involved,
            "sources": self.sources,
            "completed_at": self.completed_at,
        }
        content = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
        return sha256(content.encode()).hexdigest()

    @property
    def overall_confidence(self) -> ConfidenceLevel:
        if not self.findings:
            return ConfidenceLevel.UNKNOWN
        levels = [f.confidence for f in self.findings]
        # Weakest link — overall confidence is the lowest finding
        order = list(ConfidenceLevel)
        return max(levels, key=lambda l: order.index(l))

    def to_dict(self) -> dict:
        return {
            "inquiry_id": self.inquiry_id,
            "title": self.title,
            "abstract": self.abstract,
            "findings": [f.to_dict() for f in self.findings],
            "methodology_used": self.methodology_used.value,
            "faculties_involved": self.faculties_involved,
            "cross_domain_insights": self.cross_domain_insights,
            "open_questions": self.open_questions,
            "limitations": self.limitations,
            "sources": self.sources,
            "overall_confidence": self.overall_confidence.value,
            "content_hash": self.content_hash,
            "completed_at": self.completed_at,
        }

    def to_authority_document(self) -> str:
        """Render as dual-publish authority document.

        Every research document has two sections:
        - "For the Mesh" — technical findings, machine-readable, for federation peers
        - "For the World" — what this means for humans, readable, transferable
        """
        lines = [
            f"# {self.title}",
            "",
            f"*Inquiry ID: {self.inquiry_id} | Confidence: {self.overall_confidence.value} | "
            f"Domains: {', '.join(self.faculties_involved)}*",
            "",
            "## Abstract",
            self.abstract,
            "",
            "---",
            "",
            "# Part I: For the Mesh",
            "",
            "*Technical findings for federation nodes and agent systems.*",
            "",
            "## Methodology",
            f"- **Type:** {self.methodology_used.value}",
            f"- **Domains:** {', '.join(self.faculties_involved)}",
            f"- **Sources analyzed:** {len(self.sources)}",
            "",
            "## Findings",
        ]
        for f in self.findings:
            lines.append(f"\n### [{f.confidence.value.upper()}] {f.claim}")
            if f.evidence:
                lines.append("\n**Evidence:**")
                for e in f.evidence:
                    lines.append(f"- {e}")
            if f.limitations:
                lines.append("\n**Limitations:**")
                for lim in f.limitations:
                    lines.append(f"- {lim}")
            if f.sources:
                lines.append("\n**Sources:**")
                for s in f.sources:
                    lines.append(f"- {s}")

        if self.cross_domain_insights:
            lines.append("\n## Cross-Domain Insights")
            for i in self.cross_domain_insights:
                lines.append(f"- {i}")

        if self.open_questions:
            lines.append("\n## Open Questions")
            for q in self.open_questions:
                lines.append(f"- {q}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("# Part II: For the World")
        lines.append("")
        lines.append("*What these findings mean beyond the mesh — "
                      "for human systems, organizations, and society.*")
        lines.append("")

        # Generate human-world section from findings
        lines.append("## Why This Matters")
        lines.append("")
        if self._has_domain("agent_governance"):
            lines.append("**Governance parallel:** The challenges of decentralized decision-making "
                        "in agent meshes directly mirror challenges in human governance — "
                        "from open-source communities to international relations.")
            lines.append("")
        if self._has_domain("agent_health"):
            lines.append("**Health parallel:** Self-healing patterns in distributed systems "
                        "echo biological healing — circuit breakers as immune responses, "
                        "cascading failures as sepsis, monitoring as diagnostics.")
            lines.append("")
        if self._has_domain("agent_economics"):
            lines.append("**Economics parallel:** Resource allocation under constraints "
                        "without central planning is the fundamental problem of economics. "
                        "Every finding here has a human-economy counterpart.")
            lines.append("")
        if self._has_domain("agent_physics"):
            lines.append("**Physics parallel:** Emergent behavior in agent networks "
                        "follows patterns from physics — phase transitions, scaling laws, "
                        "information propagation. Complex systems share universal principles.")
            lines.append("")

        lines.append("## Key Takeaways for Humans")
        lines.append("")
        for f in self.findings:
            if f.confidence in (ConfidenceLevel.ESTABLISHED, ConfidenceLevel.SUPPORTED):
                lines.append(f"- {f.claim}")
        lines.append("")

        if self.limitations:
            lines.append("## Limitations")
            for lim in self.limitations:
                lines.append(f"- {lim}")
            lines.append("")

        if self.sources:
            lines.append("## Sources")
            for s in self.sources:
                lines.append(f"- {s}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## Metadata")
        lines.append(f"- Inquiry ID: `{self.inquiry_id}`")
        lines.append(f"- Overall Confidence: {self.overall_confidence.value}")
        lines.append(f"- Content Hash: `{self.content_hash}`")
        lines.append(f"- Completed: {self.completed_at}")
        lines.append("")

        return "\n".join(lines)

    def _has_domain(self, domain: str) -> bool:
        return any(domain in f for f in self.faculties_involved)
