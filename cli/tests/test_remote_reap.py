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
)
from limen.universe_recovery import ReapJournalV1, ReapPlanV1, issue_reap_capability


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=UTC)


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
        repository_id="R_example_0001",
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
        signing_material=b"fixture-material",
        observed_at=NOW + timedelta(minutes=1),
    )
    second = apply_capability(
        repository_root=checkout,
        plan=plan,
        capability=capability,
        journal_path=journal_path,
        signing_material=b"fixture-material",
        observed_at=NOW + timedelta(minutes=2),
    )

    assert first.state == second.state == "completed"


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
            signing_material=b"fixture-material",
            observed_at=NOW + timedelta(minutes=1),
        )

    assert remote_tip(second, "refs/heads/topic") == second_tip


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
            signing_material=b"fixture-material",
            observed_at=NOW + timedelta(minutes=1),
            runner=reject_push,
        )

    crashed = load_model(journal_path, ReapJournalV1)
    assert crashed.state == "crashed"
    reconciled = reconcile_effect(repository_root=checkout, current=crashed)
    assert reconciled.state == "crashed"
    assert "same capability requires owner review" in reconciled.detail
    assert remote_tip(checkout, "refs/heads/topic") == tip
