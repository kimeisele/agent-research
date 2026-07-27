"""Tests for PeerReviewRequester remote-marker dedup.

All dedup is remote — the requester searches the target repository for
an existing issue containing the delivery-key marker before creating.
"""
from __future__ import annotations

from agent_research.peer_review import (
    PeerReviewRequester,
    _delivery_key,
    _delivery_marker,
)
from agent_research.models import (
    ConfidenceLevel,
    Finding,
    ResearchResult,
    MethodologyType,
)


def _make_result(inquiry_id: str = "inq-001", title: str = "Test Inquiry") -> ResearchResult:
    return ResearchResult(
        inquiry_id=inquiry_id,
        title=title,
        abstract="A test abstract.",
        findings=[
            Finding(
                claim="Test claim",
                evidence=["some evidence"],
                confidence=ConfidenceLevel.SUPPORTED,
            )
        ],
        methodology_used=MethodologyType.DATA_ANALYSIS,
        faculties_involved=["computation-intelligence"],
    )


# ---------------------------------------------------------------------------
# Fake NadiTransport that lets us control the dedup search and issue
# creation independently, simulating the GitHub API without real HTTP.
# ---------------------------------------------------------------------------

class _FakeNadi:
    """Configurable fake: search_issues returns hits that contain the
    requested body_contains substring, or None on API failure.

    Set ``search_fails`` to True to simulate a network error.
    Set ``existing_issues`` to a list of dicts with 'body' keys.
    """

    def __init__(self, existing_issues: list[dict] | None = None,
                 search_fails: bool = False):
        self.existing_issues: list[dict] = existing_issues or []
        self.search_fails = search_fails
        self.created_issues: list[dict] = []

    def search_issues(self, repo, body_contains):
        if self.search_fails:
            return None
        return [i for i in self.existing_issues
                if body_contains in i.get("body", "")]

    def _create_issue(self, repo, title, body, labels=None):
        issue = {
            "repo": repo,
            "title": title,
            "body": body,
            "labels": labels or [],
            "number": len(self.created_issues) + 1,
        }
        self.created_issues.append(issue)
        return issue


def _find_marker_in_created(body: str, repo: str, inquiry_id: str) -> bool:
    return _delivery_marker(_delivery_key(repo, inquiry_id)) in body


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

class TestDeliveryMarkerFormat:
    def test_key_is_deterministic(self):
        assert _delivery_key("hermes-sankhya-25", "inq-abc") == _delivery_key("hermes-sankhya-25", "inq-abc")

    def test_key_differs_by_repo(self):
        k1 = _delivery_key("hermes-sankhya-25", "inq-001")
        k2 = _delivery_key("steward-federation", "inq-001")
        assert k1 != k2

    def test_key_differs_by_inquiry(self):
        k1 = _delivery_key("hermes-sankhya-25", "inq-001")
        k2 = _delivery_key("hermes-sankhya-25", "inq-002")
        assert k1 != k2

    def test_marker_is_hidden_html_comment(self):
        m = _delivery_marker("hermes-sankhya-25:review-request:inq-001")
        assert m.startswith("<!--")
        assert m.endswith("-->")
        assert "nadi-delivery-key" in m


class TestRemoteDedup:
    """7 regression tests for the remote-marker dedup design."""

    # 1. First delivery creates one issue
    def test_first_delivery_creates_one_issue(self):
        nadi = _FakeNadi()  # No existing issue
        requester = PeerReviewRequester(nadi)
        result = _make_result()

        results = requester.request_reviews(result, ["hermes-sankhya-25"])
        assert len(results) == 1
        assert len(nadi.created_issues) == 1
        assert _find_marker_in_created(nadi.created_issues[0]["body"], "hermes-sankhya-25", "inq-001")

    # 2. A fresh requester on a later simulated heartbeat finds the
    #    remote marker and creates zero issues.
    def test_second_heartbeat_is_noop(self):
        # Simulate that an issue with the marker already exists on the
        # target repo (return one search hit).
        marker = _delivery_marker(_delivery_key("hermes-sankhya-25", "inq-001"))
        nadi = _FakeNadi(existing_issues=[{"number": 1, "body": marker}])
        requester = PeerReviewRequester(nadi)
        result = _make_result()

        results = requester.request_reviews(result, ["hermes-sankhya-25"])
        assert len(results) == 0
        assert len(nadi.created_issues) == 0  # No new issue

    # 3. Closed prior issues also block duplicate delivery.
    def test_closed_prior_issue_blocks_delivery(self):
        # GitHub search covers both open and closed.  The fake just
        # returns a hit — the requester doesn't inspect state.
        marker = _delivery_marker(_delivery_key("hermes-sankhya-25", "inq-001"))
        closed_issue = {"number": 5, "state": "closed", "body": marker}
        nadi = _FakeNadi(existing_issues=[closed_issue])
        requester = PeerReviewRequester(nadi)
        result = _make_result()

        results = requester.request_reviews(result, ["hermes-sankhya-25"])
        assert len(results) == 0
        assert len(nadi.created_issues) == 0

    # 4. Different inquiry IDs may create separate issues.
    def test_different_inquiry_still_creates(self):
        # Only inq-001 has a prior delivery.  inq-002 is new.
        marker001 = _delivery_marker(_delivery_key("hermes-sankhya-25", "inq-001"))
        nadi = _FakeNadi(existing_issues=[{"number": 1, "body": marker001}])
        requester = PeerReviewRequester(nadi)

        # First call: inq-001 — blocked
        r1 = requester.request_reviews(_make_result("inq-001"), ["hermes-sankhya-25"])
        assert len(r1) == 0

        # Second call: inq-002 — new delivery
        r2 = requester.request_reviews(_make_result("inq-002"), ["hermes-sankhya-25"])
        assert len(r2) == 1
        assert len(nadi.created_issues) == 1
        assert _find_marker_in_created(nadi.created_issues[0]["body"], "hermes-sankhya-25", "inq-002")

    # 5. Different target repositories remain independent.
    def test_different_repo_still_creates(self):
        marker_hs = _delivery_marker(_delivery_key("hermes-sankhya-25", "inq-001"))
        nadi = _FakeNadi(existing_issues=[{"number": 1, "body": marker_hs}])
        requester = PeerReviewRequester(nadi)
        result = _make_result()

        # hermes-sankhya-25 is blocked, steward-federation is not
        r1 = requester.request_reviews(result, ["hermes-sankhya-25"])
        assert len(r1) == 0

        # Need to reset search_results for the second repo call —
        # the fake returns the same for every call, so let's make a
        # new Nadi that returns empty for steward-federation.
        nadi2 = _FakeNadi()  # No existing issue for steward-federation
        requester2 = PeerReviewRequester(nadi2)
        r2 = requester2.request_reviews(result, ["steward-federation"])
        assert len(r2) == 1
        assert _find_marker_in_created(nadi2.created_issues[0]["body"], "steward-federation", "inq-001")

    # 6. Lookup/API failure creates no issue (fail-closed).
    def test_api_failure_creates_no_issue(self):
        nadi = _FakeNadi(search_fails=True)  # API failure
        requester = PeerReviewRequester(nadi)
        result = _make_result()

        results = requester.request_reviews(result, ["hermes-sankhya-25"])
        assert len(results) == 0
        assert len(nadi.created_issues) == 0
        assert len(requester._skipped) == 1

    # 7. The actual heartbeat construction path invokes dedup by
    #    default (no optional constructor arg needed).
    def test_constructor_accepts_only_nadi_no_ledger(self):
        """Production code in moksha.py: PeerReviewRequester(self.nadi)"""
        nadi = _FakeNadi()
        requester = PeerReviewRequester(nadi)
        # Should be constructable without any second argument
        assert isinstance(requester, PeerReviewRequester)

        # Verify dedup is active by default — existing marker blocks creation
        marker = _delivery_marker(_delivery_key("hermes-sankhya-25", "inq-001"))
        nadi.search_fails = False
        nadi.existing_issues = [{"number": 1, "body": marker}]
        results = requester.request_reviews(_make_result(), ["hermes-sankhya-25"])
        assert len(results) == 0
        assert len(nadi.created_issues) == 0  # Dedup active without ledger arg


class TestDeliveryIdempotencyIntegration:
    """Test that the full round-trip works: create → search finds marker → NOOP."""

    def test_round_trip_dedup(self):
        # First request creates an issue with marker.
        nadi1 = _FakeNadi()
        req1 = PeerReviewRequester(nadi1)
        req1.request_reviews(_make_result("inq-001"), ["hermes-sankhya-25"])
        assert len(nadi1.created_issues) == 1
        created_body = nadi1.created_issues[0]["body"]
        assert "nadi-delivery-key" in created_body

        # Second request with the created issue in search results.
        nadi2 = _FakeNadi(existing_issues=[{"number": 1, "body": created_body}])
        req2 = PeerReviewRequester(nadi2)
        r2 = req2.request_reviews(_make_result("inq-001"), ["hermes-sankhya-25"])
        assert len(r2) == 0
        assert len(nadi2.created_issues) == 0


# ---------------------------------------------------------------------------
# Query format — _build_search_query contract
# ---------------------------------------------------------------------------

class TestSearchQueryContract:
    """Verify the GitHub search query has no contradictory state filters
    and contains the required qualifiers."""

    def test_query_omits_state_filters(self,):
        from agent_research.nadi import NadiTransport
        nadi = NadiTransport(token="fake")
        q = nadi._build_search_query("kimeisele/hermes-sankhya-25", "<!-- marker -->")
        assert "state:open" not in q, f"unexpected state:open in: {q}"
        assert "state:closed" not in q, f"unexpected state:closed in: {q}"

    def test_query_contains_required_qualifiers(self):
        from agent_research.nadi import NadiTransport
        nadi = NadiTransport(token="fake")
        q = nadi._build_search_query("kimeisele/hermes-sankhya-25", "<!-- marker -->")
        assert "repo:kimeisele/hermes-sankhya-25" in q
        assert "in:body" in q
        assert "type:issue" in q


# ---------------------------------------------------------------------------
# Approximate match rejection — FakeNadi + local body verification
# ---------------------------------------------------------------------------

class TestApproximateMatchRejection:
    """GitHub search can return approximate results.  The local body
    verification in search_issues must filter those out."""

    def test_spurious_hit_without_exact_marker_is_ignored(self):
        """A search result whose body does NOT contain the exact marker
        must not block a legitimate delivery."""
        # The real marker for inq-001 on hermes-sankhya-25:
        real_marker = _delivery_marker(_delivery_key("hermes-sankhya-25", "inq-001"))
        # A spurious issue that GitHub search returned but does NOT
        # actually contain the real marker:
        spurious_body = (
            "## Peer Review Request from agent-research\n\n"
            "**Inquiry ID:** some-other-inquiry\n"
        )
        # The FakeNadi search_issues applies local body verification,
        # so this spurious hit should be filtered out.
        nadi = _FakeNadi(existing_issues=[{"number": 99, "body": spurious_body}])
        requester = PeerReviewRequester(nadi)
        result = _make_result("inq-001")

        results = requester.request_reviews(result, ["hermes-sankhya-25"])

        # The spurious hit does not contain the real marker, so the
        # delivery must proceed.
        assert len(results) == 1, "spurious search hit should not block delivery"
        assert len(nadi.created_issues) == 1
        assert real_marker in nadi.created_issues[0]["body"]


# ---------------------------------------------------------------------------
# Workflow concurrency contract
# ---------------------------------------------------------------------------

class TestHeartbeatWorkflowContract:
    """Verify the research-heartbeat workflow defines a stable concurrency
    group that prevents concurrent executions."""

    def test_heartbeat_defines_concurrency_group(self):
        import json, subprocess
        from pathlib import Path

        # Resolve the actual repo root (handle /tmp symlinks on macOS)
        repo_root = Path(subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path(__file__).resolve().parents[1], text=True,
        ).strip())
        wf_path = repo_root / ".github" / "workflows" / "research-heartbeat.yml"

        # Use json + python parsing to avoid yaml dep — the file is
        # simple enough for line-based inspection.
        lines = wf_path.read_text().splitlines()
        # Find concurrency group line
        group_line = None
        cancel_line = None
        in_concurrency = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "concurrency:":
                in_concurrency = True
            elif in_concurrency and stripped.startswith("group:"):
                group_line = stripped
            elif in_concurrency and stripped.startswith("cancel-in-progress:"):
                cancel_line = stripped
            elif in_concurrency and not stripped.startswith(" ") and stripped:
                break  # end of concurrency block

        assert group_line is not None, "workflow must define concurrency group"
        assert "agent-research-heartbeat" in group_line, (
            f"expected stable concurrency group, got: {group_line}"
        )
        assert cancel_line is not None, "cancel-in-progress must be defined"
        assert "false" in cancel_line, (
            f"cancel-in-progress must be false, got: {cancel_line}"
        )
