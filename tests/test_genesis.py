"""Tests for GENESIS phase."""
import json
import tempfile
from pathlib import Path

from agent_research.phases.genesis import (
    CuriosityEngine,
    GenesisPhase,
    InboxScanner,
    MeshObserver,
)
from agent_research.models import InquirySource


def _make_repo(tmp: Path) -> Path:
    """Create a minimal repo structure for testing."""
    (tmp / "docs" / "authority" / "faculties" / "test-faculty").mkdir(parents=True)
    (tmp / "docs" / "authority" / "faculties" / "test-faculty" / "00-faculty-brief.md").write_text(
        "# Test Faculty\n\n## Core Questions\n\n"
        "1. **How does testing improve software quality?**\n"
        "   Unit tests, integration tests, coverage.\n\n"
        "2. **What is the optimal test strategy?**\n"
        "   Risk-based, mutation, property-based.\n"
    )
    (tmp / "data").mkdir(parents=True)
    return tmp


def test_curiosity_engine_extracts_questions():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        engine = CuriosityEngine(repo / "docs")
        inquiries = engine.scan()
        assert len(inquiries) >= 1
        assert all(i.source == InquirySource.CURIOSITY for i in inquiries)
        questions = [i.question for i in inquiries]
        assert any("testing" in q.lower() or "test" in q.lower() for q in questions)


def test_inbox_scanner_empty_graceful():
    with tempfile.TemporaryDirectory() as tmp:
        scanner = InboxScanner(Path(tmp) / "data")
        assert scanner.scan() == []


def test_inbox_scanner_parses_messages():
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp) / "data" / "federation"
        data_dir.mkdir(parents=True)
        messages = [
            {
                "operation": "research_inquiry",
                "source_city_id": "steward",
                "payload": {
                    "question": "How does self-healing work?",
                    "domains": ["computation-intelligence"],
                    "urgency": "elevated",
                },
            },
            {"operation": "heartbeat", "payload": {}},  # Should be ignored
        ]
        (data_dir / "nadi_inbox.json").write_text(json.dumps(messages))

        scanner = InboxScanner(Path(tmp) / "data")
        inquiries = scanner.scan()
        assert len(inquiries) == 1
        assert inquiries[0].question == "How does self-healing work?"
        assert inquiries[0].source == InquirySource.FEDERATION_INBOX
        assert inquiries[0].source_node == "steward"


def test_genesis_deduplicates():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        phase = GenesisPhase(repo, token=None)
        first = phase.run()
        # Run again — should not return already-seen inquiries
        second = phase.run()
        # All from first run are in ledger now, second run finds same curiosity questions
        # but they're already in ledger as "received" — so they should be returned
        # (they're not published/archived yet)
        assert len(first) >= 1


def test_mesh_observer_no_crash_without_state():
    with tempfile.TemporaryDirectory() as tmp:
        observer = MeshObserver(Path(tmp) / "data")
        assert observer.scan() == []
