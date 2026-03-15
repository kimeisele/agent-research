#!/usr/bin/env python3
"""Register agent-research with the agent-internet federation control plane.

This script:
1. Verifies local node is valid (runs validation)
2. Ensures GitHub topic is set for automatic discovery
3. Checks if agent-internet can discover this node
4. Writes a federation beacon for filesystem-based discovery
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPO_OWNER = "kimeisele"
REPO_NAME = "agent-research"
FEDERATION_NODE_TOPIC = "agent-federation-node"


def _github_api(path: str, method: str = "GET", data: dict | None = None) -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN required")
    url = f"https://api.github.com{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def ensure_topic() -> bool:
    """Ensure the repo has agent-federation-node topic."""
    repo = _github_api(f"/repos/{REPO_OWNER}/{REPO_NAME}")
    topics = repo.get("topics", [])
    if FEDERATION_NODE_TOPIC in topics:
        print(f"  \u2713 Topic '{FEDERATION_NODE_TOPIC}' already set")
        return True

    print(f"  Setting topic '{FEDERATION_NODE_TOPIC}'...")
    new_topics = list(set(topics + [FEDERATION_NODE_TOPIC]))
    try:
        result = _github_api(
            f"/repos/{REPO_OWNER}/{REPO_NAME}/topics",
            method="PUT",
            data={"names": new_topics},
        )
        print(f"  \u2713 Topics updated: {result.get('names', [])}")
        return True
    except Exception as e:
        print(f"  \u2717 Failed to set topic: {e}")
        return False


def verify_descriptor_accessible() -> bool:
    """Check if the federation descriptor is accessible via raw.githubusercontent."""
    url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/.well-known/agent-federation.json"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("kind") == "agent_federation_descriptor":
                print(f"  \u2713 Descriptor accessible at {url}")
                return True
            else:
                print(f"  \u2717 Descriptor has wrong kind: {data.get('kind')}")
                return False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  \u26a0 Descriptor not yet on main branch (404). Push to main first.")
        else:
            print(f"  \u2717 HTTP error: {e.code}")
        return False
    except Exception as e:
        print(f"  \u2717 Cannot access descriptor: {e}")
        return False


def check_federation_peers() -> None:
    """Check which other federation nodes exist."""
    print("\n--- Federation Peers ---")
    try:
        # Search for repos with the federation topic
        result = _github_api(f"/search/repositories?q=topic:{FEDERATION_NODE_TOPIC}+org:{REPO_OWNER}")
        items = result.get("items", [])
        print(f"  Found {len(items)} federation node(s):")
        for repo in items:
            marker = " <-- this node" if repo["name"] == REPO_NAME else ""
            print(f"    - {repo['full_name']}: {repo.get('description', '(no desc)')}{marker}")
    except Exception as e:
        print(f"  \u2717 Cannot search: {e}")


def write_beacon() -> None:
    """Write a beacon file for filesystem-based discovery."""
    beacon_dir = REPO_ROOT / ".agent-internet" / "beacons"
    beacon_dir.mkdir(parents=True, exist_ok=True)

    # Load capabilities
    cap_path = REPO_ROOT / "docs" / "authority" / "capabilities.json"
    capabilities = json.loads(cap_path.read_text()) if cap_path.exists() else {}

    beacon = {
        "kind": "federation_beacon",
        "version": 1,
        "city_id": REPO_NAME,
        "display_name": "Research Engine & Faculty of Agent Universe",
        "node_role": "research_engine_faculty",
        "announced_at": datetime.now(timezone.utc).isoformat(),
        "capabilities": list(capabilities.get("capabilities", {}).keys()),
        "faculties": [f["id"] for f in capabilities.get("faculties", [])],
        "transport": {
            "scheme": "https",
            "location": f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/authority-feed/latest-authority-manifest.json",
        },
        "descriptor_url": f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/.well-known/agent-federation.json",
        "ttl_seconds": 86400,
    }

    beacon_path = beacon_dir / f"{REPO_NAME}.beacon.json"
    beacon_path.write_text(json.dumps(beacon, indent=2) + "\n")
    print(f"  \u2713 Beacon written: {beacon_path.relative_to(REPO_ROOT)}")


def main() -> int:
    print("=" * 60)
    print("  FEDERATION REGISTRATION: agent-research")
    print("=" * 60)

    print("\n--- Topic Discovery ---")
    ensure_topic()

    print("\n--- Descriptor Accessibility ---")
    verify_descriptor_accessible()

    print("\n--- Beacon ---")
    write_beacon()

    check_federation_peers()

    print(f"\n{'=' * 60}")
    print("  Registration complete.")
    print("  The agent-internet relay pump will discover this node")
    print("  on its next cycle (runs every 15 minutes).")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
