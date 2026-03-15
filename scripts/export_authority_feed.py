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


def _collect_authority_documents(repo_root: Path) -> list[dict]:
    """Collect all markdown documents from the authority directory tree."""
    authority_dir = repo_root / "docs" / "authority"
    documents = []

    # Charter is always first
    charter_path = authority_dir / "charter.md"
    if charter_path.exists():
        documents.append({
            "document_id": "charter",
            "title": "Research Engine & Faculty Charter",
            "wiki_name": "Charter",
            "body_markdown": charter_path.read_text().strip(),
            "category": "governance",
        })

    # Faculty briefs
    faculties_dir = authority_dir / "faculties"
    if faculties_dir.exists():
        for faculty_dir in sorted(faculties_dir.iterdir()):
            if not faculty_dir.is_dir():
                continue
            for md_file in sorted(faculty_dir.glob("*.md")):
                doc_id = f"{faculty_dir.name}/{md_file.stem}"
                body = md_file.read_text().strip()
                title_line = body.splitlines()[0].lstrip("# ").strip() if body else faculty_dir.name
                documents.append({
                    "document_id": doc_id,
                    "title": title_line,
                    "wiki_name": title_line.replace(" ", "-"),
                    "body_markdown": body,
                    "category": "faculty",
                    "faculty": faculty_dir.name,
                })

    # Capabilities manifest
    cap_path = authority_dir / "capabilities.json"
    if cap_path.exists():
        documents.append({
            "document_id": "capabilities",
            "title": "Agent Capability Manifest",
            "wiki_name": "Capabilities",
            "body_markdown": cap_path.read_text().strip(),
            "category": "capability",
        })

    return documents


def _collect_methodology_documents(repo_root: Path) -> list[dict]:
    """Collect methodology documents."""
    methodology_dir = repo_root / "docs" / "methodology"
    documents = []
    if methodology_dir.exists():
        for md_file in sorted(methodology_dir.glob("*.md")):
            body = md_file.read_text().strip()
            title_line = body.splitlines()[0].lstrip("# ").strip() if body else md_file.stem
            documents.append({
                "document_id": f"methodology/{md_file.stem}",
                "title": title_line,
                "wiki_name": title_line.replace(" ", "-"),
                "body_markdown": body,
                "category": "methodology",
            })
    return documents


def _collect_inquiry_documents(repo_root: Path) -> list[dict]:
    """Collect inquiry protocol documents."""
    inquiry_dir = repo_root / "docs" / "inquiries"
    documents = []
    if inquiry_dir.exists():
        for md_file in sorted(inquiry_dir.glob("*.md")):
            body = md_file.read_text().strip()
            title_line = body.splitlines()[0].lstrip("# ").strip() if body else md_file.stem
            documents.append({
                "document_id": f"inquiry/{md_file.stem}",
                "title": title_line,
                "wiki_name": title_line.replace(" ", "-"),
                "body_markdown": body,
                "category": "protocol",
            })
    return documents


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
    repo_label = "Research Engine & Faculty of Agent Universe"

    # Collect all documents
    all_documents = (
        _collect_authority_documents(repo_root)
        + _collect_methodology_documents(repo_root)
        + _collect_inquiry_documents(repo_root)
    )

    version_root = output_root / "bundles" / source_sha
    version_root.mkdir(parents=True, exist_ok=True)

    # Build payloads
    payloads = {
        "canonical_surface": {
            "kind": "canonical_surface",
            "documents": [
                {
                    "document_id": doc["document_id"],
                    "title": doc["title"],
                    "wiki_name": doc["wiki_name"],
                    "body_markdown": doc["body_markdown"],
                    "category": doc.get("category", "general"),
                }
                for doc in all_documents
            ],
        },
        "public_summary_registry": {
            "kind": "public_summary_registry",
            "records": [
                {
                    "id": doc["document_id"],
                    "public_summary": doc["title"],
                    "category": doc.get("category", "general"),
                }
                for doc in all_documents
            ],
        },
        "source_surface_registry": {
            "kind": "source_surface_registry",
            "pages": [
                {
                    "id": doc["document_id"],
                    "wiki_name": doc["wiki_name"],
                    "include_in_sidebar": True,
                    "category": doc.get("category", "general"),
                }
                for doc in all_documents
            ],
        },
        "surface_metadata": {
            "kind": "surface_metadata",
            "public_surface": {
                "repo_label": repo_label,
                "node_role": "research_engine_faculty",
                "description": "Multidisciplinary research institution serving the federation with open knowledge production, synthesis, and cross-domain analysis.",
            },
            "surface_registry": {
                "kind": "wiki_surface_registry",
                "page_count": len(all_documents),
            },
            "faculties": [
                doc.get("faculty") for doc in all_documents
                if doc.get("faculty")
            ],
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
        authority_exports.append({
            "export_id": f"{repo_id}/{export_kind}",
            "repo_id": repo_id,
            "export_kind": export_kind,
            "version": source_sha,
            "artifact_uri": relative_path,
            "generated_at": generated_at,
            "contract_version": 1,
            "content_sha256": _canonical_sha(payload),
            "labels": {"source_sha": source_sha},
        })
        artifacts[relative_path] = {
            "path": str(Path("bundles") / source_sha / relative_path),
            "sha256": sha256(artifact_path.read_bytes()).hexdigest(),
        }

    bundle = {
        "kind": "source_authority_bundle",
        "contract_version": 1,
        "generated_at": generated_at,
        "source_sha": source_sha,
        "repo_role": {
            "repo_id": repo_id,
            "role": "research_engine_faculty",
            "owner_boundary": f"{repo_id.replace('-', '_')}_surface",
            "exports": list(relative_paths),
            "consumes": [
                "research_question",
                "raw_data_feed",
                "domain_observation",
                "inquiry_request",
                "peer_review_challenge",
            ],
            "publication_targets": [
                f"{repo_id}-public-wiki",
                f"{repo_id}-research-feed",
            ],
            "labels": {
                "display_name": repo_label,
                "node_role": "research_engine_faculty",
            },
        },
        "authority_exports": authority_exports,
        "artifact_paths": {
            record["export_kind"]: record["artifact_uri"]
            for record in authority_exports
        },
        "document_count": len(all_documents),
        "faculties": list({doc.get("faculty") for doc in all_documents if doc.get("faculty")}),
    }

    bundle_path = version_root / "source-authority-bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")

    manifest = {
        "kind": "source_authority_feed_manifest",
        "contract_version": 1,
        "generated_at": generated_at,
        "source_repo_id": repo_id,
        "source_sha": source_sha,
        "bundle": {
            "kind": "source_authority_bundle",
            "path": str(Path("bundles") / source_sha / "source-authority-bundle.json"),
            "sha256": sha256(bundle_path.read_bytes()).hexdigest(),
        },
        "artifacts": artifacts,
    }

    manifest_path = output_root / "latest-authority-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
