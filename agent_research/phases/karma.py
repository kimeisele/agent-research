"""KARMA Phase — Execute research.

This is where the actual work happens:
1. Gather sources and data
2. Analyze and extract findings
3. Synthesize across domains
4. Identify cross-domain connections
5. Assess confidence and limitations
6. Produce structured ResearchResult
"""
from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path
from typing import Any

from agent_research.models import (
    ConfidenceLevel,
    Finding,
    Inquiry,
    InquiryStatus,
    MethodologyType,
    ResearchResult,
    ResearchScope,
)

logger = logging.getLogger(__name__)


class SourceCollector:
    """Collect source material from available knowledge bases.

    Sources:
    - Local authority documents (our own published research)
    - Federation authority feeds (other nodes' publications)
    - Faculty knowledge bases
    - Cached external references
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.docs_dir = repo_root / "docs"
        self.data_dir = repo_root / "data"
        self.cache_dir = self.data_dir / "source_cache"

    def collect(self, scope: ResearchScope) -> list[dict[str, Any]]:
        """Collect relevant sources for the given scope."""
        sources: list[dict[str, Any]] = []

        # 1. Local faculty knowledge
        sources.extend(self._collect_faculty_knowledge(scope.faculties))

        # 2. Federation authority feeds from other nodes
        sources.extend(self._collect_federation_sources(scope))

        # 3. Prior research results
        sources.extend(self._collect_prior_research(scope))

        logger.info("  Collected %d sources", len(sources))
        return sources

    def _collect_faculty_knowledge(self, faculties: list[str]) -> list[dict[str, Any]]:
        """Read existing faculty documents."""
        sources = []
        faculties_dir = self.docs_dir / "authority" / "faculties"
        for faculty_id in faculties:
            faculty_dir = faculties_dir / faculty_id
            if not faculty_dir.exists():
                continue
            for md_file in faculty_dir.glob("*.md"):
                body = md_file.read_text()
                sources.append({
                    "type": "faculty_document",
                    "faculty": faculty_id,
                    "path": str(md_file.relative_to(self.repo_root)),
                    "content": body,
                    "content_hash": sha256(body.encode()).hexdigest()[:16],
                })
        return sources

    def _collect_federation_sources(self, scope: ResearchScope) -> list[dict[str, Any]]:
        """Read cached authority feeds from federation peers."""
        sources = []
        feed_cache = self.data_dir / "authority_feed_cache"
        if not feed_cache.exists():
            return sources

        for repo_dir in feed_cache.iterdir():
            if not repo_dir.is_dir():
                continue
            # Look for canonical surface exports
            for bundle_dir in repo_dir.glob("*/"):
                cs_path = bundle_dir / ".authority-exports" / "canonical-surface.json"
                if not cs_path.exists():
                    continue
                try:
                    cs = json.loads(cs_path.read_text())
                    for doc in cs.get("documents", []):
                        # Check if document is relevant to our faculties
                        doc_text = doc.get("body_markdown", "").lower()
                        for faculty in scope.faculties:
                            if faculty.replace("-", " ") in doc_text or faculty.replace("-", "") in doc_text:
                                sources.append({
                                    "type": "federation_document",
                                    "source_node": repo_dir.name,
                                    "document_id": doc.get("document_id", ""),
                                    "title": doc.get("title", ""),
                                    "content": doc.get("body_markdown", ""),
                                })
                                break
                except (json.JSONDecodeError, OSError):
                    continue
        return sources

    def _collect_prior_research(self, scope: ResearchScope) -> list[dict[str, Any]]:
        """Read previously completed research results."""
        sources = []
        results_dir = self.docs_dir / "authority" / "research_results"
        if not results_dir.exists():
            return sources

        for result_file in results_dir.glob("*.json"):
            try:
                result = json.loads(result_file.read_text())
                # Check for faculty overlap
                result_faculties = set(result.get("faculties_involved", []))
                if result_faculties & set(scope.faculties):
                    sources.append({
                        "type": "prior_research",
                        "inquiry_id": result.get("inquiry_id", ""),
                        "title": result.get("title", ""),
                        "content": json.dumps(result),
                    })
            except (json.JSONDecodeError, OSError):
                continue
        return sources


class Analyzer:
    """Analyze collected sources and extract findings.

    Phase 1 (current): Deterministic analysis — keyword extraction,
    pattern matching, structural analysis. No LLM.

    Phase 2 (future): LLM-assisted deep analysis — but only for the
    actual reasoning, not for plumbing.
    """

    def analyze(self, inquiry: Inquiry, scope: ResearchScope,
                sources: list[dict[str, Any]]) -> list[Finding]:
        """Extract findings from sources."""
        findings: list[Finding] = []

        if not sources:
            findings.append(Finding(
                claim=f"Insufficient sources available for: {inquiry.question}",
                evidence=["No relevant sources found in local knowledge base or federation feeds"],
                confidence=ConfidenceLevel.UNKNOWN,
                limitations=["No data available for analysis"],
            ))
            return findings

        # Structural analysis — what do our sources tell us?
        source_types = {}
        for s in sources:
            t = s.get("type", "unknown")
            source_types[t] = source_types.get(t, 0) + 1

        # Faculty coverage analysis
        covered_faculties = set()
        for s in sources:
            if "faculty" in s:
                covered_faculties.add(s["faculty"])

        uncovered = set(scope.faculties) - covered_faculties
        if uncovered:
            findings.append(Finding(
                claim=f"Research gap identified: faculties {uncovered} have no existing sources",
                evidence=[f"Source scan found 0 documents for {', '.join(uncovered)}"],
                confidence=ConfidenceLevel.ESTABLISHED,
                limitations=["Gap detection is based on local sources only"],
                related_domains=list(uncovered),
            ))

        # Extract key concepts from sources
        concept_mentions: dict[str, list[str]] = {}
        for s in sources:
            content = s.get("content", "")
            source_ref = s.get("title", s.get("path", s.get("document_id", "unknown")))
            # Simple concept extraction from headers
            for line in content.splitlines():
                if line.startswith("#"):
                    concept = line.lstrip("#").strip()
                    if concept and len(concept) > 3:
                        concept_mentions.setdefault(concept, []).append(source_ref)

        # Concepts mentioned across multiple sources = stronger evidence
        cross_referenced = {
            concept: refs
            for concept, refs in concept_mentions.items()
            if len(refs) > 1
        }
        if cross_referenced:
            findings.append(Finding(
                claim="Multiple sources converge on shared concepts",
                evidence=[f"'{c}' referenced by: {', '.join(r)}" for c, r in list(cross_referenced.items())[:5]],
                confidence=ConfidenceLevel.SUPPORTED,
                sources=[ref for refs in cross_referenced.values() for ref in refs],
            ))

        # Cross-domain bridge detection
        if scope.cross_domain_bridges:
            for fac_a, fac_b in scope.cross_domain_bridges:
                a_content = " ".join(s.get("content", "") for s in sources if s.get("faculty") == fac_a)
                b_content = " ".join(s.get("content", "") for s in sources if s.get("faculty") == fac_b)
                if a_content and b_content:
                    # Find shared terms between the two faculties
                    a_words = set(a_content.lower().split()) - _STOP_WORDS
                    b_words = set(b_content.lower().split()) - _STOP_WORDS
                    shared = a_words & b_words - _COMMON_WORDS
                    if shared:
                        top_shared = sorted(shared, key=lambda w: len(w), reverse=True)[:10]
                        findings.append(Finding(
                            claim=f"Cross-domain bridge identified between {fac_a} and {fac_b}",
                            evidence=[f"Shared concepts: {', '.join(top_shared)}"],
                            confidence=ConfidenceLevel.PRELIMINARY,
                            related_domains=[fac_a, fac_b],
                            limitations=["Based on keyword overlap only — deeper analysis needed"],
                        ))

        # Source quality assessment
        if sources:
            findings.append(Finding(
                claim=f"Source base: {len(sources)} documents from {len(source_types)} source types",
                evidence=[f"{t}: {c} documents" for t, c in source_types.items()],
                confidence=ConfidenceLevel.ESTABLISHED,
                sources=[s.get("title", s.get("path", "unnamed")) for s in sources[:10]],
            ))

        return findings


class Synthesizer:
    """Synthesize findings into a coherent ResearchResult."""

    def synthesize(self, inquiry: Inquiry, scope: ResearchScope,
                   findings: list[Finding], sources: list[dict[str, Any]]) -> ResearchResult:
        """Produce final research result from findings."""

        # Generate title
        title = f"Research: {inquiry.question}"
        if len(title) > 100:
            title = title[:97] + "..."

        # Generate abstract
        finding_claims = [f.claim for f in findings if f.confidence != ConfidenceLevel.UNKNOWN]
        if finding_claims:
            abstract = f"Investigation of: {inquiry.question}. "
            abstract += f"Analysis across {', '.join(scope.faculties)} using {scope.methodology.value} methodology. "
            abstract += f"{len(findings)} findings produced with overall confidence based on {len(sources)} sources."
        else:
            abstract = f"Initial investigation of: {inquiry.question}. Insufficient data for conclusive findings."

        # Identify cross-domain insights
        cross_insights = []
        for f in findings:
            if len(f.related_domains) > 1:
                cross_insights.append(f"{f.claim} (domains: {', '.join(f.related_domains)})")

        # Identify open questions
        open_questions = [inquiry.question]  # The original question is always open for deeper research
        for f in findings:
            if f.confidence in (ConfidenceLevel.PRELIMINARY, ConfidenceLevel.SPECULATIVE):
                open_questions.append(f"Needs deeper investigation: {f.claim}")
            for lim in f.limitations:
                if "needed" in lim.lower() or "further" in lim.lower():
                    open_questions.append(lim)

        # Collect all limitations
        all_limitations = []
        for f in findings:
            all_limitations.extend(f.limitations)
        all_limitations = list(dict.fromkeys(all_limitations))  # Deduplicate preserving order

        # Collect all source references
        all_sources = []
        for s in sources:
            ref = s.get("title", s.get("path", s.get("document_id", "")))
            if ref and ref not in all_sources:
                all_sources.append(ref)

        return ResearchResult(
            inquiry_id=inquiry.inquiry_id,
            title=title,
            abstract=abstract,
            findings=findings,
            methodology_used=scope.methodology,
            faculties_involved=scope.faculties,
            cross_domain_insights=cross_insights,
            open_questions=open_questions,
            limitations=all_limitations,
            sources=all_sources,
        )


class KarmaPhase:
    """KARMA: Execute research.

    The engine that does the actual work:
    1. Collect sources
    2. Analyze
    3. Synthesize
    4. Produce ResearchResult ready for MOKSHA
    """

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.collector = SourceCollector(repo_root)
        self.analyzer = Analyzer()
        self.synthesizer = Synthesizer()

    def run(self, inquiry: Inquiry, scope: ResearchScope) -> ResearchResult:
        """Execute KARMA for a single scoped inquiry.

        Returns a complete ResearchResult ready for publication.
        """
        logger.info("KARMA: Researching '%s'", inquiry.question[:80])
        inquiry.status = InquiryStatus.IN_RESEARCH

        # 1. Collect sources
        sources = self.collector.collect(scope)

        # 2. Analyze
        findings = self.analyzer.analyze(inquiry, scope, sources)
        logger.info("  Findings: %d", len(findings))

        # 3. Synthesize
        inquiry.status = InquiryStatus.IN_REVIEW
        result = self.synthesizer.synthesize(inquiry, scope, findings, sources)
        logger.info("  Result: '%s' (confidence: %s)", result.title[:60], result.overall_confidence.value)

        return result


# Common words to filter out from cross-domain analysis
_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "this", "that",
    "these", "those", "i", "you", "he", "she", "it", "we", "they", "me",
    "him", "her", "us", "them", "my", "your", "his", "its", "our", "their",
    "not", "no", "nor", "as", "if", "then", "than", "so", "such", "both",
    "each", "all", "any", "few", "more", "most", "other", "some", "only",
    "own", "same", "too", "very", "just", "about", "above", "after", "again",
    "also", "into", "over", "under", "between", "through", "during", "before",
    "how", "what", "which", "who", "when", "where", "why", "here", "there",
    "up", "out", "off", "down", "once", "now", "new", "one", "two", "first",
})

_COMMON_WORDS = frozenset({
    "research", "systems", "system", "based", "using", "used", "data",
    "analysis", "model", "models", "approach", "methods", "design",
    "process", "development", "knowledge", "understanding", "information",
    "-", "--", "---", "##", "###", "|", "*", "**",
})
