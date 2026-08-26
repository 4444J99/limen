from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    RecoveryStableObservationV1,
    ReviewLineageClosureV2,
    ReviewThreadClosureV2,
    SourceCoverageV1,
    UniverseRecoveryManifestV1,
    bound_reap_expiry,
    cas_delete_command,
    evaluate_recovery,
    issue_reap_capability,
    verify_reap_capability,
)
from limen.repository_identity import RepositoryIdentityV1


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
DIGEST = "a" * 64
TIP = "b" * 40
BASE = "c" * 40
SIGNING_MATERIAL = b"k" * 32
IDENTITY = RepositoryIdentityV1(
    repository_id=1255213941,
    canonical_coordinate="4444J99/limen",
    historical_aliases=("organvm/limen",),
)


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
        repository_identity=IDENTITY,
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
        repository_id=1255213941,
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
        "key": IDENTITY.stable_key(f"refs/heads/topic@{TIP}"),
        "repository_identity": IDENTITY,
        "repository": "organvm/limen",
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


def test_valid_fixed_point_is_stable_when_review_observation_time_changes():
    first = evaluate_recovery(manifest())
    refreshed_review = review().model_copy(update={"observed_at": NOW + timedelta(minutes=1)})
    second = evaluate_recovery(manifest(review_closures=(refreshed_review,)))

    assert first.ok is True
    assert second.ok is True
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


def test_landed_pull_request_requires_terminal_closure_for_exact_head():
    item_key = IDENTITY.stable_key(f"pull-request:1@{TIP}")
    landed_pull = RecoveryDispositionReceiptV1(
        item_key=item_key,
        item_kind="pull_request",
        source_digest=DIGEST,
        owner="organvm/limen:pull-request:1",
        predicate="exact head landed and review lineage is terminal",
        receipt="git:organvm/limen:docs/receipts/pull-1.json",
        terminal_class="exact_landed",
    )

    missing = evaluate_recovery(manifest(baseline_keys=(item_key,), dispositions=(landed_pull,), review_closures=()))
    wrong_head = review().model_copy(update={"head_sha": "d" * 40})
    mismatched = evaluate_recovery(
        manifest(baseline_keys=(item_key,), dispositions=(landed_pull,), review_closures=(wrong_head,))
    )
    matched = evaluate_recovery(
        manifest(baseline_keys=(item_key,), dispositions=(landed_pull,), review_closures=(review(),))
    )

    assert "missing-terminal-review-lineages:1" in missing.errors
    assert "missing-terminal-review-lineages:1" in mismatched.errors
    assert matched.ok is True


def test_pull_request_recovery_keys_reject_coordinate_only_legacy_identity():
    with pytest.raises(ValueError, match="github-repository:<id>"):
        RecoveryDispositionReceiptV1(
            item_key=f"organvm/limen:pull-request:1@{TIP}",
            item_kind="pull_request",
            source_digest=DIGEST,
            owner="organvm/limen:pull-request:1",
            predicate="exact head landed and review lineage is terminal",
            receipt="git:organvm/limen:docs/receipts/pull-1.json",
            terminal_class="exact_landed",
        )


def test_landed_pull_request_requires_the_same_numeric_repository_identity():
    item_key = IDENTITY.stable_key(f"pull-request:1@{TIP}")
    landed_pull = RecoveryDispositionReceiptV1(
        item_key=item_key,
        item_kind="pull_request",
        source_digest=DIGEST,
        owner="github-repository:1255213941/pull-request:1",
        predicate="exact head landed and review lineage is terminal",
        receipt="git:organvm/limen:docs/receipts/pull-1.json",
        terminal_class="exact_landed",
    )
    wrong_identity = RepositoryIdentityV1(
        repository_id=999_999_999,
        canonical_coordinate=IDENTITY.canonical_coordinate,
        historical_aliases=IDENTITY.historical_aliases,
    )
    wrong_repository_review = ReviewLineageClosureV2.model_validate(
        review().model_dump(mode="json") | {"repository_identity": wrong_identity.model_dump(mode="json")}
    )

    result = evaluate_recovery(
        manifest(
            baseline_keys=(item_key,),
            dispositions=(landed_pull,),
            review_closures=(wrong_repository_review,),
        )
    )

    assert "missing-terminal-review-lineages:1" in result.errors


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
    material = SIGNING_MATERIAL
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


def test_reap_capability_key_requires_32_encoded_bytes_for_issue_and_verify():
    reap_plan = plan()
    with pytest.raises(ValueError, match="at least 32 encoded bytes"):
        issue_reap_capability(
            reap_plan,
            capability_id="remote-reap-capability-short-key",
            issued_by="tabularius-keeper",
            signing_material=b"k" * 31,
            issued_at=NOW,
        )

    capability = issue_reap_capability(
        reap_plan,
        capability_id="remote-reap-capability-32-byte-key",
        issued_by="tabularius-keeper",
        signing_material=b"k" * 32,
        issued_at=NOW,
    )
    with pytest.raises(ValueError, match="at least 32 encoded bytes"):
        verify_reap_capability(
            capability,
            plan=reap_plan,
            signing_material=b"k" * 31,
            observed_at=NOW,
        )
    verify_reap_capability(
        capability,
        plan=reap_plan,
        signing_material=b"k" * 32,
        observed_at=NOW,
    )


def test_reap_expiry_is_clamped_to_the_underlying_disposition():
    assert bound_reap_expiry(NOW + timedelta(hours=1), NOW + timedelta(minutes=5)) == NOW + timedelta(minutes=5)
    assert bound_reap_expiry(NOW + timedelta(minutes=5), NOW + timedelta(hours=1)) == NOW + timedelta(minutes=5)


def test_ref_disposition_is_repository_qualified_and_proof_bound():
    row = disposition()

    assert row.reap_eligible is True
    with pytest.raises(ValueError, match="canonical or a historical alias"):
        disposition(repository="organvm/other")
    with pytest.raises(ValueError, match="tree or patch digest"):
        disposition(delivery_disposition="equivalent_landed")
    with pytest.raises(ValueError, match="named review lineage"):
        disposition(pull_requests=())
    assert disposition(lane_protection=("active-human",)).reap_eligible is False
    assert disposition(delivery_disposition="equivalent_landed", tree_digest="1" * 64).reap_eligible is False
    with pytest.raises(ValueError, match="default ref"):
        disposition(ref="refs/heads/main", key=IDENTITY.stable_key(f"refs/heads/main@{TIP}"))


def test_manifest_rejects_a_vacuous_recovery_denominator():
    with pytest.raises(ValueError, match="at least 1 item"):
        UniverseRecoveryManifestV1(
            generated_at=NOW,
            launch_digest=DIGEST,
            census_digest="d" * 64,
            cursor_receipts=(),
            sources=(),
            baseline_keys=(),
            dispositions=(),
        )


def test_read_only_predicate_requires_a_prior_matching_stable_observation(tmp_path: Path):
    current = manifest(generated_at=NOW + timedelta(minutes=1))
    result = evaluate_recovery(current)
    manifest_path = tmp_path / "manifest.json"
    prior_path = tmp_path / "prior.json"
    manifest_path.write_text(json.dumps(current.model_dump(mode="json")), encoding="utf-8")
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "scripts" / "universe-recovery.py"),
        "--check",
        "--manifest",
        str(manifest_path),
        "--prior-observation",
        str(prior_path),
    ]

    assert subprocess.run(command, check=False, capture_output=True).returncode == 1
    prior = RecoveryStableObservationV1(
        stable_digest=result.stable_digest,
        observed_at=NOW,
        manifest_receipt="git:organvm/limen:first-observation.json",
    )
    prior_path.write_text(prior.model_dump_json(), encoding="utf-8")
    assert subprocess.run(command, check=False, capture_output=True).returncode == 0


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
        signing_material=SIGNING_MATERIAL,
        issued_at=NOW,
    )
    forged = ReapCapabilityV1.model_validate(capability.model_dump(mode="json") | {"signature": "0" * 64})

    with pytest.raises(ValueError, match="signature"):
        verify_reap_capability(
            forged,
            plan=reap_plan,
            signing_material=SIGNING_MATERIAL,
            observed_at=NOW,
        )
    with pytest.raises(ValueError, match="signature"):
        verify_reap_capability(
            capability,
            plan=reap_plan,
            signing_material=b"different-fixture-material-32bytes",
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
