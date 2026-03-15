from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _display_name(repo_name: str) -> str:
    return " ".join(word.capitalize() for word in repo_name.replace("_", "-").split("-") if word) or repo_name


def _load_capabilities(repo_root: Path) -> dict | None:
    cap_path = repo_root / "docs" / "authority" / "capabilities.json"
    if cap_path.exists():
        return json.loads(cap_path.read_text())
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".well-known/agent-federation.json")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "kimeisele/agent-research"))
    parser.add_argument("--status", default="active")
    parser.add_argument("--intent", action="append", default=["public_authority_page"])
    args = parser.parse_args()

    repo_owner, repo_name = args.repo.split("/", 1)
    repo_root = Path(__file__).resolve().parents[1]
    capabilities = _load_capabilities(repo_root)

    payload = {
        "kind": "agent_federation_descriptor",
        "version": 2,
        "repo_id": repo_name,
        "display_name": "Research Engine & Faculty of Agent Universe",
        "description": "Multidisciplinary research institution serving the federation with open knowledge production, synthesis, and cross-domain analysis.",
        "node_role": "research_engine_faculty",
        "authority_feed_manifest_url": f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/authority-feed/latest-authority-manifest.json",
        "projection_intents": list(dict.fromkeys(args.intent + [
            "research_synthesis",
            "open_inquiry",
            "cross_domain_analysis",
        ])),
        "status": args.status,
        "owner_boundary": f"{repo_name.replace('-', '_')}_surface",
    }

    if capabilities:
        payload["faculties"] = [f["id"] for f in capabilities.get("faculties", [])]
        payload["capabilities"] = list(capabilities.get("capabilities", {}).keys())
        payload["federation_interfaces"] = capabilities.get("federation_interfaces", {})

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
