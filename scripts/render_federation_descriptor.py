from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _display_name(repo_name: str) -> str:
    return " ".join(word.capitalize() for word in repo_name.replace("_", "-").split("-") if word) or repo_name


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".well-known/agent-federation.json")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "kimeisele/agent-template"))
    parser.add_argument("--status", default="active")
    parser.add_argument("--intent", action="append", default=["public_authority_page"])
    args = parser.parse_args()

    repo_owner, repo_name = args.repo.split("/", 1)
    payload = {
        "kind": "agent_federation_descriptor",
        "version": 1,
        "repo_id": repo_name,
        "display_name": _display_name(repo_name),
        "authority_feed_manifest_url": f"https://raw.githubusercontent.com/{repo_owner}/{repo_name}/authority-feed/latest-authority-manifest.json",
        "projection_intents": list(dict.fromkeys(args.intent)),
        "status": args.status,
        "owner_boundary": f"{repo_name.replace('-', '_')}_surface",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())