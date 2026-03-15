"""KARMA Phase — Research execution infrastructure.

The agent running this engine IS the intelligence. KARMA provides:
1. Data access layer (GitHub API, federation peers, local docs)
2. Research task structure (what to investigate, where to look)
3. Result collection framework (structured findings with provenance)

The executing agent (Claude, Steward, any agent) brings the reasoning.
KARMA gives them the tools and the pipeline.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

from agent_research.models import (
    ConfidenceLevel,
    Finding,
    Inquiry,
    InquiryStatus,
    ResearchResult,
    ResearchScope,
)
from agent_research.jiva import (
    RESEARCH_SYSTEM_PROMPT,
    NormalizedResponse,
    ProviderChamber,
    build_chamber_from_env,
)

logger = logging.getLogger(__name__)

REPO_OWNER = "kimeisele"


class GitHubDataLayer:
    """Data access layer for the federation mesh via GitHub API.

    This is the eyes and ears of the research engine.
    Any agent can use this to fetch data from the entire federation.
    """

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")

    def search_repos(self, query: str) -> list[dict[str, Any]]:
        """Search GitHub repos."""
        data = self._api(f"/search/repositories?q={query}&per_page=20")
        return data.get("items", []) if isinstance(data, dict) else []

    def search_code(self, query: str, org: str = REPO_OWNER) -> list[dict[str, Any]]:
        """Search code across the federation."""
        data = self._api(f"/search/code?q={query}+org:{org}&per_page=20")
        return data.get("items", []) if isinstance(data, dict) else []

    def get_repo(self, repo: str) -> dict[str, Any]:
        """Get repo metadata."""
        return self._api(f"/repos/{repo}") or {}

    def get_file(self, repo: str, path: str, branch: str = "main") -> str | None:
        """Fetch a file's content from a repo."""
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    def list_dir(self, repo: str, path: str = "", branch: str = "main") -> list[dict[str, Any]]:
        """List directory contents in a repo."""
        data = self._api(f"/repos/{repo}/contents/{path}?ref={branch}")
        return data if isinstance(data, list) else []

    def get_issues(self, repo: str, labels: str = "", state: str = "open") -> list[dict[str, Any]]:
        """Get issues from a repo."""
        params = f"state={state}&per_page=30"
        if labels:
            params += f"&labels={labels}"
        data = self._api(f"/repos/{repo}/issues?{params}")
        return data if isinstance(data, list) else []

    def get_federation_nodes(self) -> list[dict[str, Any]]:
        """Discover all federation nodes."""
        repos = self.search_repos(f"topic:agent-federation-node+org:{REPO_OWNER}")
        nodes = []
        for repo in repos:
            descriptor_raw = self.get_file(repo["full_name"], ".well-known/agent-federation.json")
            descriptor = None
            if descriptor_raw:
                try:
                    descriptor = json.loads(descriptor_raw)
                except json.JSONDecodeError:
                    pass
            nodes.append({
                "name": repo["name"],
                "full_name": repo["full_name"],
                "description": repo.get("description", ""),
                "topics": repo.get("topics", []),
                "descriptor": descriptor,
            })
        return nodes

    def get_peer_documents(self, repo: str) -> list[dict[str, Any]]:
        """Fetch authority documents from a peer node."""
        docs = []
        # Try charter
        charter = self.get_file(repo, "docs/authority/charter.md")
        if charter:
            docs.append({"type": "charter", "content": charter, "source": repo})
        # Try README
        readme = self.get_file(repo, "README.md")
        if readme:
            docs.append({"type": "readme", "content": readme, "source": repo})
        return docs

    def _api(self, path: str) -> Any:
        if not self.token:
            return {}
        url = f"https://api.github.com{path}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as e:
            logger.warning("GitHub API error for %s: %s", path, e)
            return {}


class ResearchContext:
    """Everything an agent needs to conduct research on an inquiry.

    This is the workbench. The agent reads this, reasons about it,
    and produces findings.
    """

    def __init__(self, inquiry: Inquiry, scope: ResearchScope):
        self.inquiry = inquiry
        self.scope = scope
        self.local_sources: list[dict[str, Any]] = []
        self.federation_sources: list[dict[str, Any]] = []
        self.peer_nodes: list[dict[str, Any]] = []
        self.findings: list[Finding] = []

    def add_finding(self, claim: str, evidence: list[str],
                    confidence: ConfidenceLevel = ConfidenceLevel.PRELIMINARY,
                    sources: list[str] | None = None,
                    limitations: list[str] | None = None,
                    related_domains: list[str] | None = None) -> Finding:
        """Add a research finding to the context."""
        finding = Finding(
            claim=claim,
            evidence=evidence,
            confidence=confidence,
            sources=sources or [],
            limitations=limitations or [],
            related_domains=related_domains or [],
        )
        self.findings.append(finding)
        return finding

    @property
    def all_sources(self) -> list[dict[str, Any]]:
        return self.local_sources + self.federation_sources

    def source_summary(self) -> str:
        """Human-readable summary of available sources."""
        lines = [f"Research context for: {self.inquiry.question}",
                 f"Faculties: {', '.join(self.scope.faculties)}",
                 f"Methodology: {self.scope.methodology.value}",
                 f"Local sources: {len(self.local_sources)}",
                 f"Federation sources: {len(self.federation_sources)}",
                 f"Peer nodes: {len(self.peer_nodes)}"]
        return "\n".join(lines)


class KarmaPhase:
    """KARMA: Research execution infrastructure.

    Provides the data layer and result framework. The agent running
    the engine brings the intelligence.

    For automated cycles (heartbeat), KARMA does structural analysis.
    For agent-driven research, KARMA hands the ResearchContext to the
    agent and collects their findings.
    """

    def __init__(self, repo_root: Path, token: str | None = None):
        self.repo_root = repo_root
        self.data = GitHubDataLayer(token)
        self.docs_dir = repo_root / "docs"

    def build_context(self, inquiry: Inquiry, scope: ResearchScope) -> ResearchContext:
        """Build a research context with all available data.

        This is what an agent gets to work with.
        """
        ctx = ResearchContext(inquiry, scope)

        # Collect local faculty knowledge
        faculties_dir = self.docs_dir / "authority" / "faculties"
        for faculty_id in scope.faculties:
            faculty_dir = faculties_dir / faculty_id
            if not faculty_dir.exists():
                continue
            for md_file in sorted(faculty_dir.glob("*.md")):
                ctx.local_sources.append({
                    "type": "faculty_document",
                    "faculty": faculty_id,
                    "path": str(md_file.relative_to(self.repo_root)),
                    "content": md_file.read_text(),
                })

        # Collect federation peer data
        ctx.peer_nodes = self.data.get_federation_nodes()
        for node in ctx.peer_nodes:
            if node["name"] == "agent-research":
                continue
            peer_docs = self.data.get_peer_documents(node["full_name"])
            for doc in peer_docs:
                ctx.federation_sources.append({
                    "type": f"peer_{doc['type']}",
                    "source_node": node["name"],
                    "content": doc["content"],
                })

        # Collect prior research
        results_dir = self.docs_dir / "authority" / "research_results"
        if results_dir.exists():
            for f in results_dir.glob("*.json"):
                try:
                    result = json.loads(f.read_text())
                    if set(result.get("faculties_involved", [])) & set(scope.faculties):
                        ctx.local_sources.append({
                            "type": "prior_research",
                            "title": result.get("title", ""),
                            "content": json.dumps(result, indent=2),
                        })
                except (json.JSONDecodeError, OSError):
                    continue

        logger.info("  Context built: %d local, %d federation, %d peers",
                     len(ctx.local_sources), len(ctx.federation_sources), len(ctx.peer_nodes))
        return ctx

    def auto_analyze(self, ctx: ResearchContext) -> None:
        """Automated structural analysis for heartbeat cycles.

        This is the fallback when no agent is actively reasoning.
        It does honest structural work: mapping what exists, finding
        gaps, identifying connections. No fake "findings".
        """
        inquiry = ctx.inquiry
        scope = ctx.scope
        all_content = "\n".join(s.get("content", "") for s in ctx.all_sources)
        query_terms = _extract_terms(inquiry.question)

        # 1. Map what the federation knows about this topic
        if ctx.peer_nodes:
            relevant_peers = []
            for node in ctx.peer_nodes:
                desc = node.get("descriptor") or {}
                node_text = f"{node.get('description', '')} {desc.get('display_name', '')} {' '.join(desc.get('capabilities', []))}"
                overlap = query_terms & _extract_terms(node_text)
                if overlap:
                    relevant_peers.append((node["name"], node.get("description", ""), overlap))

            if relevant_peers:
                ctx.add_finding(
                    claim="Federation nodes with relevant capabilities identified",
                    evidence=[f"{name}: {desc} (matching: {', '.join(sorted(terms))})"
                              for name, desc, terms in relevant_peers],
                    confidence=ConfidenceLevel.ESTABLISHED,
                    sources=[f"federation:{name}" for name, _, _ in relevant_peers],
                )

        # 2. Extract relevant knowledge from local faculty docs
        relevant_sections = _find_relevant_sections(all_content, query_terms)
        if relevant_sections:
            ctx.add_finding(
                claim="Existing knowledge base contains relevant material",
                evidence=[f"[{heading}]: {body[:200]}..." if len(body) > 200 else f"[{heading}]: {body}"
                          for heading, body in relevant_sections[:5]],
                confidence=ConfidenceLevel.SUPPORTED,
                sources=[s.get("path", s.get("source_node", "")) for s in ctx.local_sources[:5]],
                limitations=["Extracted from faculty briefs — research priorities, not confirmed findings"],
            )

        # 3. Cross-domain connection scan
        if len(scope.faculties) > 1 or scope.cross_domain_bridges:
            faculty_terms: dict[str, set[str]] = {}
            for s in ctx.local_sources:
                if s.get("type") == "faculty_document":
                    fac = s.get("faculty", "")
                    if fac:
                        faculty_terms.setdefault(fac, set()).update(_extract_terms(s.get("content", "")))

            for fac_a, fac_b in scope.cross_domain_bridges:
                terms_a = faculty_terms.get(fac_a, set())
                terms_b = faculty_terms.get(fac_b, set())
                shared = terms_a & terms_b - _NOISE_TERMS
                if len(shared) >= 3:
                    ctx.add_finding(
                        claim=f"Cross-domain bridge: {fac_a} ↔ {fac_b}",
                        evidence=[f"Shared concepts ({len(shared)}): {', '.join(sorted(shared, key=len, reverse=True)[:12])}"],
                        confidence=ConfidenceLevel.PRELIMINARY,
                        related_domains=[fac_a, fac_b],
                        limitations=["Term co-occurrence — not semantic analysis"],
                    )

        # 4. Always: honest gap report
        gaps = []
        if not ctx.federation_sources:
            gaps.append("No federation peer documents accessible")
        if len(ctx.local_sources) < 2:
            gaps.append("Thin local source base")
        gaps.append("Automated structural analysis only — agent-driven deep research recommended")
        ctx.add_finding(
            claim="Research gaps and limitations",
            evidence=gaps,
            confidence=ConfidenceLevel.ESTABLISHED,
        )

    def jiva_analyze(self, ctx: ResearchContext) -> None:
        """LLM-powered deep analysis via the Research Jiva.

        If providers are available, the Jiva reads ALL sources and produces
        real findings through actual reasoning — not keyword extraction.
        Falls back to auto_analyze if no providers available.
        """
        chamber = build_chamber_from_env()
        if len(chamber) == 0:
            logger.info("  Jiva offline — no API keys. Falling back to structural analysis.")
            self.auto_analyze(ctx)
            return

        # Build the research prompt with all source material
        source_text = ""
        for i, s in enumerate(ctx.all_sources):
            source_label = s.get("path", s.get("source_node", s.get("title", f"source_{i}")))
            content = s.get("content", "")
            # Truncate very long sources to stay within context limits
            if len(content) > 4000:
                content = content[:4000] + "\n[... truncated ...]"
            source_text += f"\n\n--- SOURCE: {source_label} ---\n{content}"

        user_prompt = (
            f"## Research Question\n{ctx.inquiry.question}\n\n"
            f"## Context\n{ctx.inquiry.context or 'No additional context.'}\n\n"
            f"## Faculties\n{', '.join(ctx.scope.faculties)}\n\n"
            f"## Methodology\n{ctx.scope.methodology.value}\n\n"
            f"## Source Material ({len(ctx.all_sources)} documents)\n{source_text}\n\n"
            f"Analyze these sources and produce findings. Respond with JSON only."
        )

        messages = [
            {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = chamber.invoke(messages=messages, max_tokens=2048)
            self._parse_jiva_response(ctx, response)
            logger.info("  Jiva: produced %d findings", len(ctx.findings))
        except Exception as e:
            logger.warning("  Jiva failed: %s — falling back to structural analysis", e)
            self.auto_analyze(ctx)

    def _parse_jiva_response(self, ctx: ResearchContext, response: NormalizedResponse) -> None:
        """Parse the Jiva's JSON response into findings."""
        content = response.content.strip()
        # Handle markdown code blocks
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from mixed output
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(content[start:end])
                except json.JSONDecodeError:
                    ctx.add_finding(
                        claim="Jiva produced non-parseable output",
                        evidence=[content[:500]],
                        confidence=ConfidenceLevel.UNKNOWN,
                        limitations=["LLM response could not be parsed as JSON"],
                    )
                    return
            else:
                ctx.add_finding(
                    claim="Jiva produced non-structured output",
                    evidence=[content[:500]],
                    confidence=ConfidenceLevel.UNKNOWN,
                )
                return

        # Parse findings
        confidence_map = {
            "established": ConfidenceLevel.ESTABLISHED,
            "supported": ConfidenceLevel.SUPPORTED,
            "preliminary": ConfidenceLevel.PRELIMINARY,
            "speculative": ConfidenceLevel.SPECULATIVE,
            "unknown": ConfidenceLevel.UNKNOWN,
        }

        for f_data in data.get("findings", []):
            ctx.add_finding(
                claim=f_data.get("claim", ""),
                evidence=f_data.get("evidence", []),
                confidence=confidence_map.get(f_data.get("confidence", ""), ConfidenceLevel.PRELIMINARY),
                sources=f_data.get("sources", []),
                limitations=f_data.get("limitations", []),
                related_domains=f_data.get("related_domains", []),
            )

        # Parse cross-domain insights and open questions into the context
        for insight in data.get("cross_domain_insights", []):
            ctx.add_finding(
                claim=f"Cross-domain insight: {insight}",
                evidence=[insight],
                confidence=ConfidenceLevel.PRELIMINARY,
                related_domains=ctx.scope.faculties,
            )

        for oq in data.get("open_questions", []):
            ctx.add_finding(
                claim=f"Emerging question: {oq}",
                evidence=["Identified during Jiva analysis"],
                confidence=ConfidenceLevel.SPECULATIVE,
                limitations=["Question emerged from analysis — not yet investigated"],
            )

    def run(self, inquiry: Inquiry, scope: ResearchScope) -> ResearchResult:
        """Execute KARMA: build context, analyze (Jiva or structural), produce result."""
        logger.info("KARMA: '%s'", inquiry.question[:80])
        inquiry.status = InquiryStatus.IN_RESEARCH

        ctx = self.build_context(inquiry, scope)

        # Try Jiva first, fall back to structural analysis
        self.jiva_analyze(ctx)

        inquiry.status = InquiryStatus.IN_REVIEW
        return self._to_result(ctx)

    def _to_result(self, ctx: ResearchContext) -> ResearchResult:
        """Convert research context into a publishable result."""
        inquiry = ctx.inquiry
        scope = ctx.scope
        findings = [f for f in ctx.findings if f.evidence]

        source_refs = []
        for s in ctx.all_sources:
            ref = s.get("path", s.get("source_node", s.get("title", "")))
            if ref and ref not in source_refs:
                source_refs.append(ref)

        abstract = f"Analysis of: {inquiry.question}. "
        abstract += f"Faculties: {', '.join(scope.faculties)}. "
        abstract += f"Method: {scope.methodology.value}. "
        abstract += f"{len(findings)} findings from {len(ctx.local_sources)} local + {len(ctx.federation_sources)} federation sources."

        limitations = []
        for f in findings:
            for lim in f.limitations:
                if lim not in limitations:
                    limitations.append(lim)

        open_questions = [inquiry.question]
        for f in findings:
            if f.confidence in (ConfidenceLevel.PRELIMINARY, ConfidenceLevel.SPECULATIVE):
                open_questions.append(f"Investigate further: {f.claim}")

        cross_insights = [f.claim for f in findings if len(f.related_domains) > 1]

        return ResearchResult(
            inquiry_id=inquiry.inquiry_id,
            title=inquiry.question,
            abstract=abstract,
            findings=findings,
            methodology_used=scope.methodology,
            faculties_involved=scope.faculties,
            cross_domain_insights=cross_insights,
            open_questions=open_questions,
            limitations=limitations,
            sources=source_refs,
        )


def _extract_terms(text: str) -> set[str]:
    words = re.findall(r'[a-zA-Z]{4,}', text.lower())
    return {w for w in words if w not in _STOP_WORDS}


def _find_relevant_sections(content: str, query_terms: set[str]) -> list[tuple[str, str]]:
    """Find sections in markdown content relevant to query terms."""
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("#"):
            if current_heading and current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    text_terms = _extract_terms(current_heading + " " + body)
                    if query_terms & text_terms:
                        sections.append((current_heading, body))
            current_heading = line.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading and current_lines:
        body = "\n".join(current_lines).strip()
        if body and query_terms & _extract_terms(current_heading + " " + body):
            sections.append((current_heading, body))

    return sections


_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "this", "that",
    "these", "those", "him", "her", "them", "your", "his", "its", "our",
    "their", "not", "nor", "as", "if", "then", "than", "so", "such",
    "both", "each", "all", "any", "few", "more", "most", "other", "some",
    "only", "own", "same", "too", "very", "just", "about", "above", "after",
    "also", "into", "over", "under", "between", "through", "during", "before",
    "how", "what", "which", "who", "when", "where", "why", "here", "there",
    "down", "once", "now", "new", "one", "two", "first", "well", "like",
    "make", "many", "much", "need", "know", "take", "come", "think", "look",
    "want", "give", "tell", "work", "call", "keep", "help", "talk", "turn",
})

_NOISE_TERMS = frozenset({
    "research", "systems", "system", "based", "using", "used", "data",
    "analysis", "model", "models", "approach", "methods", "design",
    "process", "development", "knowledge", "understanding", "information",
    "document", "documents", "faculty", "faculties", "authority",
    "open", "questions", "core", "scope", "cross", "domain", "connections",
})
