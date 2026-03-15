from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha256
from pathlib import Path


def _git_output(repo_root: Path, args: list[str]) -> str:
    return subprocess.check_output(["git", "-C", str(repo_root), *args], text=True).strip()


def _canonical_sha(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=".authority-feed-out")
    parser.add_argument("--repo-id")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    output_root = Path(args.output_dir)
    if not output_root.is_absolute():
        output_root = repo_root / output_root
    repo_id = args.repo_id or repo_root.name
    source_sha = _git_output(repo_root, ["rev-parse", "HEAD"])
    generated_at = 0.0
    repo_label = " ".join(word.capitalize() for word in repo_id.replace("_", "-").split("-") if word) or repo_id
    charter_path = repo_root / "docs/authority/charter.md"
    charter_body = charter_path.read_text().strip()
    version_root = output_root / "bundles" / source_sha
    version_root.mkdir(parents=True, exist_ok=True)

    payloads = {
        "canonical_surface": {
            "kind": "canonical_surface",
            "documents": [{"document_id": "charter", "title": f"{repo_label} Charter", "wiki_name": "Charter", "body_markdown": charter_body}],
        },
        "public_summary_registry": {
            "kind": "public_summary_registry",
            "records": [{"id": "charter", "public_summary": charter_body.splitlines()[0].lstrip('# ').strip() or f"{repo_label} public charter"}],
        },
        "source_surface_registry": {
            "kind": "source_surface_registry",
            "pages": [{"id": "charter", "wiki_name": "Charter", "include_in_sidebar": True}],
        },
        "surface_metadata": {
            "kind": "surface_metadata",
            "public_surface": {"repo_label": repo_label},
            "surface_registry": {"kind": "wiki_surface_registry", "page_count": 1},
        },
    }
    relative_paths = {
        "canonical_surface": ".authority-exports/canonical-surface.json",
        "public_summary_registry": ".authority-exports/public-summary-registry.json",
        "source_surface_registry": ".authority-exports/source-surface-registry.json",
        "surface_metadata": ".authority-exports/surface-metadata.json",
    }
    authority_exports = []
    artifacts = {}
    for export_kind, relative_path in relative_paths.items():
        payload = payloads[export_kind]
        artifact_path = version_root / relative_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        authority_exports.append(
            {
                "export_id": f"{repo_id}/{export_kind}",
                "repo_id": repo_id,
                "export_kind": export_kind,
                "version": source_sha,
                "artifact_uri": relative_path,
                "generated_at": generated_at,
                "contract_version": 1,
                "content_sha256": _canonical_sha(payload),
                "labels": {"source_sha": source_sha},
            },
        )
        artifacts[relative_path] = {"path": str(Path("bundles") / source_sha / relative_path), "sha256": sha256(artifact_path.read_bytes()).hexdigest()}

    bundle = {
        "kind": "source_authority_bundle",
        "contract_version": 1,
        "generated_at": generated_at,
        "source_sha": source_sha,
        "repo_role": {"repo_id": repo_id, "role": "normative_source", "owner_boundary": f"{repo_id.replace('-', '_')}_surface", "exports": list(relative_paths), "consumes": [], "publication_targets": [f"{repo_id}-public-wiki"], "labels": {"display_name": repo_label}},
        "authority_exports": authority_exports,
        "artifact_paths": {record["export_kind"]: record["artifact_uri"] for record in authority_exports},
    }
    bundle_path = version_root / "source-authority-bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    manifest = {
        "kind": "source_authority_feed_manifest",
        "contract_version": 1,
        "generated_at": generated_at,
        "source_repo_id": repo_id,
        "source_sha": source_sha,
        "bundle": {"kind": "source_authority_bundle", "path": str(Path("bundles") / source_sha / "source-authority-bundle.json"), "sha256": sha256(bundle_path.read_bytes()).hexdigest()},
        "artifacts": artifacts,
    }
    manifest_path = output_root / "latest-authority-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())