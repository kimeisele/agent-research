"""Tests for Nadi delivery dedup ledger."""
import json
import tempfile
from pathlib import Path

from agent_research.peer_review import DeliveryLedger


class TestDeliveryLedger:
    def test_empty_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            ledger = DeliveryLedger(path)
            assert len(ledger) == 0
            assert not ledger.has_been_delivered("hermes-sankhya-25", "inq-001")

    def test_record_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            ledger = DeliveryLedger(path)

            assert not ledger.has_been_delivered("hermes-sankhya-25", "inq-001")
            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            assert ledger.has_been_delivered("hermes-sankhya-25", "inq-001")
            assert len(ledger) == 1

    def test_diff_repos_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            ledger = DeliveryLedger(path)

            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            assert ledger.has_been_delivered("hermes-sankhya-25", "inq-001")
            assert not ledger.has_been_delivered("steward-federation", "inq-001")
            assert len(ledger) == 1

    def test_diff_inquiries_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            ledger = DeliveryLedger(path)

            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            assert ledger.has_been_delivered("hermes-sankhya-25", "inq-001")
            assert not ledger.has_been_delivered("hermes-sankhya-25", "inq-002")
            assert len(ledger) == 1

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            ledger = DeliveryLedger(path)
            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            ledger.record_delivery("hermes-sankhya-25", "inq-002")
            ledger.record_delivery("steward-federation", "inq-001")
            assert len(ledger) == 3
            ledger.save()
            assert path.exists()

            # Reload from disk
            ledger2 = DeliveryLedger(path)
            assert len(ledger2) == 3
            assert ledger2.has_been_delivered("hermes-sankhya-25", "inq-001")
            assert ledger2.has_been_delivered("hermes-sankhya-25", "inq-002")
            assert ledger2.has_been_delivered("steward-federation", "inq-001")

    def test_same_key_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            ledger = DeliveryLedger(path)

            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            assert len(ledger) == 1  # No duplicates

    def test_handles_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("not valid json{{{")

            ledger = DeliveryLedger(path)
            assert len(ledger) == 0  # Graceful fallback

    def test_handles_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nonexistent" / "delivery_ledger.json"
            ledger = DeliveryLedger(path)
            assert len(ledger) == 0
            # Should not crash on save
            ledger.record_delivery("hermes-sankhya-25", "inq-001")
            ledger.save()
            assert path.exists()

    def test_delivery_key_format_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delivery_ledger.json"
            ledger = DeliveryLedger(path)
            ledger.record_delivery("hermes-sankhya-25", "inq-abc123")
            ledger.save()

            raw = json.loads(path.read_text())
            expected_key = "hermes-sankhya-25:review-request:inq-abc123"
            assert expected_key in raw["delivered"]
