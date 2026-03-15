"""Research Engine — the 4-phase cognitive cycle.

GENESIS → DHARMA → KARMA → MOKSHA

The engine orchestrates the complete research lifecycle:
- Discover questions (GENESIS)
- Scope and route them (DHARMA)
- Execute research (KARMA)
- Publish results (MOKSHA)

Like Steward's heartbeat but for research: deterministic infrastructure,
LLM only where genuine reasoning is needed.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agent_research.models import Inquiry, ResearchPhase, ResearchResult, ResearchScope
from agent_research.phases.dharma import DharmaPhase
from agent_research.phases.genesis import GenesisPhase
from agent_research.phases.karma import KarmaPhase
from agent_research.phases.moksha import MokshaPhase

logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Result of one complete research cycle."""
    cycle_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    inquiries_discovered: int = 0
    inquiries_scoped: int = 0
    inquiries_researched: int = 0
    inquiries_published: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0 and self.inquiries_published >= 0

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "inquiries_discovered": self.inquiries_discovered,
            "inquiries_scoped": self.inquiries_scoped,
            "inquiries_researched": self.inquiries_researched,
            "inquiries_published": self.inquiries_published,
            "errors": self.errors,
            "success": self.success,
        }


class ResearchEngine:
    """The core research engine running the 4-phase cycle.

    Usage:
        engine = ResearchEngine(repo_root=Path("."))

        # Run one complete cycle
        result = engine.run_cycle()

        # Or run individual phases
        inquiries = engine.genesis()
        scoped = engine.dharma(inquiries)
        results = engine.karma(scoped)
        engine.moksha(results)
    """

    def __init__(self, repo_root: Path, token: str | None = None, max_per_cycle: int = 5):
        self.repo_root = repo_root
        self.max_per_cycle = max_per_cycle
        self.genesis_phase = GenesisPhase(repo_root, token)
        self.dharma_phase = DharmaPhase(repo_root)
        self.karma_phase = KarmaPhase(repo_root, token)
        self.moksha_phase = MokshaPhase(repo_root, token)
        self.history_path = repo_root / "data" / "cycle_history.json"

    def genesis(self) -> list[Inquiry]:
        """Phase 1: Discover research questions."""
        logger.info("=" * 60)
        logger.info("  PHASE: GENESIS")
        logger.info("=" * 60)
        return self.genesis_phase.run()

    def dharma(self, inquiries: list[Inquiry]) -> list[tuple[Inquiry, ResearchScope]]:
        """Phase 2: Scope and route inquiries."""
        logger.info("=" * 60)
        logger.info("  PHASE: DHARMA")
        logger.info("=" * 60)
        return self.dharma_phase.run_batch(inquiries)

    def karma(self, scoped: list[tuple[Inquiry, ResearchScope]]) -> list[tuple[Inquiry, ResearchResult]]:
        """Phase 3: Execute research."""
        logger.info("=" * 60)
        logger.info("  PHASE: KARMA")
        logger.info("=" * 60)
        results = []
        for inquiry, scope in scoped:
            try:
                result = self.karma_phase.run(inquiry, scope)
                results.append((inquiry, result))
            except Exception as e:
                logger.error("KARMA failed for %s: %s", inquiry.inquiry_id, e)
        return results

    def moksha(self, results: list[tuple[Inquiry, ResearchResult]]) -> int:
        """Phase 4: Publish results. Returns count of successful publications."""
        logger.info("=" * 60)
        logger.info("  PHASE: MOKSHA")
        logger.info("=" * 60)
        published = 0
        for inquiry, result in results:
            try:
                if self.moksha_phase.run(inquiry, result):
                    published += 1
            except Exception as e:
                logger.error("MOKSHA failed for %s: %s", inquiry.inquiry_id, e)
        return published

    def run_cycle(self, max_inquiries: int | None = None) -> CycleResult:
        """Run one complete GENESIS → DHARMA → KARMA → MOKSHA cycle.

        This is the heartbeat. Call this every N minutes.
        """
        limit = max_inquiries or self.max_per_cycle
        cycle = CycleResult(
            cycle_id=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        logger.info("=" * 60)
        logger.info("  RESEARCH ENGINE CYCLE: %s", cycle.cycle_id)
        logger.info("=" * 60)

        try:
            # GENESIS — discover questions
            inquiries = self.genesis()
            cycle.inquiries_discovered = len(inquiries)
            if not inquiries:
                logger.info("No inquiries found. Cycle complete (idle).")
                cycle.completed_at = datetime.now(timezone.utc).isoformat()
                self._record_cycle(cycle)
                return cycle

            # Limit batch size
            batch = inquiries[:limit]
            logger.info("Processing %d of %d inquiries", len(batch), len(inquiries))

            # DHARMA — scope and route
            scoped = self.dharma(batch)
            cycle.inquiries_scoped = len(scoped)

            # KARMA — research
            results = self.karma(scoped)
            cycle.inquiries_researched = len(results)

            # MOKSHA — publish
            published = self.moksha(results)
            cycle.inquiries_published = published

        except Exception as e:
            logger.error("Cycle error: %s", e)
            cycle.errors.append(str(e))

        cycle.completed_at = datetime.now(timezone.utc).isoformat()
        self._record_cycle(cycle)

        logger.info("=" * 60)
        logger.info("  CYCLE COMPLETE: %s", cycle.cycle_id)
        logger.info("  Discovered: %d  Scoped: %d  Researched: %d  Published: %d",
                     cycle.inquiries_discovered, cycle.inquiries_scoped,
                     cycle.inquiries_researched, cycle.inquiries_published)
        if cycle.errors:
            logger.info("  Errors: %d", len(cycle.errors))
        logger.info("=" * 60)

        return cycle

    def _record_cycle(self, cycle: CycleResult) -> None:
        """Persist cycle result to history."""
        history: list[dict] = []
        if self.history_path.exists():
            try:
                history = json.loads(self.history_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        history.append(cycle.to_dict())
        # Keep last 100 cycles
        history = history[-100:]

        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(json.dumps(history, indent=2) + "\n")
