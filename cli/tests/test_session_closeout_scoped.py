"""Multi-repository publication and native binding use real Git fixtures."""

import hashlib
import json
import subprocess

import pytest
from limen import session_closeout as closeout
from limen.session_closeout import path_digest

SID = "multi-session"
OWNER = "https://github.com/example/project/issues/1"


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).rstrip("\n")


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
    roots = {}
    declarations = []
    for identifier in ("owner", "subject"):
        root, remote = tmp_path / identifier, tmp_path / f"{identifier}.git"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "work", str(root)], check=True, capture_output=True)
        git(root, "config", "user.name", "Fixture")
        git(root, "config", "user.email", "fixture@example.test")
        git(root, "config", "commit.gpgsign", "false")
        git(root, "remote", "add", "origin", str(remote))
        (root / "implementation.py").write_text("value = 1\n")
        git(root, "add", ".")
        git(root, "commit", "-m", "implementation")
        head = git(root, "rev-parse", "HEAD")
        git(root, "push", "origin", "work")
        roots[identifier] = root
        declarations.append(
            {
                "id": identifier,
                "kind": "git",
                "path_sha256": path_digest(root),
                "repository": str(remote).removesuffix(".git"),
                "base_head": head,
                "subject_head": head,
                "publication_branch": "work",
                "owned_paths": ["implementation.py"],
                "retained_work": [],
            }
        )
    retained = tmp_path / "private"
    retained.mkdir()
    roots["private"] = retained
    declarations.append({"id": "private", "kind": "retained", "path_sha256": path_digest(retained), "owner_url": OWNER})
    evidence = roots["owner"] / "evidence.json"
    evidence.write_text('{"verified":true}\n')
    packet = {"evidence": evidence.name, "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
    receipt = {
        "schema": closeout.SCHEMA_V2,
        "session_id": SID,
        "session_root_path_sha256": path_digest(tmp_path),
        "receipt_root_id": "owner",
        "owner_url": OWNER,
        "disposition": "handoff",
        "scope_roots": declarations,
        "verification": [
            {"root_id": row["id"], "head": row["base_head"], "exit_code": 0, **packet} for row in declarations[:2]
        ],
        "custody": {"verified": True, "root_ids": list(roots), **packet},
    }
    path = roots["owner"] / "session-closeout.json"
    transcript = tmp_path / "native.jsonl"
    transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": SID, "cwd": str(tmp_path)}}))
    audit = {
        "session_id": SID,
        "session_present": False,
        "active_lease_count": 0,
        "retained_run_count": 0,
        "runs": [],
        "coverage": {"retained_state_complete": True},
    }

    def publish():
        path.write_text(json.dumps(receipt))
        git(roots["owner"], "add", ".")
        git(roots["owner"], "commit", "--allow-empty", "-m", "receipt")
        git(roots["owner"], "push", "origin", "work")

    def evaluate(**changes):
        return closeout.evaluate_scoped(
            tmp_path,
            SID,
            path,
            changes.pop("scope_roots", roots),
            audit=changes.pop("audit", audit),
            binding=changes.pop("binding", None),
            native_transcript=changes.pop("native_transcript", transcript),
            read_owner=lambda url: {"state": "open"},
            observe_processes=changes.pop(
                "observe_processes", lambda *args, **kwargs: {"complete": True, "process_count": 0}
            ),
            **changes,
        )

    publish()
    return roots, receipt, transcript, publish, evaluate


def test_non_git_native_root_releases_explicit_scopes_idempotently(cohort):
    roots, _, _, _, evaluate = cohort
    before = {key: git(root, "status", "--porcelain") for key, root in roots.items() if key != "private"}
    result = evaluate()
    assert result["session_released"] and not result["task_completed"]
    assert evaluate() == result
    assert {key: git(root, "status", "--porcelain") for key, root in roots.items() if key != "private"} == before


@pytest.mark.parametrize(
    "failure", [None, "foreign_identity", "wrong_scope", "no_native_witness", "absent_registration"]
)
def test_explicit_current_broker_scope_preserves_native_anchor(cohort, failure):
    roots, receipt, _, publish, evaluate = cohort
    receipt["broker_scope_root_id"] = "subject"
    publish()
    audit = {
        "session_id": SID,
        "session_present": True,
        "active_lease_count": 0,
        "retained_run_count": 0,
        "runs": [],
        "coverage": {"retained_state_complete": True},
    }
    binding = {"session_id": SID, "worktree": str(roots["subject"])}
    changes = {"audit": audit, "binding": binding}
    if failure == "foreign_identity":
        binding["session_id"] = "another-session"
    elif failure == "wrong_scope":
        binding["worktree"] = str(roots["owner"])
    elif failure == "no_native_witness":
        changes["native_transcript"] = None
    elif failure == "absent_registration":
        audit["session_present"] = False
    if failure:
        with pytest.raises(closeout.Unmeasured):
            evaluate(**changes)
    else:
        result = evaluate(**changes)
        assert result["session_released"]
        assert evaluate(**changes) == result


@pytest.mark.parametrize(
    "failure", ["missing", "extra", "alias", "wrong_cwd", "child_binding", "stale_head", "custody"]
)
def test_incomplete_or_conflicting_scope_never_releases(cohort, failure):
    roots, receipt, transcript, publish, evaluate = cohort
    mapping = dict(roots)
    changes = {}
    if failure == "missing":
        del mapping["subject"]
    elif failure == "extra":
        mapping["extra"] = roots["owner"].parent
    elif failure == "alias":
        mapping["private"] = roots["owner"]
    elif failure == "wrong_cwd":
        transcript.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": SID, "cwd": str(roots["subject"])}})
        )
    elif failure == "child_binding":
        changes["binding"] = {"session_id": SID, "worktree": str(roots["subject"])}
    elif failure == "stale_head":
        receipt["scope_roots"][1]["subject_head"] = "0" * 40
        publish()
    else:
        receipt["custody"]["root_ids"] = ["owner"]
        publish()
    with pytest.raises(closeout.Unmeasured):
        evaluate(scope_roots=mapping, **changes)


@pytest.mark.parametrize("failure", ["dirty", "unattributed", "unpublished", "changed", "process", "release_check"])
def test_failure_in_any_subject_blocks_whole_session(cohort, failure):
    roots, receipt, _, publish, evaluate = cohort
    subject = roots["subject"]
    changes = {}
    if failure == "dirty":
        (subject / "implementation.py").write_text("dirty\n")
    elif failure == "unattributed":
        (subject / "unknown").write_text("dirty\n")
    elif failure == "unpublished":
        git(subject, "commit", "--allow-empty", "-m", "unpublished")
        receipt["scope_roots"][1]["subject_head"] = git(subject, "rev-parse", "HEAD")
        publish()
    elif failure == "changed":
        (subject / "implementation.py").write_text("value = 2\n")
        git(subject, "add", ".")
        git(subject, "commit", "-m", "changed")
        git(subject, "push", "origin", "work")
        receipt["scope_roots"][1]["subject_head"] = git(subject, "rev-parse", "HEAD")
        publish()
    elif failure == "process":
        changes["observe_processes"] = lambda *args, **kwargs: {"complete": True, "process_count": 1}
    else:
        receipt["verification"][1].update(exit_code=1, purpose="release", owner_url=OWNER)
        publish()
    assert not evaluate(**changes)["session_released"]


def test_completion_failure_keeps_open_handoff(cohort):
    _, receipt, _, publish, evaluate = cohort
    receipt["verification"][1].update(exit_code=1, purpose="completion", owner_url=OWNER)
    publish()
    assert evaluate()["session_released"]
    receipt["disposition"] = "complete"
    publish()
    assert not evaluate()["session_released"]


@pytest.mark.parametrize("contract", ["limen.custody_receipt.v2", "unknown-contract"])
def test_portable_contract_requires_real_committed_supporting_evidence(cohort, contract):
    _, receipt, _, publish, evaluate = cohort
    receipt["custody"]["contract"] = contract
    publish()
    with pytest.raises(closeout.Unmeasured):
        evaluate()


@pytest.mark.parametrize("same_id", [True, False])
@pytest.mark.parametrize("prefix", ["https://github.com/", "git@github.com:", "ssh://git@github.com/"])
def test_repository_transfer_uses_stable_identity(cohort, monkeypatch, same_id, prefix):
    roots, receipt, _, publish, evaluate = cohort
    original = closeout.git
    original_run = closeout.run

    def publication_api(command, **kwargs):
        if command[:4] == ["gh", "api", "--method", "GET"]:
            root = roots[command[4].split("/")[2]]
            tip, ref = original(root, "ls-remote", "--exit-code", "origin", "refs/heads/work").split()
            return json.dumps({"ref": ref, "object": {"type": "commit", "sha": tip}})
        return original_run(command, **kwargs)

    def remote_alias(root, *args, **kwargs):
        if args == ("remote", "get-url", "origin"):
            return prefix + "old-owner/" + root.name + ".git"
        return original(root, *args, **kwargs)

    for index, row in enumerate(receipt["scope_roots"][:2]):
        row.update(repository=f"new-owner/{row['id']}", repository_id=index + 1)
    publish()
    monkeypatch.setattr(closeout, "git", remote_alias)
    monkeypatch.setattr(closeout, "run", publication_api)

    def read_repository(slug):
        identifier = slug.split("/")[1]
        return {"id": (1 if identifier == "owner" else 2) if same_id else 999, "full_name": f"new-owner/{identifier}"}

    if same_id:
        assert evaluate(read_repository=read_repository)["session_released"]
    else:
        with pytest.raises(closeout.Unmeasured, match="repository identity"):
            evaluate(read_repository=read_repository)


def test_dirty_or_tampered_evidence_is_unmeasured(cohort):
    roots, _, _, _, evaluate = cohort
    (roots["owner"] / "evidence.json").write_text("tampered")
    with pytest.raises(closeout.Unmeasured, match="local changes"):
        evaluate()


@pytest.mark.parametrize("declared", [True, False])
def test_nested_scope_requires_parent_coverage(cohort, declared):
    roots, receipt, _, publish, evaluate = cohort
    nested = roots["owner"] / "private-retained"
    nested.mkdir()
    roots["private"] = nested
    receipt["scope_roots"][2]["path_sha256"] = path_digest(nested)
    if declared:
        receipt["scope_roots"][2]["nested_in"] = "owner"
        receipt["scope_roots"][0]["retained_work"] = [{"paths": ["private-retained"], "owner_url": OWNER}]
    publish()
    if declared:
        assert evaluate()["session_released"]
    else:
        with pytest.raises(closeout.Unmeasured, match="parent ownership"):
            evaluate()


@pytest.mark.parametrize("nested", [True, False])
def test_malformed_retained_work_is_unmeasured(cohort, nested):
    roots, receipt, _, publish, evaluate = cohort
    receipt["scope_roots"][0]["retained_work"] = ["invalid"]
    if nested:
        child = roots["owner"] / "private-retained"
        child.mkdir()
        roots["private"] = child
        receipt["scope_roots"][2].update(path_sha256=path_digest(child), nested_in="owner")
    publish()
    with pytest.raises(closeout.Unmeasured, match="retained work"):
        evaluate()


def test_relative_native_cwd_is_unmeasured(cohort):
    _, _, transcript, _, evaluate = cohort
    transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": SID, "cwd": "."}}))
    with pytest.raises(closeout.Unmeasured, match="native transcript"):
        evaluate()


def test_scoped_cli_errors_preserve_v2_schema(monkeypatch, capsys, tmp_path):
    from limen.conduct import client

    monkeypatch.setattr(client, "client_from_env", lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))
    assert (
        closeout.main(
            [
                "--session-id",
                SID,
                "--worktree",
                str(tmp_path),
                "--receipt",
                "receipt.json",
                "--scope-root",
                f"owner={tmp_path}",
                "--json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["schema"] == closeout.SCHEMA_V2
