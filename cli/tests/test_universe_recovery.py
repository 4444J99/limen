from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.universe_recovery import (
    CustodyCopyV1,
    CustodyProofV1,
    CursorReceiptV1,
    RefDispositionV2,
    ReapCapabilityV1,
    ReapJournalState,
    ReapJournalV1,
    ReapPlanV1,
    RecoveryDispositionReceiptV1,
    ReviewLineageClosureV2,
    ReviewThreadClosureV2,
    SourceCoverageV1,
    UniverseRecoveryManifestV1,
    cas_delete_command,
    evaluate_recovery,
    issue_reap_capability,
    verify_reap_capability,
)


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
DIGEST = "a" * 64
TIP = "b" * 40
BASE = "c" * 40


def cursor(surface: str = "repositories") -> CursorReceiptV1:
    return CursorReceiptV1(surface=surface, total_count=1, observed_count=1, page_count=1, complete=True)


def review(*, terminal: bool = True, outdated: bool = False) -> ReviewLineageClosureV2:
    threads = ()
    current = outdated_count = 0
    if not terminal:
        threads = (
            ReviewThreadClosureV2(
                thread_id="PRRT_example_0001",
                resolved=False,
                outdated=outdated,
                disposition="pending",
            ),
        )
        current = 0 if outdated else 1
        outdated_count = 1 if outdated else 0
    return ReviewLineageClosureV2(
        repository="organvm/limen",
        pull_request=1,
        observed_at=NOW,
        head_sha=TIP,
        base_ref="main",
        base_sha=BASE,
        review_decision=None,
        checks_digest=DIGEST,
        cursor_receipts=(cursor("reviewThreads"), cursor("reviewThreads.comments")),
        threads=threads,
        unresolved_current=current,
        unresolved_outdated=outdated_count,
        lifecycle_stage="open",
        terminal=terminal,
    )


def manifest(**updates) -> UniverseRecoveryManifestV1:
    values = {
        "generated_at": NOW,
        "launch_digest": DIGEST,
        "census_digest": "d" * 64,
        "cursor_receipts": (cursor(),),
        "sources": (
            SourceCoverageV1(
                source_instance_id="github-estate-0001",
                source_kind="github_estate",
                enumeration_complete=True,
                owner="organvm/limen",
                predicate="python3 scripts/github-estate-census.py --check",
                receipt="git:organvm/limen:docs/github-estate-census.json",
            ),
        ),
        "baseline_keys": ("organvm/limen/refs/heads/topic@" + TIP,),
        "newcomer_keys": (),
        "dispositions": (
            RecoveryDispositionReceiptV1(
                item_key="organvm/limen/refs/heads/topic@" + TIP,
                item_kind="ref",
                source_digest=DIGEST,
                owner="organvm/limen",
                predicate="git merge-base --is-ancestor",
                receipt="git:organvm/limen:docs/receipts/topic.json",
                terminal_class="exact_landed",
            ),
        ),
        "review_closures": (review(),),
        "reap_journals": (),
    }
    values.update(updates)
    return UniverseRecoveryManifestV1(**values)


def plan() -> ReapPlanV1:
    return ReapPlanV1(
        plan_id="remote-reap-plan-0001",
        repository="organvm/limen",
        repository_id="R_repo_0001",
        remote_url_digest=DIGEST,
        ref="refs/heads/topic",
        live_tip=TIP,
        disposition_digest="d" * 64,
        custody_receipt_digest="e" * 64,
        review_closure_digest="f" * 64,
        grace_satisfied_at=NOW - timedelta(days=1),
        planned_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def disposition(**updates) -> RefDispositionV2:
    values = {
        "key": f"organvm/limen/refs/heads/topic@{TIP}",
        "repository": "organvm/limen",
        "repository_id": "R_repo_0001",
        "ref": "refs/heads/topic",
        "tip": TIP,
        "default_ref": "refs/heads/main",
        "default_tip": BASE,
        "default_generation": DIGEST,
        "commit_digest": "d" * 64,
        "custody_proof_digest": "f" * 64,
        "pull_requests": (1,),
        "custody_disposition": "not_required_landed",
        "delivery_disposition": "exact_landed",
        "owner": "organvm/limen",
        "predicate": "git merge-base --is-ancestor",
        "receipt": "git:organvm/limen:docs/receipts/topic.json",
        "census_digest": "e" * 64,
        "grace_satisfied_at": NOW,
    }
    values.update(updates)
    return RefDispositionV2(**values)


def test_valid_fixed_point_is_stable_when_only_timestamp_changes():
    first = evaluate_recovery(manifest())
    second = evaluate_recovery(manifest(generated_at=NOW + timedelta(minutes=1)))

    assert first.ok is True
    assert first.stable_digest == second.stable_digest


def test_missing_newcomer_and_unknown_disposition_fail_closed():
    missing = evaluate_recovery(manifest(newcomer_keys=("organvm/new#1@" + TIP,)))
    unknown_row = manifest().dispositions[0].model_copy(update={"terminal_class": "unknown"})
    unknown = evaluate_recovery(manifest(dispositions=(unknown_row,)))

    assert "missing-dispositions:1" in missing.errors
    assert "unknown-dispositions:1" in unknown.errors


def test_unresolved_outdated_review_blocks_terminal_state():
    open_review = review(terminal=False, outdated=True)
    result = evaluate_recovery(manifest(review_closures=(open_review,)))

    assert open_review.unresolved_outdated == 1
    assert result.errors == ("nonterminal-review-lineages:1",)


def test_post_merge_new_review_requires_corrective_owner():
    with pytest.raises(ValueError, match="corrective owner"):
        review(terminal=False).model_copy(update={"lifecycle_stage": "merged"}, deep=True).__class__.model_validate(
            review(terminal=False).model_dump(mode="json") | {"lifecycle_stage": "merged"}
        )


def test_unreconciled_crash_blocks_fixed_point():
    journal = ReapJournalV1(
        effect_id="remote-reap-effect-0001",
        capability_id="remote-reap-capability-0001",
        repository="organvm/limen",
        ref="refs/heads/topic",
        expected_tip=TIP,
        state="crashed",
        updated_at=NOW,
        detail="post-delete probe unavailable",
    )

    assert evaluate_recovery(manifest(reap_journals=(journal,))).errors == ("unreconciled-reap-effects:1",)


@pytest.mark.parametrize("state", ["planned", "verified", "applying", "crashed"])
def test_every_noncompleted_reap_journal_blocks_fixed_point(state: ReapJournalState):
    journal = ReapJournalV1(
        effect_id="remote-reap-effect-0001",
        capability_id="remote-reap-capability-0001",
        repository="organvm/limen",
        ref="refs/heads/topic",
        expected_tip=TIP,
        state=state,
        updated_at=NOW,
        detail="not terminal",
    )

    assert evaluate_recovery(manifest(reap_journals=(journal,))).errors == ("unreconciled-reap-effects:1",)


def test_capability_is_plan_bound_expiring_and_exact_tip_cas_only():
    material = b"fixture-material"
    reap_plan = plan()
    capability = issue_reap_capability(
        reap_plan,
        capability_id="remote-reap-capability-0001",
        issued_by="tabularius-keeper",
        signing_material=material,
        issued_at=NOW,
    )

    verify_reap_capability(capability, plan=reap_plan, signing_material=material, observed_at=NOW)
    assert cas_delete_command(capability) == (
        "git",
        "push",
        f"--force-with-lease=refs/heads/topic:{TIP}",
        "origin",
        ":refs/heads/topic",
    )
    with pytest.raises(ValueError, match="expired"):
        verify_reap_capability(
            capability,
            plan=reap_plan,
            signing_material=material,
            observed_at=NOW + timedelta(hours=2),
        )


def test_ref_disposition_is_repository_qualified_and_proof_bound():
    row = disposition()

    assert row.reap_eligible is True
    with pytest.raises(ValueError, match="repository/ref@tip"):
        disposition(repository="organvm/other")
    with pytest.raises(ValueError, match="tree or patch digest"):
        disposition(delivery_disposition="equivalent_landed")
    with pytest.raises(ValueError, match="named review lineage"):
        disposition(pull_requests=())
    assert disposition(lane_protection=("active-human",)).reap_eligible is False
    assert disposition(delivery_disposition="equivalent_landed", tree_digest="1" * 64).reap_eligible is False


def test_paired_custody_requires_two_distinct_verified_devices_and_restore():
    source_digest = "7" * 64
    copies = (
        CustodyCopyV1(device_id_digest="8" * 64, content_digest=source_digest),
        CustodyCopyV1(device_id_digest="9" * 64, content_digest=source_digest),
    )
    proof = CustodyProofV1(
        repository="organvm/limen",
        ref="refs/heads/topic",
        tip=TIP,
        disposition="paired_verified",
        source_digest=source_digest,
        copies=copies,
        restore_tested=True,
        verified_at=NOW,
        predicate="scripts/paired-custody.py --restore-test",
    )

    assert len(proof.copies) == 2
    with pytest.raises(ValueError, match="two devices"):
        CustodyProofV1.model_validate(proof.model_dump(mode="json") | {"copies": copies[:1]})
    with pytest.raises(ValueError, match="restore test"):
        CustodyProofV1.model_validate(proof.model_dump(mode="json") | {"restore_tested": False})


def test_forged_or_wrong_plan_capability_is_rejected():
    reap_plan = plan()
    capability = issue_reap_capability(
        reap_plan,
        capability_id="remote-reap-capability-0001",
        issued_by="tabularius-keeper",
        signing_material=b"fixture-material",
        issued_at=NOW,
    )
    forged = ReapCapabilityV1.model_validate(capability.model_dump(mode="json") | {"signature": "0" * 64})

    with pytest.raises(ValueError, match="signature"):
        verify_reap_capability(
            forged,
            plan=reap_plan,
            signing_material=b"fixture-material",
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="signature"):
        verify_reap_capability(
            capability,
            plan=reap_plan,
            signing_material=b"other-fixture-material",
            observed_at=NOW,
        )


def test_cursor_moved_total_and_incomplete_source_require_visible_debt():
    with pytest.raises(ValueError, match="cursor completeness"):
        CursorReceiptV1(surface="branches", total_count=2, observed_count=1, page_count=1, complete=True)
    with pytest.raises(ValueError, match="durable blocker"):
        SourceCoverageV1(
            source_instance_id="archive-device-0001",
            source_kind="paired_custody",
            enumeration_complete=False,
            owner="organvm/limen",
            predicate="mount and identity-verify custody target",
            receipt="git:organvm/limen:docs/continuations/universe-recovery-20260823/manifest.json",
        )
