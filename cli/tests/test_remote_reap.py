from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.remote_reap import (
    apply_capability,
    atomic_json,
    github_repository_slug,
    journal,
    load_model,
    reconcile_effect,
    remote_tip,
    remote_url_digest,
    validate_disposition_evidence,
)
from limen.repository_identity import RepositoryIdentityV1
from limen.universe_recovery import (
    CursorReceiptV1,
    CustodyProofV1,
    RefDispositionV2,
    ReapJournalV1,
    ReapPlanV1,
    ReviewLineageClosureV2,
    canonical_digest,
    issue_reap_capability,
)


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)
EXAMPLE_IDENTITY = RepositoryIdentityV1(
    repository_id=123456789,
    canonical_coordinate="4444J99/example",
    historical_aliases=("organvm/example",),
)


@pytest.mark.parametrize(
    ("origin", "slug"),
    [
        ("git@github.com:organvm/limen.git", "organvm/limen"),
        ("https://github.com/organvm/limen.git", "organvm/limen"),
        ("ssh://git@github.com/organvm/limen.git", "organvm/limen"),
    ],
)
def test_github_repository_identity_is_derived_from_origin(origin: str, slug: str):
    def observe(_command, **_kwargs):
        return subprocess.CompletedProcess([], 0, origin + "\n", "")

    assert github_repository_slug(Path("/unused"), runner=observe) == slug


def test_non_github_repository_identity_is_denied():
    def observe(_command, **_kwargs):
        return subprocess.CompletedProcess([], 0, "file:///tmp/origin.git\n", "")

    with pytest.raises(RuntimeError, match="canonical GitHub"):
        github_repository_slug(Path("/unused"), runner=observe)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def repository(tmp_path: Path) -> tuple[Path, str]:
    origin = tmp_path / "origin.git"
    checkout = tmp_path / "checkout"
    git(tmp_path, "init", "--bare", str(origin))
    git(tmp_path, "clone", str(origin), str(checkout))
    git(checkout, "config", "user.name", "Universe Recovery Test")
    git(checkout, "config", "user.email", "universe-recovery@example.invalid")
    (checkout / "README.md").write_text("base\n", encoding="utf-8")
    git(checkout, "add", "README.md")
    git(checkout, "commit", "-m", "base")
    git(checkout, "branch", "-M", "main")
    git(checkout, "push", "-u", "origin", "main")
    git(checkout, "switch", "-c", "topic")
    (checkout / "topic.txt").write_text("topic\n", encoding="utf-8")
    git(checkout, "add", "topic.txt")
    git(checkout, "commit", "-m", "topic")
    git(checkout, "push", "-u", "origin", "topic")
    return checkout, git(checkout, "rev-parse", "HEAD")


def admitted(checkout: Path, tip: str):
    plan = ReapPlanV1(
        plan_id="remote-reap-plan-0001",
        repository="organvm/example",
        repository_id=EXAMPLE_IDENTITY.repository_id,
        remote_url_digest=remote_url_digest(checkout),
        ref="refs/heads/topic",
        live_tip=tip,
        disposition_digest="a" * 64,
        custody_receipt_digest="b" * 64,
        review_closure_digest="c" * 64,
        grace_satisfied_at=NOW - timedelta(days=1),
        planned_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    capability = issue_reap_capability(
        plan,
        capability_id="remote-reap-capability-0001",
        issued_by="tabularius-keeper",
        signing_material=b"fixture-material",
        issued_at=NOW,
    )
    return plan, capability


def test_exact_unchanged_tip_deletes_and_verifies_absence(tmp_path: Path):
    checkout, tip = repository(tmp_path)
    plan, capability = admitted(checkout, tip)
    journal_path = tmp_path / "journal.json"
    verified = journal(
        capability=capability,
        state="verified",
        detail="verified fixture",
        observed_at=NOW,
    )
    atomic_json(journal_path, verified.model_dump(mode="json"))

    completed = apply_capability(
        repository_root=checkout,
        plan=plan,
        capability=capability,
        journal_path=journal_path,
        redemption_path=tmp_path / "redemptions.json",
        signing_material=b"fixture-material",
        observed_at=NOW + timedelta(minutes=1),
    )

    assert completed.state == "completed"
    assert remote_tip(checkout, "refs/heads/topic") is None


def test_advanced_tip_is_preserved_before_delete(tmp_path: Path):
    checkout, tip = repository(tmp_path)
    plan, capability = admitted(checkout, tip)
    journal_path = tmp_path / "journal.json"
    verified = journal(
        capability=capability,
        state="verified",
        detail="verified fixture",
        observed_at=NOW,
    )
    atomic_json(journal_path, verified.model_dump(mode="json"))
    (checkout / "topic.txt").write_text("advanced\n", encoding="utf-8")
    git(checkout, "add", "topic.txt")
    git(checkout, "commit", "-m", "advance")
    git(checkout, "push", "origin", "topic")
    advanced = git(checkout, "rev-parse", "HEAD")

    with pytest.raises(RuntimeError, match="live ref tip"):
        apply_capability(
            repository_root=checkout,
            plan=plan,
            capability=capability,
            journal_path=journal_path,
            redemption_path=tmp_path / "redemptions.json",
            signing_material=b"fixture-material",
            observed_at=NOW + timedelta(minutes=1),
        )

    assert remote_tip(checkout, "refs/heads/topic") == advanced


def test_completed_capability_is_idempotent_only_while_ref_remains_absent(tmp_path: Path):
    checkout, tip = repository(tmp_path)
    plan, capability = admitted(checkout, tip)
    journal_path = tmp_path / "journal.json"
    atomic_json(
        journal_path,
        journal(capability=capability, state="verified", detail="verified", observed_at=NOW).model_dump(mode="json"),
    )
    first = apply_capability(
        repository_root=checkout,
        plan=plan,
        capability=capability,
        journal_path=journal_path,
        redemption_path=tmp_path / "redemptions.json",
        signing_material=b"fixture-material",
        observed_at=NOW + timedelta(minutes=1),
    )
    second = apply_capability(
        repository_root=checkout,
        plan=plan,
        capability=capability,
        journal_path=journal_path,
        redemption_path=tmp_path / "redemptions.json",
        signing_material=b"fixture-material",
        observed_at=NOW + timedelta(minutes=2),
    )

    assert first.state == second.state == "completed"


def test_capability_cannot_be_replayed_from_a_copied_verified_journal(tmp_path: Path):
    checkout, tip = repository(tmp_path)
    plan, capability = admitted(checkout, tip)
    journal_path = tmp_path / "journal.json"
    copied_journal_path = tmp_path / "copied-journal.json"
    redemption_path = tmp_path / "redemptions.json"
    verified = journal(capability=capability, state="verified", detail="verified", observed_at=NOW)
    atomic_json(journal_path, verified.model_dump(mode="json"))
    atomic_json(copied_journal_path, verified.model_dump(mode="json"))
    apply_capability(
        repository_root=checkout,
        plan=plan,
        capability=capability,
        journal_path=journal_path,
        redemption_path=redemption_path,
        signing_material=b"fixture-material",
        observed_at=NOW + timedelta(minutes=1),
    )
    git(checkout, "push", "origin", f"{tip}:refs/heads/topic")

    with pytest.raises(RuntimeError, match="already been redeemed"):
        apply_capability(
            repository_root=checkout,
            plan=plan,
            capability=capability,
            journal_path=copied_journal_path,
            redemption_path=redemption_path,
            signing_material=b"fixture-material",
            observed_at=NOW + timedelta(minutes=2),
        )

    assert remote_tip(checkout, "refs/heads/topic") == tip


def test_wrong_repository_origin_is_denied(tmp_path: Path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first, tip = repository(first_root)
    second, second_tip = repository(second_root)
    plan, capability = admitted(first, tip)
    journal_path = tmp_path / "journal.json"
    atomic_json(
        journal_path,
        journal(capability=capability, state="verified", detail="verified", observed_at=NOW).model_dump(mode="json"),
    )

    with pytest.raises(RuntimeError, match="origin"):
        apply_capability(
            repository_root=second,
            plan=plan,
            capability=capability,
            journal_path=journal_path,
            redemption_path=tmp_path / "redemptions.json",
            signing_material=b"fixture-material",
            observed_at=NOW + timedelta(minutes=1),
        )

    assert remote_tip(second, "refs/heads/topic") == second_tip


def test_completed_journal_cannot_be_applied_to_an_absent_ref_in_another_repository(tmp_path: Path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first, tip = repository(first_root)
    second, _second_tip = repository(second_root)
    plan, capability = admitted(first, tip)
    journal_path = tmp_path / "journal.json"
    redemption_path = tmp_path / "redemptions.json"
    atomic_json(
        journal_path,
        journal(capability=capability, state="verified", detail="verified", observed_at=NOW).model_dump(mode="json"),
    )
    apply_capability(
        repository_root=first,
        plan=plan,
        capability=capability,
        journal_path=journal_path,
        redemption_path=redemption_path,
        signing_material=b"fixture-material",
        observed_at=NOW + timedelta(minutes=1),
    )
    git(second, "push", "origin", ":refs/heads/topic")

    with pytest.raises(RuntimeError, match="origin"):
        apply_capability(
            repository_root=second,
            plan=plan,
            capability=capability,
            journal_path=journal_path,
            redemption_path=redemption_path,
            signing_material=b"fixture-material",
            observed_at=NOW + timedelta(minutes=2),
        )


def test_failed_effect_is_journaled_and_reconciled_without_retry(tmp_path: Path):
    checkout, tip = repository(tmp_path)
    plan, capability = admitted(checkout, tip)
    journal_path = tmp_path / "journal.json"
    atomic_json(
        journal_path,
        journal(capability=capability, state="verified", detail="verified", observed_at=NOW).model_dump(mode="json"),
    )

    def reject_push(command, **kwargs):
        if "push" in command:
            return subprocess.CompletedProcess(command, 1, "", "rejected")
        return subprocess.run(command, **kwargs)

    with pytest.raises(RuntimeError, match="CAS deletion was rejected"):
        apply_capability(
            repository_root=checkout,
            plan=plan,
            capability=capability,
            journal_path=journal_path,
            redemption_path=tmp_path / "redemptions.json",
            signing_material=b"fixture-material",
            observed_at=NOW + timedelta(minutes=1),
            runner=reject_push,
        )

    crashed = load_model(journal_path, ReapJournalV1)
    assert crashed.state == "crashed"
    forged = capability.model_copy(update={"remote_url_digest": "f" * 64})
    with pytest.raises(RuntimeError, match="authenticated redemption binding"):
        reconcile_effect(
            repository_root=checkout,
            current=crashed,
            capability=forged,
            redemption_path=tmp_path / "redemptions.json",
        )
    reconciled = reconcile_effect(
        repository_root=checkout,
        current=crashed,
        capability=capability,
        redemption_path=tmp_path / "redemptions.json",
    )
    assert reconciled.state == "crashed"
    assert "same capability requires owner review" in reconciled.detail
    assert remote_tip(checkout, "refs/heads/topic") == tip


def test_verifier_recomputes_live_landing_and_custody_evidence():
    default_tip = "c" * 40
    tip = "b" * 40
    repository_name = "organvm/example"
    generation = canonical_digest(
        {
            "repository_id": EXAMPLE_IDENTITY.repository_id,
            "default_ref": "main",
            "default_sha": default_tip,
            "archived": False,
        }
    )
    commit_digest = canonical_digest(
        {
            "repository_id": EXAMPLE_IDENTITY.repository_id,
            "ref": "refs/heads/topic",
            "tip": tip,
        }
    )
    custody = CustodyProofV1(
        repository=repository_name,
        ref="refs/heads/topic",
        tip=tip,
        disposition="not_required_landed",
        source_digest=commit_digest,
        restore_tested=False,
        verified_at=NOW,
        predicate="live exact-landing proof",
    )
    disposition = RefDispositionV2(
        key=EXAMPLE_IDENTITY.stable_key(f"refs/heads/topic@{tip}"),
        repository_identity=EXAMPLE_IDENTITY,
        repository=repository_name,
        ref="refs/heads/topic",
        tip=tip,
        default_ref="refs/heads/main",
        default_tip=default_tip,
        default_generation=generation,
        commit_digest=commit_digest,
        custody_proof_digest=canonical_digest(custody),
        pull_requests=(7,),
        custody_disposition="not_required_landed",
        delivery_disposition="exact_landed",
        owner=repository_name,
        predicate="git merge-base --is-ancestor",
        receipt="git:organvm/example:receipt.json",
        census_digest="d" * 64,
        grace_satisfied_at=NOW,
    )
    review = ReviewLineageClosureV2(
        repository_identity=EXAMPLE_IDENTITY,
        repository=repository_name,
        pull_request=7,
        observed_at=NOW,
        head_sha=tip,
        base_ref="main",
        base_sha="a" * 40,
        merge_sha=default_tip,
        checks_digest="e" * 64,
        cursor_receipts=(
            CursorReceiptV1(surface="reviewThreads", total_count=0, observed_count=0, page_count=1, complete=True),
        ),
        threads=(),
        unresolved_current=0,
        unresolved_outdated=0,
        lifecycle_stage="main_verified",
        terminal=True,
    )

    def live(command, **_kwargs):
        if command[:5] == ["git", "-C", "/unused", "remote", "get-url"]:
            return subprocess.CompletedProcess(command, 0, "git@github.com:organvm/example.git\n", "")
        if command[:3] == ["git", "-C", "/unused"] and "ls-remote" in command:
            ref = command[-1]
            live_tip = default_tip if ref == "refs/heads/main" else tip
            return subprocess.CompletedProcess(command, 0, f"{live_tip}\t{ref}\n", "")
        if command[:3] == ["gh", "api", f"repos/{repository_name}"]:
            return subprocess.CompletedProcess(
                command,
                0,
                '{"id":123456789,"full_name":"4444J99/example","default_branch":"main","archived":false}',
                "",
            )
        if command[:3] == ["gh", "api", f"repos/{repository_name}/compare/{tip}...{default_tip}"]:
            return subprocess.CompletedProcess(command, 0, '{"merge_base_commit":{"sha":"' + tip + '"}}', "")
        if command[:3] == ["gh", "api", f"repos/{repository_name}/pulls/7"]:
            return subprocess.CompletedProcess(command, 0, '{"merged":true,"head":{"sha":"' + tip + '"}}', "")
        raise AssertionError(command)

    validate_disposition_evidence(
        repository_root=Path("/unused"),
        disposition=disposition,
        review=review,
        custody=custody,
        runner=live,
    )
    stale = disposition.model_copy(update={"default_tip": "f" * 40})
    with pytest.raises(ValueError, match="default generation"):
        validate_disposition_evidence(
            repository_root=Path("/unused"),
            disposition=stale,
            review=review,
            custody=custody,
            runner=live,
        )
