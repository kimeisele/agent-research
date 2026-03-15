"""Tests for the Research Engine (full cycle)."""
import json
import tempfile
from pathlib import Path

from agent_research.engine import ResearchEngine


def _make_repo(tmp: Path) -> Path:
    """Create a minimal but complete repo for engine testing."""
    # Faculty
    fac = tmp / "docs" / "authority" / "faculties" / "computation-intelligence"
    fac.mkdir(parents=True)
    (fac / "00-faculty-brief.md").write_text(
        "# Computation & Intelligence\n\n"
        "## Core Questions\n\n"
        "1. **How do agents coordinate?**\n"
        "   Protocols, consensus, mesh.\n"
    )

    # Capabilities
    cap = {
        "faculties": [{"id": "computation-intelligence", "domains": ["ai", "agents"]}],
        "capabilities": {"research_synthesis": {}},
        "federation_interfaces": {"produces": ["authority_document"], "consumes": ["research_question"]},
    }
    (tmp / "docs" / "authority" / "capabilities.json").write_text(json.dumps(cap))

    # Charter
    (tmp / "docs" / "authority" / "charter.md").write_text("# Charter\nResearch for the common good.")

    # Data dir
    (tmp / "data").mkdir(parents=True)

    # Export script (minimal stub)
    (tmp / "scripts").mkdir(parents=True)
    (tmp / "scripts" / "export_authority_feed.py").write_text(
        "import sys; sys.exit(0)  # stub\n"
    )

    return tmp


def test_full_cycle():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        engine = ResearchEngine(repo, token=None, max_per_cycle=2)
        result = engine.run_cycle()

        assert result.success
        assert result.inquiries_discovered >= 1
        assert result.inquiries_scoped >= 1
        assert result.inquiries_researched >= 1
        assert result.inquiries_published >= 1

        # Verify files exist
        results_dir = repo / "docs" / "authority" / "research_results"
        assert len(list(results_dir.glob("*.md"))) >= 1
        assert len(list(results_dir.glob("*.json"))) >= 1

        # Verify ledger
        ledger = json.loads((repo / "data" / "inquiry_ledger.json").read_text())
        published = [e for e in ledger.values() if e.get("status") == "published"]
        assert len(published) >= 1

        # Verify cycle history
        history = json.loads((repo / "data" / "cycle_history.json").read_text())
        assert len(history) == 1
        assert history[0]["success"]


def test_cycle_with_no_inquiries():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / "docs" / "authority").mkdir(parents=True)
        (repo / "data").mkdir(parents=True)
        engine = ResearchEngine(repo, token=None)
        result = engine.run_cycle()
        # No inquiries = idle cycle, still success
        assert result.success
        assert result.inquiries_discovered == 0
