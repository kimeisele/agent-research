"""CLI for the Research Engine."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from agent_research.engine import ResearchEngine


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="agent-research",
        description="Research Engine & Faculty of Agent Universe",
    )
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    sub = parser.add_subparsers(dest="command")

    # run-cycle: one complete GENESIS→DHARMA→KARMA→MOKSHA
    cycle_parser = sub.add_parser("run-cycle", help="Run one complete research cycle")
    cycle_parser.add_argument("--max", type=int, default=5, help="Max inquiries per cycle")

    # genesis: only discover
    sub.add_parser("genesis", help="Run GENESIS phase only (discover inquiries)")

    # status: show engine state
    sub.add_parser("status", help="Show engine status")

    # validate: run federation validation
    sub.add_parser("validate", help="Validate federation node")

    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    token = os.environ.get("GITHUB_TOKEN")

    if args.command == "run-cycle":
        engine = ResearchEngine(repo_root, token, max_per_cycle=args.max)
        result = engine.run_cycle()
        return 0 if result.success else 1

    elif args.command == "genesis":
        engine = ResearchEngine(repo_root, token)
        inquiries = engine.genesis()
        for i, inq in enumerate(inquiries, 1):
            print(f"  {i}. [{inq.source.value}] [{inq.urgency.value}] {inq.question}")
            if inq.domains:
                print(f"     Domains: {', '.join(inq.domains)}")
        print(f"\nTotal: {len(inquiries)} inquiries")
        return 0

    elif args.command == "status":
        _print_status(repo_root)
        return 0

    elif args.command == "validate":
        # Delegate to existing validation script
        import subprocess
        return subprocess.call([sys.executable, str(repo_root / "scripts" / "validate_federation.py")])

    else:
        parser.print_help()
        return 0


def _print_status(repo_root: Path) -> None:
    import json

    print("=" * 60)
    print("  RESEARCH ENGINE STATUS")
    print("=" * 60)

    # Cycle history
    history_path = repo_root / "data" / "cycle_history.json"
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text())
            last = history[-1] if history else None
            print(f"\nCycles run: {len(history)}")
            if last:
                print(f"Last cycle: {last['cycle_id']}")
                print(f"  Discovered: {last['inquiries_discovered']}")
                print(f"  Published:  {last['inquiries_published']}")
                print(f"  Errors:     {len(last.get('errors', []))}")
        except (json.JSONDecodeError, OSError):
            print("\nCycle history: unreadable")
    else:
        print("\nCycle history: none (no cycles run yet)")

    # Inquiry ledger
    ledger_path = repo_root / "data" / "inquiry_ledger.json"
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text())
            statuses = {}
            for entry in ledger.values():
                s = entry.get("status", "unknown")
                statuses[s] = statuses.get(s, 0) + 1
            print(f"\nInquiry ledger: {len(ledger)} entries")
            for s, c in sorted(statuses.items()):
                print(f"  {s}: {c}")
        except (json.JSONDecodeError, OSError):
            pass
    else:
        print("\nInquiry ledger: empty")

    # Research results
    results_dir = repo_root / "docs" / "authority" / "research_results"
    if results_dir.exists():
        md_count = len(list(results_dir.glob("*.md")))
        json_count = len(list(results_dir.glob("*.json")))
        print(f"\nPublished results: {md_count} documents, {json_count} JSON exports")
    else:
        print("\nPublished results: none")

    # Federation state
    descriptor_path = repo_root / ".well-known" / "agent-federation.json"
    if descriptor_path.exists():
        try:
            desc = json.loads(descriptor_path.read_text())
            print(f"\nFederation: {desc.get('status', '?')}")
            print(f"  Role: {desc.get('node_role', '?')}")
            print(f"  Faculties: {len(desc.get('faculties', []))}")
            print(f"  Capabilities: {len(desc.get('capabilities', []))}")
        except (json.JSONDecodeError, OSError):
            pass

    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    raise SystemExit(main())
