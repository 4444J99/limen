"""Hermetic contract for scripts/session-closeout-receipt.py, judged by the REAL v2 checker.

The producer is only worth having if the receipts it emits are accepted by `limen.session_closeout`
itself, and if every way the checker would be fooled (or would crash) is refused up front. These tests build
real git repositories with GitHub-style origins (the fetch URL is github.com, the push URL is a local bare
repository), fake only `gh` (through `closeout.run`), the conduct broker and the process census, and then drive
plan -> attest -> build -> commit -> push -> check through the producer's own CLI. No network, no broker, no
secrets. One negative control per amendment of the adversarial review is named `test_aNN_*`.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli/src"))
sys.path.insert(0, str(ROOT / "cli/tests"))

from limen import session_closeout as closeout
from portable_custody_fixtures import make_graph

SPEC = importlib.util.spec_from_file_location("session_closeout_receipt", ROOT / "scripts/session-closeout-receipt.py")
producer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = producer  # dataclasses resolve string annotations through sys.modules
SPEC.loader.exec_module(producer)

SID = "producer-session"
OWNER_URL = "https://github.com/example/owner/issues/1"
FOREIGN_URL = "https://github.com/example/other/issues/7"
PULL_URL = "https://github.com/example/subject/pull/5"
CONTINUATION = "docs/continuations/closeout-test"
EVIDENCE_DIR = f"{CONTINUATION}/closeout-evidence/{SID}"
REPOSITORY_IDS = {"owner": 101, "subject": 102, "subject2": 103}

REGISTRY = """\
gates:
  trivial:
    command: "true"
    paths: ["implementation.py"]
    owner: test
    note: always passes
  failing:
    command: "false"
    paths: ["implementation.py"]
    owner: test
    note: always fails
  mutating:
    command: "git commit -m sneaky"
    paths: ["implementation.py"]
    owner: test
    note: must be refused
  abspath:
    command: "bash /tmp/run-it.sh"
    paths: ["implementation.py"]
    owner: test
    note: must be refused
  tokenflag:
    command: "echo --token abc123xyz"
    paths: ["implementation.py"]
    owner: test
    note: must be refused
  slow:
    command: "sleep 30"
    paths: ["implementation.py"]
    owner: test
    note: exceeds the deadline
  envcheck:
    command: 'test -z "$GH_TOKEN" && test -z "$LIMEN_CONDUCT_TOKEN"'
    paths: ["implementation.py"]
    owner: test
    note: proves the environment is scrubbed
  touch:
    command: "touch created-by-gate.txt"
    paths: ["implementation.py"]
    owner: test
    note: dirties the tree
"""


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).rstrip("\n")


def codes(payload):
    return {gap["code"] for gap in payload.get("gaps", [])}


class World:
    """Two real GitHub-style repositories, an optional retained directory and a plain non-git anchor."""

    def __init__(self, tmp_path, monkeypatch, *, retained=True, anchor_is_owner=False, owner_topic=False):
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
        monkeypatch.setenv("GIT_CONFIG_SYSTEM", "/dev/null")
        monkeypatch.delenv("LIMEN_ROOT", raising=False)
        self.monkeypatch = monkeypatch
        self.tmp = tmp_path.resolve()
        self.staging = self.tmp / "staging"
        self.staging.mkdir(mode=0o700)
        self.registry = self.staging / "gates.yaml"
        self.registry.write_text(REGISTRY)
        self.retained_scope = retained
        self.owner_states: dict[str, str] = {}
        self.pulls: dict[str, dict] = {}
        self.effect_readbacks: dict[str, dict] = {}
        self.census = {"complete": True, "process_count": 0, "counts": {}}
        self.census_sequence: list[dict] = []
        self.repos: dict[str, Path] = {}
        self.bases: dict[str, str] = {}
        self.branch = {"owner": "topic" if owner_topic else "work", "subject": "work", "subject2": "work"}
        self._repo("owner", topic=owner_topic)
        self._repo("subject")
        self.private = self.tmp / "retained" / "private"
        self.private.mkdir(parents=True)
        (self.private / "payload.bin").write_bytes(b"private payload\n")
        if anchor_is_owner:
            self.anchor = self.repos["owner"]
        else:
            self.anchor = self.tmp / "session"
            self.anchor.mkdir()
        self.audit = {
            "session_id": SID,
            "session_present": True,
            "active_lease_count": 0,
            "retained_run_count": 0,
            "runs": [],
            "coverage": {"retained_state_complete": True},
        }
        self.sessions = [{"session_id": SID, "worktree": str(self.anchor)}]
        self.manifest_path = self.staging / "manifest.json"
        self._install_fakes()

    # ---- repositories

    def _repo(self, ident, *, topic=False):
        remote, root = self.tmp / "remotes" / f"{ident}.git", self.tmp / "repos" / ident
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
        git(root, "config", "user.name", "Fixture")
        git(root, "config", "user.email", "fixture@example.test")
        git(root, "config", "commit.gpgsign", "false")
        git(root, "remote", "add", "origin", f"https://github.com/example/{ident}.git")
        git(root, "config", "remote.origin.pushurl", str(remote))
        (root / "README.md").write_text("base\n")
        paths = ["README.md"]
        if ident == "owner":
            (root / CONTINUATION).mkdir(parents=True)
            (root / CONTINUATION / "NOTES.md").write_text("continuation owner\n")
            paths.append(f"{CONTINUATION}/NOTES.md")
        git(root, "add", "--", *paths)
        git(root, "commit", "-q", "-m", "base")
        self.bases[ident] = git(root, "rev-parse", "HEAD")
        git(root, "push", "-q", "-u", "origin", "main")
        branch = self.branch[ident]
        git(root, "checkout", "-q", "-b", "work")
        (root / "implementation.py").write_text("value = 1\n")
        git(root, "add", "--", "implementation.py")
        git(root, "commit", "-q", "-m", "implementation")
        git(root, "push", "-q", "-u", "origin", "work")
        if topic:
            git(root, "checkout", "-q", "-b", branch)
            # A branch that was never pushed but names `origin` as its upstream (the first-push case).
            git(root, "config", f"branch.{branch}.remote", "origin")
            git(root, "config", f"branch.{branch}.merge", f"refs/heads/{branch}")
        self.repos[ident] = root

    def remote(self, ident):
        return self.tmp / "remotes" / f"{ident}.git"

    def clone_subject(self, ident="subject2"):
        root = self.tmp / "repos" / ident
        subprocess.run(
            ["git", "clone", "-q", "-b", "work", str(self.remote("subject")), str(root)],
            check=True,
            capture_output=True,
        )
        git(root, "config", "user.name", "Fixture")
        git(root, "config", "user.email", "fixture@example.test")
        git(root, "remote", "set-url", "origin", "https://github.com/example/subject.git")
        git(root, "config", "remote.origin.pushurl", str(self.remote("subject")))
        self.repos[ident] = root
        return root

    # ---- fakes

    def repo_info(self, slug):
        ident = slug.split("/")[1]
        return {"id": REPOSITORY_IDS.get(ident, 999), "full_name": slug, "default_branch": "main"}

    def gh(self, endpoint):
        parts = endpoint.split("/")
        assert parts[0] == "repos", endpoint
        slug, rest = f"{parts[1]}/{parts[2]}", parts[3:]
        if not rest:
            return json.dumps(self.repo_info(slug))
        if rest[0] in {"issues", "pulls"}:
            url = f"https://github.com/{slug}/{'issues' if rest[0] == 'issues' else 'pull'}/{rest[1]}"
            value = {"html_url": url, "state": self.owner_states.get(url, "open"), "number": int(rest[1])}
            value.update(self.pulls.get(url, {}))
            return json.dumps(value)
        if rest[:3] == ["git", "ref", "heads"]:
            branch = unquote(rest[3])
            remote = self.remote(parts[2])
            sha = self._real_run(
                ["git", "--git-dir", str(remote), "rev-parse", "--verify", "-q", f"refs/heads/{branch}"]
            )
            return json.dumps({"ref": f"refs/heads/{branch}", "object": {"type": "commit", "sha": sha}})
        raise AssertionError(endpoint)

    def _install_fakes(self):
        self._real_run = closeout.run
        world = self

        def fake_run(command, *, raw=False):
            if command[:4] == ["gh", "api", "--method", "GET"]:
                text = world.gh(command[4])
                return text.encode() if raw else text
            return world._real_run(command, raw=raw)

        class Client:
            def session_audit(self, session_id):
                return json.loads(json.dumps(world.audit))

            def capabilities(self):
                return {"sessions": json.loads(json.dumps(world.sessions))}

        def observe_many(roots, session_id, *, anchor, evidence=()):
            return world.observe(roots, session_id, anchor=anchor, evidence=evidence)

        import limen.conduct.client as conduct_client
        import limen.process_ownership as process_ownership

        self.monkeypatch.setattr(closeout, "run", fake_run)
        self.monkeypatch.setattr(conduct_client, "client_from_env", lambda: Client())
        self.monkeypatch.setattr(process_ownership, "observe_many", observe_many)

    def observe(self, roots, session_id, *, anchor, evidence=()):
        if self.census_sequence:
            return dict(self.census_sequence.pop(0))
        return dict(self.census)

    def read_effect(self, spec):
        if spec["id"] not in self.effect_readbacks:
            raise closeout.Unmeasured("no readback")
        return json.loads(json.dumps(self.effect_readbacks[spec["id"]]))

    def seams(self):
        return producer.Seams(
            audit=lambda session_id: json.loads(json.dumps(self.audit)),
            sessions=lambda: json.loads(json.dumps(self.sessions)),
            read_owner=lambda url: {"state": self.owner_states.get(url, "open"), "html_url": url},
            read_repository=self.repo_info,
            observe=self.observe,
            read_effect=self.read_effect,
            now=lambda: datetime(2026, 10, 18, tzinfo=UTC),
        )

    # ---- manifest and CLI

    def scope_rows(self):
        rows = [
            {
                "id": "owner",
                "kind": "git",
                "path": str(self.repos["owner"]),
                "base_head": self.bases["owner"],
                "owned_paths": ["implementation.py"],
                "retained_work": [],
            },
            {
                "id": "subject",
                "kind": "git",
                "path": str(self.repos["subject"]),
                "base_head": "fork-point",
                "owned_paths": ["implementation.py"],
                "retained_work": [],
            },
        ]
        if self.retained_scope:
            rows.append({"id": "private", "kind": "retained", "path": str(self.private), "owner_url": FOREIGN_URL})
        return rows

    def base_manifest(self):
        return {
            "schema": producer.MANIFEST_SCHEMA,
            "session_id": SID,
            "anchor": str(self.anchor),
            "owner_url": OWNER_URL,
            "receipt": {"root_id": "owner", "continuation": CONTINUATION},
            "scopes": self.scope_rows(),
            "verification": [],
            "custody": {"mode": "evidence", "bundle": f"{CONTINUATION}/custody-bundle.json"},
            "external_effects": [],
            "external_effects_enumerated": True,
        }

    def write_manifest(self, manifest, *, mode=0o600, path=None):
        target = path or self.manifest_path
        target.write_text(json.dumps(manifest))
        target.chmod(mode)
        self.manifest_path = target
        return target

    def cli(self, verb, *extra, live=False):
        """Run the producer CLI. `live=True` uses the production seams, faked only below them (broker, gh, census)."""
        argv = [verb, "--manifest", str(self.manifest_path), "--json", *extra]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = producer.main(argv, seams=None if live else self.seams())
        return code, json.loads(buffer.getvalue())

    def attest(self, scope, label, gate="trivial", *extra):
        return self.cli(
            "attest", "--scope", scope, "--label", label, "--gate", gate, "--gates-registry", str(self.registry), *extra
        )

    def write_bundle(self, manifest):
        scope_paths = {row["id"]: closeout.path_digest(Path(row["path"])) for row in manifest["scopes"]}
        bundle, files = make_graph(session_id=SID, scope_paths=scope_paths, now=datetime.now(UTC))
        owner = self.repos["owner"]
        for stale in getattr(self, "_bundle_files", []):
            stale.unlink(missing_ok=True)  # a regenerated bundle must not leave uncited orphans behind
        self._bundle_files = []
        for relative, raw in files.items():
            target = owner / relative
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(raw)
            self._bundle_files.append(target)
        (owner / CONTINUATION / "custody-bundle.json").write_text(json.dumps(bundle, sort_keys=True))

    def ready(self, *, custody="evidence", extra=None):
        """Attest both repositories, write the custody evidence and the manifest; return the manifest dict."""
        if getattr(self, "last_manifest", None) is not None and custody == "evidence" and not extra:
            return json.loads(json.dumps(self.last_manifest))
        manifest = self.base_manifest()
        for key, value in (extra or {}).items():
            manifest[key] = value
        self.write_manifest(manifest)
        for scope in ("owner", "subject"):
            code, payload = self.attest(scope, f"gate-{scope}")
            assert code == 0, payload
            manifest["verification"].append({"scope": scope, "evidence": payload["write"][0]})
        if custody == "evidence":
            self.write_bundle(manifest)
        else:
            manifest["custody"] = {"mode": "absence"}
        self.write_manifest(manifest)
        self.last_manifest = json.loads(json.dumps(manifest))
        return manifest

    def build_clean(self):
        code, payload = self.cli("build")
        assert code == 0, payload
        return payload

    def commit_and_push(self, payload, *, push=True):
        paths = shlex.split(payload["git_add"][0])[3:]
        owner = self.repos["owner"]
        git(owner, "add", "--", *paths)
        git(owner, "commit", "-q", "-m", "receipt")
        if push:
            git(owner, "push", "-q", "origin", f"HEAD:refs/heads/{self.branch['owner']}")

    def receipt(self):
        return json.loads((self.repos["owner"] / CONTINUATION / "session-closeout.json").read_text())


@pytest.fixture
def world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


@pytest.fixture
def complete_world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch, retained=False)


# =========================================================================== the happy path


def test_valid_two_repo_session_is_accepted_by_the_real_checker(world):
    manifest = world.ready()
    code, plan = world.cli("plan")
    assert code == 0 and plan["status"] == "ready", plan
    assert plan["census"]["process_count"] == 0
    assert plan["dry_run"].startswith("skipped")
    code, built = world.cli("build")
    assert code == 0 and built["status"] == "built", built
    receipt = world.receipt()
    assert receipt["schema"] == closeout.SCHEMA_V2
    assert receipt["disposition"] == "handoff", "a retained scope forces handoff (A23)"
    assert receipt["session_root_path_sha256"] == closeout.path_digest(world.anchor)
    assert not (world.anchor / ".git").exists(), "the anchor is a plain non-git directory"
    rows = {row["id"]: row for row in receipt["scope_roots"]}
    assert rows["owner"]["repository_id"] == 101 and rows["subject"]["repository_id"] == 102
    assert rows["owner"]["repository"] == "example/owner"
    assert "subject_head" not in rows["owner"] and rows["subject"]["subject_head"] == git(
        world.repos["subject"], "rev-parse", "HEAD"
    )
    assert rows["subject"]["base_head"] == world.bases["subject"], "fork-point is the merge base with origin/main"
    assert rows["subject"]["publication_branch"] == "work"
    assert rows["private"] == {
        "id": "private",
        "kind": "retained",
        "path_sha256": closeout.path_digest(world.private),
        "owner_url": FOREIGN_URL,
    }
    assert receipt["custody"]["contract"] == "limen.custody_receipt.v2"
    assert receipt["custody"]["root_ids"] == sorted(row["id"] for row in manifest["scopes"])
    assert receipt["external_effects"] == []
    assert built["dry_run"]["non_evidence"] is True
    # The printed list is the only thing the operator stages; evidence files are 0644.
    assert built["git_add"][0].startswith("git add -- ")
    for relative in built["write"]:
        assert (world.repos["owner"] / relative).stat().st_mode & 0o777 == 0o644
    # The attestation heads stay ancestors of the final head (A21) after the evidence + receipt commits.
    world.commit_and_push(built)
    final = git(world.repos["owner"], "rev-parse", "HEAD")
    for entry in receipt["verification"]:
        assert (
            subprocess.run(
                ["git", "-C", str(world.repos[entry["root_id"]]), "merge-base", "--is-ancestor", entry["head"], "HEAD"]
            ).returncode
            == 0
        )
    status_before = {key: git(root, "status", "--porcelain") for key, root in world.repos.items()}
    code, first = world.cli("check")
    assert code == 0 and first["status"] == "released", first
    code, second = world.cli("check")
    assert code == 0 and second["checker_result"] == first["checker_result"], "a fixed point: two bare exit-0 runs"
    assert {key: git(root, "status", "--porcelain") for key, root in world.repos.items()} == status_before
    assert git(world.repos["owner"], "rev-parse", "HEAD") == final
    assert first["checker_result"]["session_released"] is True
    assert first["checker_result"]["task_completed"] is False, "retained work is never a completion claim"
    assert first["checker"]["module_sha256"]


def test_complete_session_is_derived_and_accepted(complete_world):
    world = complete_world
    world.audit["runs"] = [{"status": "done"}, {"status": "succeeded"}]
    world.audit["retained_run_count"] = 2
    world.ready()
    built = world.build_clean()
    assert world.receipt()["disposition"] == "complete"
    world.commit_and_push(built)
    code, result = world.cli("check")
    assert code == 0 and result["checker_result"]["task_completed"] is True


def test_absence_custody_session_is_accepted_when_provable(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch, retained=False, anchor_is_owner=True)
    world.ready(custody="absence")
    built = world.build_clean()
    receipt = world.receipt()
    assert "contract" not in receipt["custody"]
    evidence = json.loads((world.repos["owner"] / receipt["custody"]["evidence"]).read_text())
    assert evidence["schema"] == "limen.custody_absence.v1"
    by_id = {row["root_id"]: row for row in evidence["scopes"]}
    assert "published" not in by_id["owner"], "publication is never recorded for the receipt root (A4)"
    assert by_id["owner"]["excluded"] and by_id["subject"]["published"] is True
    world.commit_and_push(built)
    code, result = world.cli("check")
    assert code == 0, result


# =========================================================================== refusals the checker cannot make


def test_missing_owner_url_is_refused_and_writes_nothing(world):
    manifest = world.ready()
    manifest.pop("owner_url")
    world.write_manifest(manifest)
    before = git(world.repos["owner"], "status", "--porcelain")
    code, payload = world.cli("build")
    assert code == 1 and "owner_url_missing" in codes(payload)
    assert not (world.repos["owner"] / CONTINUATION / "session-closeout.json").exists()
    assert git(world.repos["owner"], "status", "--porcelain") == before


def test_dirty_scope_is_refused_with_candidates_never_written(world):
    world.ready()
    (world.repos["subject"] / "stray.txt").write_text("not mine\n")
    code, payload = world.cli("build")
    assert code == 1 and "unattributed_dirty_path" in codes(payload)
    assert payload["unattributed_NOT_written"]["subject"]["unattributed_dirty"] == ["stray.txt"]
    assert not (world.repos["owner"] / CONTINUATION / "session-closeout.json").exists()


def test_unpublished_head_is_a_gap_not_exit_two(world):
    world.ready()
    subject = world.repos["subject"]
    (subject / "implementation.py").write_text("value = 2\n")
    git(subject, "add", "--", "implementation.py")
    git(subject, "commit", "-q", "-m", "ahead")
    code, payload = world.cli("plan")
    assert code == 1 and "not_remotely_durable" in codes(payload)


def test_a01_never_pushed_branch_is_ref_absent_gap_not_exit_two(world):
    world.ready()
    subject = world.repos["subject"]
    git(subject, "checkout", "-q", "-b", "topic")
    git(subject, "config", "branch.topic.remote", "origin")
    git(subject, "config", "branch.topic.merge", "refs/heads/topic")
    code, payload = world.cli("plan")
    assert code == 1, payload
    assert "ref_absent_on_remote" in codes(payload)


def test_a01_first_push_dry_run_is_labelled_non_evidence_and_never_a_pass(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch, owner_topic=True)
    world.ready()
    built = world.build_clean()
    world.commit_and_push(built, push=False)
    # The receipt branch was never pushed: the real published() RAISES, so a bare check is exit 2.
    code, bare = world.cli("check")
    assert code == 2 and bare["status"] == "unmeasured"
    code, dry = world.cli("check", "--expect-unpublished")
    assert code == 3, dry
    assert dry["status"] == "dry_run_clean_not_evidence" and dry["non_evidence"] is True
    assert dry["receipt_root_publication"] == "ref_absent_on_remote"
    assert "checker_result" not in dry and "released" not in json.dumps(dry)
    assert closeout.published.__name__ == "published", "the overlay never leaks past the dry run"
    git(world.repos["owner"], "push", "-q", "-u", "origin", "topic")
    code, real = world.cli("check")
    assert code == 0 and real["status"] == "released"


def test_a01_dry_run_surfaces_real_findings(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch)
    world.ready()
    built = world.build_clean()
    world.commit_and_push(built, push=False)
    (world.repos["subject"] / "late.txt").write_text("late\n")
    code, dry = world.cli("check", "--expect-unpublished")
    assert code == 1 and dry["status"] == "dry_run_findings"
    assert any("unattributed dirty path" in finding for finding in dry["findings"])


def test_control_the_checker_alone_accepts_unbound_custody_and_asserted_effects(tmp_path, monkeypatch):
    """Why the producer refuses what it refuses: hand-edit a built receipt and the real checker still releases it."""
    world = World(tmp_path, monkeypatch, retained=False, anchor_is_owner=True)
    world.ready(custody="absence")
    built = world.build_clean()
    owner = world.repos["owner"]
    receipt = world.receipt()
    (owner / receipt["custody"]["evidence"]).unlink()
    sealed = json.dumps({"schema": "limen.sealed_custody_receipt.tracked.v1", "run_id": "unrelated"}).encode()
    effect = json.dumps({"claimed": "merged"}).encode()
    (owner / CONTINUATION / "sealed.json").write_bytes(sealed)
    (owner / CONTINUATION / "asserted.json").write_bytes(effect)
    receipt["custody"] = {
        "verified": True,
        "root_ids": receipt["custody"]["root_ids"],
        "evidence": f"{CONTINUATION}/sealed.json",
        "sha256": hashlib.sha256(sealed).hexdigest(),
    }
    receipt["external_effects"] = [
        {
            "id": "asserted",
            "kind": "pull_request",
            "verified": True,
            "evidence": f"{CONTINUATION}/asserted.json",
            "sha256": hashlib.sha256(effect).hexdigest(),
        }
    ]
    (owner / CONTINUATION / "session-closeout.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    paths = [p for p in shlex.split(built["git_add"][0])[3:] if not p.endswith("custody-absence.json")]
    git(owner, "add", "--", *paths, f"{CONTINUATION}/sealed.json", f"{CONTINUATION}/asserted.json")
    git(owner, "commit", "-q", "-m", "hand edited receipt")
    git(owner, "push", "-q", "origin", "HEAD:refs/heads/work")
    code, result = world.cli("check")
    assert code == 0 and result["checker_result"]["task_completed"] is True, (
        "the checker cannot tell: the producer must"
    )


# ---- retained work (A18) and nested ownership (A9)


def _with_shared_file(world, owner_url=FOREIGN_URL, paths=("shared",), create=True):
    manifest = world.ready()
    if create:
        (world.repos["subject"] / "shared").mkdir()
        (world.repos["subject"] / "shared" / "notes.md").write_text("someone else is editing\n")
    for row in manifest["scopes"]:
        if row["id"] == "subject":
            row["retained_work"] = [{"paths": list(paths), "owner_url": owner_url}]
    world.write_manifest(manifest)
    return manifest


def test_retained_work_with_an_open_foreign_owner_is_accepted(world):
    _with_shared_file(world)
    code, payload = world.cli("plan")
    assert code == 0, payload
    assert payload["disposition"] == "handoff"


def test_retained_work_with_a_closed_or_absent_owner_is_refused(world):
    _with_shared_file(world)
    world.owner_states[FOREIGN_URL] = "closed"
    code, payload = world.cli("plan")
    assert code == 1 and "retained_owner_unavailable" in codes(payload)
    manifest = json.loads(world.manifest_path.read_text())
    manifest["scopes"][1]["retained_work"] = [{"paths": ["shared"]}]
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "retained_owner_unavailable" in codes(payload)


def test_a18_retained_owner_may_not_be_the_receipt_owner(world):
    _with_shared_file(world, owner_url=OWNER_URL)
    code, payload = world.cli("plan")
    assert code == 1 and "retained_owner_is_receipt_owner" in codes(payload)


def test_a18_ownership_broader_than_the_change_is_refused(world):
    manifest = _with_shared_file(world, paths=("shared", "nothing-here"))
    code, payload = world.cli("plan")
    assert code == 1 and "retained_path_matches_nothing" in codes(payload)
    manifest["scopes"][1]["retained_work"] = [{"paths": ["shared"], "owner_url": FOREIGN_URL}]
    manifest["scopes"][1]["owned_paths"] = ["implementation.py", "ghost"]
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "owned_path_matches_nothing" in codes(payload)


def test_a09_nested_retained_scope_is_declared_and_accepted_by_the_real_checker(world):
    manifest = world.ready()
    nested = world.repos["subject"] / "vendor-private"
    nested.mkdir()
    (nested / "x.bin").write_bytes(b"x")
    manifest["scopes"][1]["retained_work"] = [{"paths": ["vendor-private"], "owner_url": FOREIGN_URL}]
    manifest["scopes"].append({"id": "vendor", "kind": "retained", "path": str(nested), "owner_url": FOREIGN_URL})
    world.write_manifest(manifest)
    world.write_bundle(manifest)
    built = world.build_clean()
    rows = {row["id"]: row for row in world.receipt()["scope_roots"]}
    assert rows["vendor"]["nested_in"] == "subject"
    world.commit_and_push(built)
    code, result = world.cli("check")
    assert code == 0, result


def test_a09_nested_scope_without_parent_coverage_is_refused(world):
    manifest = world.ready()
    nested = world.repos["subject"] / "vendor-private"
    nested.mkdir()
    (nested / "x.bin").write_bytes(b"x")
    manifest["scopes"].append({"id": "vendor", "kind": "retained", "path": str(nested), "owner_url": FOREIGN_URL})
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "nested_scope_unowned" in codes(payload)


def test_a09_git_scope_nested_under_a_retained_scope_carries_nested_in_and_parent_retained_work(world):
    manifest = world.ready()
    inner = world.private / "inner"
    subprocess.run(["git", "init", "-q", "-b", "work", str(inner)], check=True, capture_output=True)
    git(inner, "config", "user.name", "Fixture")
    git(inner, "config", "user.email", "fixture@example.test")
    git(inner, "remote", "add", "origin", "https://github.com/example/subject.git")
    (inner / "a.txt").write_text("a\n")
    git(inner, "add", "--", "a.txt")
    git(inner, "commit", "-q", "-m", "inner")
    manifest["scopes"][2]["retained_work"] = [{"paths": ["inner"], "owner_url": FOREIGN_URL}]
    manifest["scopes"].append({"id": "inner", "kind": "git", "path": str(inner), "base_head": "fork-point"})
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    # The inner checkout was never pushed, so it is gated, but the nesting itself must be well formed.
    assert "nested_scope_unowned" not in codes(payload)
    assert code == 1


# ---- custody (A3, A4)


def test_a03_sealed_custody_tracked_receipt_is_not_scope_bound_custody(world):
    manifest = world.ready()
    (world.repos["owner"] / CONTINUATION / "custody-bundle.json").write_text(
        json.dumps({"schema": "limen.sealed_custody_receipt.tracked.v1", "run_id": "x"})
    )
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "custody_unbound_to_scope" in codes(payload)


def test_a03_a_bundle_that_validate_bundle_rejects_never_becomes_verified_custody(world):
    manifest = world.ready()
    other = json.loads((world.repos["owner"] / CONTINUATION / "custody-bundle.json").read_text())
    other["session_id"] = "some-other-session"
    (world.repos["owner"] / CONTINUATION / "custody-bundle.json").write_text(json.dumps(other))
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "custody_bundle_invalid" in codes(payload)


def test_custody_absence_is_refused_when_it_cannot_be_proven(world):
    manifest = world.ready(custody="absence")
    code, payload = world.cli("plan")
    assert code == 1
    assert {"custody_absence_anchor_not_git_scope", "custody_absence_not_measurable_for_retained_scope"} <= codes(
        payload
    )
    assert manifest["custody"] == {"mode": "absence"}


def test_a04_absence_is_refused_when_ignored_payload_exists(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch, retained=False, anchor_is_owner=True)
    world.ready(custody="absence")
    subject = world.repos["subject"]
    (subject / ".git" / "info" / "exclude").write_text("cache/\n")
    (subject / "cache").mkdir()
    (subject / "cache" / "blob.bin").write_bytes(b"ignored but present")
    code, payload = world.cli("plan")
    assert code == 1 and "custody_absence_unproven" in codes(payload)


def test_a04_absence_is_refused_when_a_stash_exists(tmp_path, monkeypatch):
    world = World(tmp_path, monkeypatch, retained=False, anchor_is_owner=True)
    world.ready(custody="absence")
    subject = world.repos["subject"]
    (subject / "implementation.py").write_text("value = 99\n")
    git(subject, "stash", "-q")
    code, payload = world.cli("plan")
    assert code == 1 and "custody_absence_unproven" in codes(payload)


# ---- verification (A5, A6, A8, A21)


def test_empty_verification_is_refused(world):
    manifest = world.ready()
    manifest["verification"] = []
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "verification_required" in codes(payload)


def test_attest_tolerates_only_its_own_evidence_directory_on_the_receipt_root(world):
    world.write_manifest(world.base_manifest())
    for label in ("first", "second"):
        code, payload = world.attest("owner", label)
        assert code == 0, payload
    (world.repos["owner"] / "junk.txt").write_text("not evidence\n")
    code, payload = world.attest("owner", "third")
    assert code == 1 and "tree_dirty_at_start" in codes(payload)


def test_a05_attestations_bind_the_gate_definition_the_head_and_the_digest_but_no_output(world):
    world.write_manifest(world.base_manifest())
    code, payload = world.attest("subject", "bound")
    record = json.loads((world.repos["owner"] / payload["write"][0]).read_text())
    assert record["schema"] == producer.ATTESTATION_SCHEMA and record["gate_id"] == "trivial"
    assert record["head"] == git(world.repos["subject"], "rev-parse", "HEAD") and record["exit_code"] == 0
    assert (
        record["gate_definition_sha256"]
        == hashlib.sha256(producer.json_bytes({"command": "true", "paths": ["implementation.py"]})).hexdigest()
    )
    assert record["output_sha256"] == hashlib.sha256(b"").hexdigest() and record["output_bytes"] == 0
    assert record["tree_clean_at_start"] is True and "duration_ms" not in record, "A16: no volatile fields"
    assert "stdout" not in record and "output" not in record


def test_a05_a_failing_gate_records_its_real_exit_and_is_refused_under_complete(complete_world):
    world = complete_world
    manifest = world.ready()
    code, payload = world.attest("subject", "gate-failing", "failing")
    assert code == 0 and payload["recorded"]["exit_code"] == 1, "attest records, it does not check=True"
    manifest["verification"].append({"scope": "subject", "evidence": payload["write"][0]})
    manifest["disposition"] = "complete"
    world.write_manifest(manifest)
    code, plan = world.cli("plan")
    assert code == 1 and "disposition_overstated" in codes(plan)


def test_a05_a_failing_completion_check_is_handed_off_to_an_open_owner(world):
    manifest = world.ready()
    code, payload = world.attest("subject", "gate-failing", "failing", "--purpose", "completion")
    assert code == 0
    manifest["verification"].append({"scope": "subject", "evidence": payload["write"][0]})
    world.write_manifest(manifest)
    built = world.build_clean()
    receipt = world.receipt()
    failing = [entry for entry in receipt["verification"] if entry["exit_code"] != 0]
    assert failing and failing[0]["purpose"] == "completion" and failing[0]["owner_url"] == OWNER_URL
    assert receipt["disposition"] == "handoff"
    world.commit_and_push(built)
    code, result = world.cli("check")
    assert code == 0 and result["checker_result"]["task_completed"] is False


def test_a05_a_failing_non_completion_check_is_never_emitted(world):
    manifest = world.ready()
    code, payload = world.attest("subject", "gate-failing", "failing")
    manifest["verification"].append({"scope": "subject", "evidence": payload["write"][0]})
    world.write_manifest(manifest)
    code, plan = world.cli("plan")
    assert code == 1 and "required_predicate_failed" in codes(plan)


def test_a05_attest_scrubs_the_environment_and_kills_the_group_at_its_deadline(world, monkeypatch):
    world.write_manifest(world.base_manifest())
    monkeypatch.setenv("GH_TOKEN", "leaky-value")
    monkeypatch.setenv("LIMEN_CONDUCT_TOKEN", "leaky-value")
    code, payload = world.attest("subject", "gate-env", "envcheck")
    assert code == 0 and payload["recorded"]["exit_code"] == 0, "the gate saw neither credential"
    started = time.monotonic()
    code, payload = world.attest("subject", "gate-slow", "slow", "--timeout", "1")
    assert code == 2 and "deadline" in payload["reason"]
    assert time.monotonic() - started < 20
    assert not (world.repos["owner"] / EVIDENCE_DIR / "gate-slow.json").exists(), "nothing is attested after a kill"


def test_a06_only_registry_declared_gates_are_attested(world):
    world.write_manifest(world.base_manifest())
    code, payload = world.cli(
        "attest", "--scope", "subject", "--label", "x", "--gates-registry", str(world.registry), "--", "echo", "hi"
    )
    assert code == 1 and "argv_not_registry_gate" in codes(payload)
    code, payload = world.cli(
        "attest", "--scope", "subject", "--label", "ok", "--gates-registry", str(world.registry), "--", "true"
    )
    assert code == 0 and payload["recorded"]["gate_id"] == "trivial"
    code, payload = world.attest("subject", "x", "no-such-gate")
    assert code == 1 and "gate_not_declared" in codes(payload)
    code, payload = world.cli(
        "attest",
        "--scope",
        "subject",
        "--label",
        "y",
        "--gate",
        "trivial",
        "--gates-registry",
        str(world.registry),
        "--",
        "false",
    )
    assert code == 1 and "argv_not_registry_gate" in codes(payload)


@pytest.mark.parametrize(
    "gate,code_",
    [
        ("mutating", "command_mutates_repository_or_broker"),
        ("abspath", "committed_bytes_unsafe"),
        ("tokenflag", "committed_bytes_unsafe"),
    ],
)
def test_a06_a14_unsafe_gate_commands_are_refused(world, gate, code_):
    world.write_manifest(world.base_manifest())
    code, payload = world.attest("subject", "unsafe", gate)
    assert code == 1 and code_ in codes(payload)
    assert not list((world.repos["owner"] / CONTINUATION).glob("closeout-evidence/*/unsafe.json"))


def test_a06_attest_refuses_a_dirty_tree_and_a_gate_that_changes_it(world):
    world.write_manifest(world.base_manifest())
    code, payload = world.attest("subject", "touch", "touch")
    assert code == 1 and "tree_or_head_changed_during_run" in codes(payload)
    code, payload = world.attest("subject", "after", "trivial")
    assert code == 1 and "tree_dirty_at_start" in codes(payload)


def test_a06_a_second_attestation_with_the_same_label_never_overwrites(world):
    world.write_manifest(world.base_manifest())
    code, first = world.attest("subject", "same")
    assert code == 0
    target = world.repos["owner"] / first["write"][0]
    original = target.read_bytes()
    code, payload = world.attest("subject", "same")
    assert code == 1 and "attestation_exists" in codes(payload)
    assert target.read_bytes() == original


def test_a21_receipt_root_verification_head_is_required_and_stale_checks_are_refused(world):
    manifest = world.ready()
    owner = world.repos["owner"]
    (owner / "implementation.py").write_text("value = 3\n")
    git(owner, "add", "--", "implementation.py")
    git(owner, "commit", "-q", "-m", "owned change after the attestation")
    git(owner, "push", "-q", "origin", "work")
    code, payload = world.cli("plan")
    assert code == 1 and "verification_stale" in codes(payload)
    assert manifest["verification"][0]["scope"] == "owner"


def test_a21_two_checkouts_of_one_repository_on_one_branch_are_refused(world):
    manifest = world.ready()
    clone = world.clone_subject()
    manifest["scopes"].append(
        {
            "id": "subject2",
            "kind": "git",
            "path": str(clone),
            "base_head": "fork-point",
            "owned_paths": [],
            "retained_work": [],
        }
    )
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "shared_publication_branch" in codes(payload)


# ---- broker audit and registration (A8, A20) and the census (A2)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda audit: audit.update(active_lease_count=1), "active_lease"),
        (lambda audit: audit.update(runs=[{"status": "running"}], retained_run_count=1), "nonterminal_runs"),
        (lambda audit: audit.update(coverage={"retained_state_complete": False}), "audit_incomplete"),
        (lambda audit: audit.update(retained_run_count=3), "retained_runs_incomplete"),
        (lambda audit: audit.update(session_id="somebody-else"), "audit_incomplete"),
    ],
)
def test_a08_audit_state_is_a_gap_before_the_checker_would_reject_it(world, mutation, expected):
    world.ready()
    mutation(world.audit)
    code, payload = world.cli("plan")
    assert code == 1 and expected in codes(payload)


def test_a08_complete_is_refused_when_a_run_is_not_a_success(complete_world):
    world = complete_world
    world.audit["runs"] = [{"status": "failed"}]
    world.audit["retained_run_count"] = 1
    manifest = world.ready()
    manifest["disposition"] = "complete"
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "disposition_overstated" in codes(payload)


def test_a20_broker_binding_mismatch_classes_are_named(world):
    world.ready()
    world.sessions = []
    code, payload = world.cli("plan")
    assert code == 1 and "binding_no_row" in codes(payload)
    message = next(gap["message"] for gap in payload["gaps"] if gap["code"] == "binding_no_row")
    assert "BLOCKED" in message and "never overridden" in message
    world.sessions = [{"session_id": SID, "worktree": str(world.tmp / "elsewhere")}]
    code, payload = world.cli("plan")
    assert "binding_worktree_mismatch" in codes(payload)
    alias = world.tmp / "alias"
    alias.symlink_to(world.anchor, target_is_directory=True)
    world.sessions = [{"session_id": SID, "worktree": str(alias)}]
    code, payload = world.cli("plan")
    assert "binding_worktree_not_canonical" in codes(payload)
    world.sessions = [{"session_id": SID, "worktree": "relative/path"}]
    code, payload = world.cli("plan")
    assert "binding_worktree_not_absolute" in codes(payload)


def test_a02_census_is_reported_as_counts_by_category_without_pids(world):
    world.ready()
    world.census = {
        "complete": True,
        "process_count": 3,
        "counts": {"unknown": 2, "shared_service": 1},
        "processes": [{"pid": 41231, "category": "unknown"}],
    }
    code, payload = world.cli("plan")
    assert code == 1 and "process_census_nonzero" in codes(payload)
    text = json.dumps(payload)
    assert "41231" not in text and payload["census"]["counts"] == {"shared_service": 1, "unknown": 2}
    assert "shared directory" not in next(
        g["message"] for g in payload["gaps"] if g["code"] == "process_census_nonzero"
    )


def test_a02_a_shared_home_anchor_cannot_reach_zero_while_other_agents_run(world):
    manifest = world.ready()
    home = Path.home().resolve()
    manifest["anchor"] = str(home)
    world.write_manifest(manifest)
    world.census = {"complete": True, "process_count": 5, "counts": {"unknown": 5}}
    world.sessions = [{"session_id": SID, "worktree": str(home)}]
    code, payload = world.cli("plan")
    message = next(g["message"] for g in payload["gaps"] if g["code"] == "process_census_nonzero")
    assert "shared directory" in message and "cannot reach zero" in message


def test_a02_an_incomplete_census_is_unmeasured_exit_two(world):
    world.ready()
    world.census = {"complete": False, "process_count": 0}
    code, payload = world.cli("plan")
    assert code == 2 and payload["status"] == "unmeasured"


# ---- fork point and base (A7), publication branch (A15)


def test_fork_point_equal_to_head_is_refused(world):
    world.ready()
    subject = world.repos["subject"]
    git(subject, "push", "-q", "origin", "work:main")
    code, payload = world.cli("plan")
    assert code == 1 and "fork_point_equals_head" in codes(payload)


def test_a07_explicit_base_must_not_hide_commits_after_the_fork_point(world):
    manifest = world.ready()
    subject = world.repos["subject"]
    # The session's own implementation commit sits after the fork point; a base at that commit would hide it.
    manifest["scopes"][1]["base_head"] = git(subject, "rev-parse", "HEAD~1")
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 0 and "base_after_fork_point" not in codes(payload), "the fork point itself is a valid explicit base"
    git(subject, "checkout", "-q", "-b", "later")
    git(subject, "config", "branch.later.remote", "origin")
    git(subject, "config", "branch.later.merge", "refs/heads/work")
    (subject / "second.py").write_text("v = 2\n")
    git(subject, "add", "--", "second.py")
    git(subject, "commit", "-q", "-m", "second")
    git(subject, "push", "-q", "origin", "later:work")
    manifest["scopes"][1]["base_head"] = git(subject, "rev-parse", "HEAD~1")
    manifest["scopes"][1]["owned_paths"] = ["implementation.py", "second.py"]
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "base_after_fork_point" in codes(payload)
    manifest["scopes"][1]["base_head"] = git(subject, "rev-parse", "HEAD")
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "base_equals_head" in codes(payload)


def test_a07_an_explicit_base_must_be_an_ancestor_of_head(world):
    manifest = world.ready()
    manifest["scopes"][1]["base_head"] = "0" * 40
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "base_not_ancestor" in codes(payload)
    manifest["scopes"][1]["base_head"] = "not-a-sha"
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "base_head_required" in codes(payload)


def test_a15_publication_branch_is_derived_from_the_upstream_never_guessed(world):
    manifest = world.ready()
    subject = world.repos["subject"]
    manifest["scopes"][1]["publication_branch"] = "somewhere-else"
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "publication_branch_mismatch" in codes(payload)
    manifest["scopes"][1].pop("publication_branch")
    world.write_manifest(manifest)
    git(subject, "config", "branch.work.remote", "elsewhere")
    code, payload = world.cli("plan")
    assert code == 1 and "publication_branch_unbound" in codes(payload)


def test_a15_a_detached_checkout_needs_an_explicit_branch_and_a_live_proof(world):
    manifest = world.ready()
    subject = world.repos["subject"]
    git(subject, "checkout", "-q", "--detach")
    code, payload = world.cli("plan")
    assert code == 1 and "publication_branch_unbound" in codes(payload)
    manifest["scopes"][1]["publication_branch"] = "work"
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 0, payload
    assert {fact["id"]: fact for fact in payload["scopes"]}["subject"]["publication_branch_source"] == "detached"


# ---- effects (A10, A16, A17)


def _effect_manifest(world, effects, **extra):
    manifest = world.ready()
    manifest["external_effects"] = effects
    manifest.update(extra)
    world.write_manifest(manifest)
    return manifest


def test_a10_an_empty_effect_list_needs_an_explicit_enumeration_attestation(world):
    manifest = world.ready()
    manifest.pop("external_effects_enumerated")
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "external_effects_not_enumerated" in codes(payload)


def test_a10_effect_verification_is_derived_from_a_readback_never_asserted(world):
    spec = {"id": "pr-5", "kind": "pull_request", "url": PULL_URL, "expect": {"merged": True}}
    _effect_manifest(world, [{**spec, "verified": True}])
    code, payload = world.cli("plan")
    assert code == 1 and "external_effect_assertion" in codes(payload)
    _effect_manifest(world, [{"id": "pr-5", "kind": "pull_request", "url": PULL_URL}])
    code, payload = world.cli("plan")
    assert code == 1 and "external_effect_expect_required" in codes(payload)
    _effect_manifest(world, [{"id": "pr-5", "kind": "pull_request", "url": PULL_URL, "expect": {}}])
    code, payload = world.cli("plan")
    assert code == 1 and "external_effect_expect_required" in codes(payload)


def test_a10_an_unmet_expectation_is_unverified_and_forces_handoff(complete_world):
    world = complete_world
    world.effect_readbacks["pr-5"] = {"state": "open", "html_url": PULL_URL, "merged": False}
    _effect_manifest(world, [{"id": "pr-5", "kind": "pull_request", "url": PULL_URL, "expect": {"merged": True}}])
    built = world.build_clean()
    receipt = world.receipt()
    assert receipt["disposition"] == "handoff", "an unverified effect can never be a complete session (A23)"
    assert receipt["external_effects"][0]["verified"] is False
    assert receipt["external_effects"][0]["owner_url"] == OWNER_URL
    world.commit_and_push(built)
    code, result = world.cli("check")
    assert code == 0 and result["checker_result"]["task_completed"] is False


def test_a10_a_met_expectation_is_verified_and_the_session_can_complete(complete_world):
    world = complete_world
    world.effect_readbacks["pr-5"] = {
        "state": "closed",
        "html_url": PULL_URL,
        "merged": True,
        "head": {"sha": "a" * 40},
    }
    _effect_manifest(
        world,
        [{"id": "pr-5", "kind": "pull_request", "url": PULL_URL, "expect": {"merged": True, "head.sha": "a" * 40}}],
    )
    built = world.build_clean()
    receipt = world.receipt()
    assert receipt["disposition"] == "complete" and receipt["external_effects"][0]["verified"] is True
    world.commit_and_push(built)
    code, result = world.cli("check")
    assert code == 0 and result["checker_result"]["task_completed"] is True


def test_a10_caller_supplied_effects_are_never_marked_verified(world):
    world.ready()
    evidence = world.repos["owner"] / CONTINUATION / "export-receipt.json"
    evidence.write_text(json.dumps({"attested_by": "caller", "export": "archive-1"}))
    _effect_manifest(world, [{"id": "export-1", "kind": "export", "evidence": f"{CONTINUATION}/export-receipt.json"}])
    built = world.build_clean()
    effect = world.receipt()["external_effects"][0]
    assert effect["verified"] is False and effect["owner_url"] == OWNER_URL
    world.commit_and_push(built)
    code, result = world.cli("check")
    assert code == 0, result


def test_a14_effect_evidence_carrying_a_secret_is_never_written(world):
    world.effect_readbacks["pr-5"] = {"state": "open", "html_url": PULL_URL, "note": "ghp_" + "a" * 36}
    _effect_manifest(world, [{"id": "pr-5", "kind": "pull_request", "url": PULL_URL, "expect": {"state": "open"}}])
    code, payload = world.cli("build")
    assert code == 1 and "committed_bytes_unsafe" in codes(payload)
    assert not (world.repos["owner"] / EVIDENCE_DIR / "effect-pr-5.json").exists()
    assert "ghp_" not in json.dumps(payload)


def test_a16_existing_effect_evidence_is_reused_not_regenerated(world):
    world.effect_readbacks["pr-5"] = {"state": "open", "html_url": PULL_URL, "merged": False}
    _effect_manifest(world, [{"id": "pr-5", "kind": "pull_request", "url": PULL_URL, "expect": {"merged": True}}])
    built = world.build_clean()
    evidence = world.repos["owner"] / EVIDENCE_DIR / "effect-pr-5.json"
    original = evidence.read_bytes()
    receipt = (world.repos["owner"] / CONTINUATION / "session-closeout.json").read_bytes()
    world.effect_readbacks["pr-5"] = {"state": "closed", "html_url": PULL_URL, "merged": True}
    code, again = world.cli("build")
    assert code == 0 and again["status"] == "unchanged", again
    assert evidence.read_bytes() == original
    assert (world.repos["owner"] / CONTINUATION / "session-closeout.json").read_bytes() == receipt
    assert built["write"]


def test_a17_the_receipt_branch_is_proven_by_its_scope_row_not_an_effect(world):
    world.effect_readbacks["ref-1"] = {"ref": "refs/heads/work", "object": {"sha": "b" * 40}}
    _effect_manifest(
        world,
        [
            {
                "id": "ref-1",
                "kind": "git_ref",
                "repository": "example/owner",
                "branch": "work",
                "expect": {"object.sha": "b" * 40},
            }
        ],
    )
    code, payload = world.cli("plan")
    assert code == 1 and "effect_is_receipt_branch" in codes(payload)


def test_the_production_seams_read_prs_issues_and_refs_through_gh(world):
    """Same flow with the live seams: only the broker client, `gh` and the census are faked, below the producer."""
    world.pulls[PULL_URL] = {
        "merged": True,
        "merge_commit_sha": "c" * 40,
        "head": {"sha": "a" * 40},
        "base": {"ref": "main"},
    }
    head = git(world.repos["subject"], "rev-parse", "HEAD")
    _effect_manifest(
        world,
        [
            {"id": "pr-5", "kind": "pull_request", "url": PULL_URL, "expect": {"merged": True, "base.ref": "main"}},
            {"id": "issue-7", "kind": "issue", "url": FOREIGN_URL, "expect": {"state": "open"}},
            {
                "id": "ref-subject",
                "kind": "git_ref",
                "repository": "example/subject",
                "branch": "work",
                "expect": {"object.sha": head},
            },
        ],
    )
    code, built = world.cli("build", live=True)
    assert code == 0, built
    effects = {effect["id"]: effect for effect in world.receipt()["external_effects"]}
    assert all(effect["verified"] is True for effect in effects.values()) and len(effects) == 3
    evidence = json.loads((world.repos["owner"] / effects["ref-subject"]["evidence"]).read_text())
    assert evidence["readback"]["object"] == {"type": "commit", "sha": head} and evidence["matches"] is True
    world.commit_and_push(built)
    code, result = world.cli("check", live=True)
    assert code == 0, result


def test_the_production_seams_fail_closed_without_a_broker(world, monkeypatch):
    world.ready()
    import limen.conduct.client as conduct_client

    def unavailable():
        raise conduct_client.BrokerUnavailable("conduct broker is not configured")

    monkeypatch.setattr(conduct_client, "client_from_env", unavailable)
    code, payload = world.cli("plan", live=True)
    assert code == 2 and payload["status"] == "unmeasured" and payload["error_type"] == "BrokerUnavailable"
    assert not (world.repos["owner"] / CONTINUATION / "session-closeout.json").exists()


# ---- disposition (A23)


def test_a23_complete_is_refused_when_anything_is_retained(world):
    manifest = world.ready()
    manifest["disposition"] = "complete"
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "disposition_overstated" in codes(payload)


def test_a23_a_complete_claim_can_always_be_downgraded_to_handoff_but_read_only_owns_nothing(complete_world):
    world = complete_world
    manifest = world.ready()
    manifest["disposition"] = "handoff"
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 0 and payload["disposition"] == "handoff"
    manifest["disposition"] = "read_only"
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "read_only_with_owned_paths" in codes(payload)


# ---- paths, files and manifests (A12, A13, A14, A19)


def test_a12_an_uncited_attestation_is_named_before_it_becomes_an_unattributed_path(world):
    world.ready()
    code, payload = world.attest("subject", "superseded")
    assert code == 0
    code, plan = world.cli("plan")
    assert code == 1 and "uncited_evidence_file" in codes(plan)
    assert any("superseded" in gap["message"] for gap in plan["gaps"])


def test_a13_a_symlinked_continuation_is_refused_and_nothing_is_written_through_it(world):
    world.ready()
    owner = world.repos["owner"]
    elsewhere = world.tmp / "elsewhere"
    (owner / CONTINUATION).rename(elsewhere)
    (owner / CONTINUATION).symlink_to(elsewhere, target_is_directory=True)
    code, payload = world.cli("build")
    assert code == 1 and "continuation_unsafe" in codes(payload)
    assert not (elsewhere / "session-closeout.json").exists()
    code, payload = world.attest("subject", "through-link")
    assert code == 1


def test_a13_a_symlinked_evidence_directory_is_refused(world):
    manifest = world.ready()
    owner = world.repos["owner"]
    target = world.tmp / "outside"
    target.mkdir()
    (owner / CONTINUATION / "closeout-evidence").rename(world.tmp / "moved-evidence")
    (owner / CONTINUATION / "closeout-evidence").symlink_to(target, target_is_directory=True)
    world.write_manifest(manifest)
    code, payload = world.cli("build")
    assert code == 1
    assert codes(payload) & {"evidence_dir_unsafe", "verification_evidence_unreadable"}
    assert list(target.iterdir()) == []


def test_a13_an_overlong_session_id_cannot_name_an_evidence_directory(world):
    manifest = world.ready()
    manifest["session_id"] = "s" * 110
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 1 and "session_slug_invalid" in codes(payload)


def test_a19_a_manifest_inside_a_scope_or_with_open_permissions_is_refused(world):
    manifest = world.ready()
    world.write_manifest(manifest, mode=0o644)
    code, payload = world.cli("plan")
    assert code == 1 and "manifest_mode_too_open" in codes(payload)
    inside = world.repos["subject"] / "manifest.json"
    world.write_manifest(manifest, path=inside)
    code, payload = world.cli("plan")
    assert "manifest_inside_scope" in codes(payload)


def test_a14_committed_output_carries_no_private_path_secret_or_origin(world):
    world.ready()
    built = world.build_clean()
    forbidden = [str(world.tmp), str(Path.home()), "/Users/", "/private/", "/var/folders", "file://", "ghp_", "token"]
    for relative in built["write"]:
        text = (world.repos["owner"] / relative).read_text()
        for item in forbidden:
            assert item not in text, (relative, item)
    for relative in built["git_add"][0].split("--", 1)[1].split():
        assert not relative.startswith("/")
    assert str(world.tmp) not in json.dumps(built)
    assert producer.scrub_problems(world.manifest_path.read_bytes(), literals=[], allowed=[], strict=True), (
        "the private manifest itself would be refused as a committed file"
    )


def test_a14_origin_credentials_are_refused_and_never_echoed(world):
    world.ready()
    git(
        world.repos["subject"], "remote", "set-url", "origin", "https://user:s3cr3tvalue@github.com/example/subject.git"
    )
    code, payload = world.cli("plan")
    assert code == 1 and "origin_has_embedded_credentials" in codes(payload)
    assert "s3cr3tvalue" not in json.dumps(payload)


def test_a14_a_private_path_origin_is_refused_unless_the_test_flag_allows_it(world):
    world.ready()
    git(world.repos["subject"], "remote", "set-url", "origin", str(world.remote("subject")))
    code, payload = world.cli("plan")
    assert code == 1 and "repository_string_is_private_path" in codes(payload)
    code, payload = world.cli("plan", "--allow-local-remote")
    assert "repository_string_is_private_path" not in codes(payload)


def test_a14_scrubber_flags_secrets_paths_and_declared_literals_without_echoing_them():
    bad = b'{"a": "/Users/someone/x", "b": "Bearer abcdefghijkl", "c": "op://vault/item"}'
    assert producer.scrub_problems(bad, literals=[], allowed=[], strict=True) == ["secret_shape", "absolute_path"]
    assert producer.scrub_problems(b"/work/private/dir", literals=["/work/private/dir"], allowed=[], strict=False) == [
        "declared_private_path"
    ]
    assert (
        producer.scrub_problems(b'{"repository": "/Users/x/r"}', literals=[], allowed=["/Users/x/r"], strict=True) == []
    )
    assert producer.scrub_problems(b'"password": "hunter22"', literals=[], allowed=[], strict=True) == [
        "credential_assignment"
    ]


# ---- the dry run is the real checker (A11), create-only writes (A16), rollback


def test_a11_the_dry_run_is_the_real_checker_and_rolls_back_what_it_created(world):
    world.ready()
    # Plan sees a quiet census; by the dry run a straggler has appeared, which only the real checker measures.
    world.census_sequence = [
        {"complete": True, "process_count": 0, "counts": {}},
        {"complete": True, "process_count": 1, "counts": {"unknown": 1}},
    ]
    code, payload = world.cli("build")
    assert code == 1 and payload["status"] == "refused_rolled_back", payload
    assert "checker_finding" in codes(payload)
    assert any("surviving or unattributed processes" in gap["message"] for gap in payload["gaps"])
    assert not (world.repos["owner"] / CONTINUATION / "session-closeout.json").exists()
    assert closeout.git.__name__ == "git" and closeout.published.__name__ == "published"


def test_a11_the_dry_run_reports_checker_unmeasured_reasons_as_gaps(world):
    world.ready()
    world.audit["session_present"] = False
    world.sessions = [{"session_id": SID, "worktree": str(world.anchor)}]
    manifest = json.loads(world.manifest_path.read_text())
    manifest["broker_scope_root_id"] = "subject"
    world.write_manifest(manifest)
    code, payload = world.cli("build")
    assert code == 1 and "broker_scope_unsupported" in codes(payload)


def test_create_only_rebuild_is_idempotent_and_never_overwrites_a_different_receipt(world):
    world.ready()
    first = world.build_clean()
    path = world.repos["owner"] / CONTINUATION / "session-closeout.json"
    snapshot = path.read_bytes()
    code, again = world.cli("build")
    assert code == 0 and again["status"] == "unchanged" and again["write"] == []
    assert path.read_bytes() == snapshot
    path.write_bytes(snapshot + b"\n")
    code, refused = world.cli("build")
    assert code == 1 and "receipt_exists_use_distinct_name" in codes(refused)
    assert path.read_bytes() == snapshot + b"\n"
    path.unlink()  # the operator discards the tampered file; a leftover would be an unattributed dirty path
    manifest = json.loads(world.manifest_path.read_text())
    manifest["receipt"]["name"] = "session-closeout-second.json"
    world.write_manifest(manifest)
    code, second = world.cli("build")
    assert code == 0 and second["status"] == "built"
    assert first["git_add"] != second["git_add"]


def test_build_leaves_nothing_staged_or_committed(world):
    world.ready()
    owner = world.repos["owner"]
    head = git(owner, "rev-parse", "HEAD")
    world.build_clean()
    assert git(owner, "rev-parse", "HEAD") == head
    assert git(owner, "diff", "--cached", "--name-only") == ""
    assert git(owner, "log", "-1", "--format=%s") == "implementation"


# ---- check (A22, A24) and top-level hygiene


def test_a22_recheck_heads_names_the_scope_that_moved(world):
    world.ready()
    built = world.build_clean()
    world.commit_and_push(built)
    code, held = world.cli("check", "--recheck-heads")
    assert code == 0 and held["recheck"] == {"held": ["subject"], "moved": []}
    subject = world.repos["subject"]
    (subject / "implementation.py").write_text("value = 5\n")
    git(subject, "add", "--", "implementation.py")
    git(subject, "commit", "-q", "-m", "someone else moved the shared checkout")
    code, moved = world.cli("check", "--recheck-heads")
    assert code == 1 and moved["recheck"]["moved"] == ["subject"] and moved["status"] == "heads_moved"


def test_a24_checker_skew_against_the_canonical_copy_is_reported(world, tmp_path):
    world.ready()
    built = world.build_clean()
    world.commit_and_push(built)
    same = Path(closeout.__file__)
    code, result = world.cli("check", "--canonical-checker", str(same))
    assert code == 0 and result["checker"]["skew"] is False
    other = tmp_path / "canonical-session-closeout.py"
    other.write_text(same.read_text() + "\n# a different canonical checker\n")
    code, result = world.cli("check", "--canonical-checker", str(other))
    assert code == 0 and result["checker"]["skew"] is True


def test_exceptions_the_checker_leaks_as_tracebacks_exit_two_in_the_producer(world, monkeypatch):
    world.ready()

    def explode(ctx, seams):
        raise AttributeError("boom")

    monkeypatch.setattr(producer, "derive", explode)
    code, payload = world.cli("plan")
    assert code == 2 and payload["error_type"] == "AttributeError" and payload["status"] == "unmeasured"
    monkeypatch.setattr(producer, "derive", lambda ctx, seams: [][1])
    code, payload = world.cli("plan")
    assert code == 2 and payload["error_type"] == "IndexError"


def test_a_missing_anchor_or_receipt_is_unmeasured_exit_two(world):
    manifest = world.ready()
    code, payload = world.cli("check")
    assert code == 2 and "receipt does not exist" in payload["reason"]
    manifest["anchor"] = str(world.tmp / "does-not-exist")
    world.write_manifest(manifest)
    code, payload = world.cli("plan")
    assert code == 2 and "anchor does not exist" in payload["reason"]


def test_the_producer_never_registers_stages_commits_or_pushes():
    source = (ROOT / "scripts/session-closeout-receipt.py").read_text()
    for verb in ('"commit"', '"push"', '"merge"', '"add"', '"register"', '"submit"', '"report"', '"harvest"'):
        assert verb not in source, f"{verb} would be a mutating call; the producer only prints `git add -- <paths>`"
    for banned in ("conduct register", "conduct submit", "gh pr merge", "merge-drain"):
        assert banned not in source.replace("limen conduct", ""), banned


def test_the_script_runs_as_a_cli_under_an_isolated_interpreter():
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts/session-closeout-receipt.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0 and "plan" in result.stdout and "attest" in result.stdout
