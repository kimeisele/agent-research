#!/usr/bin/env python3
"""Validate that agent-research is a well-formed federation node.

Checks:
1. Federation descriptor exists and is valid
2. Authority feed generates without errors
3. All documents have required fields
4. SHA256 hashes are consistent
5. Capability manifest is valid
6. GitHub topic is set for discovery
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DESCRIPTOR_FIELDS = {"kind", "version", "repo_id", "display_name", "authority_feed_manifest_url", "status"}
REQUIRED_CAPABILITY_FIELDS = {"kind", "version", "node_id", "node_role", "faculties", "capabilities", "federation_interfaces"}
REQUIRED_DOC_FIELDS = {"document_id", "title", "wiki_name", "body_markdown"}


class ValidationError:
    def __init__(self, check: str, message: str, severity: str = "error"):
        self.check = check
        self.message = message
        self.severity = severity  # error | warning

    def __str__(self) -> str:
        icon = "\u2717" if self.severity == "error" else "\u26a0"
        return f"  {icon} [{self.check}] {self.message}"


def validate_descriptor() -> list[ValidationError]:
    """Validate .well-known/agent-federation.json"""
    errors = []
    path = REPO_ROOT / ".well-known" / "agent-federation.json"
    if not path.exists():
        errors.append(ValidationError("descriptor", "Missing .well-known/agent-federation.json"))
        return errors

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        errors.append(ValidationError("descriptor", f"Invalid JSON: {e}"))
        return errors

    missing = REQUIRED_DESCRIPTOR_FIELDS - set(data.keys())
    if missing:
        errors.append(ValidationError("descriptor", f"Missing fields: {missing}"))

    if data.get("kind") != "agent_federation_descriptor":
        errors.append(ValidationError("descriptor", f"Wrong kind: {data.get('kind')}"))

    if data.get("status") != "active":
        errors.append(ValidationError("descriptor", f"Status is '{data.get('status')}', expected 'active'", "warning"))

    if not data.get("authority_feed_manifest_url", "").startswith("https://"):
        errors.append(ValidationError("descriptor", "authority_feed_manifest_url must be HTTPS"))

    return errors


def validate_capabilities() -> list[ValidationError]:
    """Validate docs/authority/capabilities.json"""
    errors = []
    path = REPO_ROOT / "docs" / "authority" / "capabilities.json"
    if not path.exists():
        errors.append(ValidationError("capabilities", "Missing capabilities.json"))
        return errors

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        errors.append(ValidationError("capabilities", f"Invalid JSON: {e}"))
        return errors

    missing = REQUIRED_CAPABILITY_FIELDS - set(data.keys())
    if missing:
        errors.append(ValidationError("capabilities", f"Missing fields: {missing}"))

    faculties = data.get("faculties", [])
    if not faculties:
        errors.append(ValidationError("capabilities", "No faculties defined"))

    for f in faculties:
        if not f.get("id"):
            errors.append(ValidationError("capabilities", f"Faculty missing 'id': {f}"))
        if not f.get("domains"):
            errors.append(ValidationError("capabilities", f"Faculty '{f.get('id', '?')}' has no domains"))

    interfaces = data.get("federation_interfaces", {})
    if not interfaces.get("produces"):
        errors.append(ValidationError("capabilities", "No 'produces' in federation_interfaces"))
    if not interfaces.get("consumes"):
        errors.append(ValidationError("capabilities", "No 'consumes' in federation_interfaces"))

    return errors


def validate_authority_feed() -> list[ValidationError]:
    """Run the export script and validate output."""
    errors = []
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "export_authority_feed.py"), "--output-dir", tmpdir],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            errors.append(ValidationError("feed", f"Export failed: {result.stderr}"))
            return errors

        manifest_path = Path(tmpdir) / "latest-authority-manifest.json"
        if not manifest_path.exists():
            errors.append(ValidationError("feed", "No manifest generated"))
            return errors

        manifest = json.loads(manifest_path.read_text())
        if manifest.get("kind") != "source_authority_feed_manifest":
            errors.append(ValidationError("feed", f"Wrong manifest kind: {manifest.get('kind')}"))

        if manifest.get("contract_version") != 1:
            errors.append(ValidationError("feed", f"Unsupported contract_version: {manifest.get('contract_version')}"))

        # Verify bundle hash
        bundle_info = manifest.get("bundle", {})
        bundle_path = Path(tmpdir) / bundle_info.get("path", "")
        if bundle_path.exists():
            actual_sha = sha256(bundle_path.read_bytes()).hexdigest()
            if actual_sha != bundle_info.get("sha256"):
                errors.append(ValidationError("feed", f"Bundle SHA256 mismatch: expected {bundle_info.get('sha256')}, got {actual_sha}"))

            bundle = json.loads(bundle_path.read_text())
            doc_count = bundle.get("document_count", 0)
            if doc_count == 0:
                errors.append(ValidationError("feed", "Bundle has 0 documents"))
        else:
            errors.append(ValidationError("feed", f"Bundle not found at {bundle_info.get('path')}"))

        # Verify artifact hashes
        for artifact_key, artifact_info in manifest.get("artifacts", {}).items():
            artifact_path = Path(tmpdir) / artifact_info.get("path", "")
            if artifact_path.exists():
                actual_sha = sha256(artifact_path.read_bytes()).hexdigest()
                if actual_sha != artifact_info.get("sha256"):
                    errors.append(ValidationError("feed", f"Artifact SHA256 mismatch for {artifact_key}"))
            else:
                errors.append(ValidationError("feed", f"Artifact not found: {artifact_key}"))

        # Validate canonical surface documents
        for artifact_key, artifact_info in manifest.get("artifacts", {}).items():
            artifact_path = Path(tmpdir) / artifact_info["path"]
            if not artifact_path.exists():
                continue
            artifact_data = json.loads(artifact_path.read_text())
            if artifact_data.get("kind") == "canonical_surface":
                for doc in artifact_data.get("documents", []):
                    missing = REQUIRED_DOC_FIELDS - set(doc.keys())
                    if missing:
                        errors.append(ValidationError("feed", f"Document '{doc.get('document_id', '?')}' missing fields: {missing}"))
                    if not doc.get("body_markdown", "").strip():
                        errors.append(ValidationError("feed", f"Document '{doc.get('document_id', '?')}' has empty body"))

    return errors


def validate_faculty_structure() -> list[ValidationError]:
    """Validate that faculty directories match capabilities."""
    errors = []
    faculties_dir = REPO_ROOT / "docs" / "authority" / "faculties"
    cap_path = REPO_ROOT / "docs" / "authority" / "capabilities.json"

    if not faculties_dir.exists():
        errors.append(ValidationError("structure", "Missing docs/authority/faculties/ directory"))
        return errors

    if not cap_path.exists():
        return errors

    capabilities = json.loads(cap_path.read_text())
    declared_ids = {f["id"] for f in capabilities.get("faculties", [])}
    actual_dirs = {d.name for d in faculties_dir.iterdir() if d.is_dir()}

    missing_dirs = declared_ids - actual_dirs
    if missing_dirs:
        errors.append(ValidationError("structure", f"Declared faculties without directories: {missing_dirs}"))

    extra_dirs = actual_dirs - declared_ids
    if extra_dirs:
        errors.append(ValidationError("structure", f"Directories without declaration in capabilities: {extra_dirs}", "warning"))

    for d in faculties_dir.iterdir():
        if d.is_dir():
            md_files = list(d.glob("*.md"))
            if not md_files:
                errors.append(ValidationError("structure", f"Faculty '{d.name}' has no documents"))

    return errors


def validate_github_topic() -> list[ValidationError]:
    """Check if the repo has the agent-federation-node topic."""
    errors = []
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        errors.append(ValidationError("discovery", "No GITHUB_TOKEN — cannot verify topics", "warning"))
        return errors

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com/repos/kimeisele/agent-research",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            topics = data.get("topics", [])
            if "agent-federation-node" not in topics:
                errors.append(ValidationError("discovery", f"Missing 'agent-federation-node' topic. Current: {topics}"))
            else:
                pass  # OK
    except Exception as e:
        errors.append(ValidationError("discovery", f"Cannot check topics: {e}", "warning"))

    return errors


def main() -> int:
    print("=" * 60)
    print("  FEDERATION NODE VALIDATION: agent-research")
    print("=" * 60)

    all_errors: list[ValidationError] = []
    checks = [
        ("Federation Descriptor", validate_descriptor),
        ("Capability Manifest", validate_capabilities),
        ("Faculty Structure", validate_faculty_structure),
        ("Authority Feed", validate_authority_feed),
        ("GitHub Discovery", validate_github_topic),
    ]

    for name, check_fn in checks:
        print(f"\n--- {name} ---")
        errors = check_fn()
        all_errors.extend(errors)
        if errors:
            for e in errors:
                print(str(e))
        else:
            print(f"  \u2713 All checks passed")

    error_count = sum(1 for e in all_errors if e.severity == "error")
    warning_count = sum(1 for e in all_errors if e.severity == "warning")

    print(f"\n{'=' * 60}")
    if error_count:
        print(f"  FAILED: {error_count} error(s), {warning_count} warning(s)")
        return 1
    elif warning_count:
        print(f"  PASSED with {warning_count} warning(s)")
        return 0
    else:
        print("  ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
