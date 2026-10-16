"""The pre-rewrite containment predicate classifies a synthetic two-lineage history correctly.

Fixture: a shared boundary commit, an OLD lineage that adds a purged file and a third-party name,
and a NEW lineage produced the way the 2026-10-10 rewrite was: purged path dropped, name scrubbed,
abbreviated ids in messages rewritten, same author dates. A bare "private" clone holds the old
lineage. Nothing here touches the real repository.
"""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "check-prerewrite-containment.py"
MARKER = "# Sensitive material lives in the private sibling 4444J99/limen--private (purged)"


def load():
    spec = importlib.util.spec_from_file_location("prerewrite_containment", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(cwd, *args, date=None):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


def commit(repo, files, message, date):
    for name, body in files.items():
        path = repo / name
        if body is None:
            run(repo, "rm", "-q", name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
        run(repo, "add", name)
    run(repo, "commit", "-q", "-m", message, date=date)
    return run(repo, "rev-parse", "HEAD")


@pytest.fixture()
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "init", "-q", "-b", "main")
    boundary = commit(repo, {"app.txt": "v1\n", "notes.txt": "intro\n"}, "base", "2026-05-31T10:00:00")

    # OLD lineage
    o1 = commit(
        repo,
        {"secret/record.md": "private\n", "notes.txt": "intro\nmet Alice today\n"},
        "add record",
        "2026-06-01T10:00:00",
    )
    o2 = commit(repo, {"app.txt": "v2\n"}, f"bump app after {o1[:7]}", "2026-06-02T10:00:00")
    o3 = commit(repo, {"app.txt": "v3 local only\n"}, "unpushed local work", "2026-06-03T10:00:00")
    run(repo, "branch", "old-topic", o3)
    old_main = o2

    # NEW lineage, as filter-repo would produce it
    run(repo, "checkout", "-q", "--detach", boundary)
    n1 = commit(repo, {"notes.txt": "intro\nmet Person-One today\n"}, "add record", "2026-06-01T10:00:00")
    commit(repo, {"app.txt": "v2\n"}, f"bump app after {n1[:7]}", "2026-06-02T10:00:00")
    manifest = commit(repo, {".gitignore": f"{MARKER}\n/secret/\n"}, "privacy manifest", "2026-10-10T10:00:00")
    run(repo, "update-ref", "refs/remotes/origin/main", manifest)
    run(repo, "checkout", "-q", "-B", "main", old_main)
    run(repo, "remote", "add", "origin", str(tmp_path / "nowhere.git"))
    run(repo, "config", "branch.main.remote", "origin")
    run(repo, "config", "branch.main.merge", "refs/heads/main")

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    run(tmp_path, "clone", "-q", "--bare", "--no-local", str(repo), str(private / "limen--private.git"))

    mod = load()
    monkeypatch.chdir(repo)
    monkeypatch.setattr(mod, "BOUNDARY", boundary)
    monkeypatch.setattr(mod, "MANIFEST_COMMIT", manifest)
    return {
        "mod": mod,
        "repo": repo,
        "private": private,
        "ledger": tmp_path / "ledger.json",
        "o1": o1,
        "o2": o2,
        "o3": o3,
    }


def test_classes_follow_the_evidence(world):
    mod = world["mod"]
    ev = mod.evaluate(world["private"], learn=True)
    classes = {oid: c["class"] for oid, c in ev["commits"].items()}
    assert classes[world["o1"]] == "purge-equivalent"  # dropped path + scrubbed name
    assert classes[world["o2"]] == "already-on-new-lineage"  # message ids rewritten, change identical
    assert classes[world["o3"]] == "unique-work"
    refs = {r["ref"]: r["class"] for r in ev["refs"]}
    assert refs == {"refs/heads/main": "purge-equivalent", "refs/heads/old-topic": "unique-work"}
    assert ev["blobs_missing"] == [] and ev["unheld_paths"] == []


def test_ledger_never_carries_old_ids_paths_or_names(world):
    mod = world["mod"]
    assert mod.main(["--private-dir", str(world["private"]), "--ledger", str(world["ledger"]), "--write-ledger"]) == 1
    text = world["ledger"].read_text()
    for needle in (world["o1"], world["o1"][:7], "secret/record.md", "Alice"):
        assert needle not in text
    assert json.loads(text)["summary"]["purged_paths"] == 1


def test_upstream_quarantine_is_the_only_remaining_failure(world, capsys):
    mod = world["mod"]
    args = ["--private-dir", str(world["private"]), "--ledger", str(world["ledger"])]
    assert mod.main([*args, "--write-ledger"]) == 1
    assert "C: refs/heads/main has a push-capable upstream" in capsys.readouterr().out
    # old-topic has no upstream: push.default=current would still target origin
    for branch in ("main", "old-topic"):
        run(world["repo"], "config", f"branch.{branch}.remote", ".")
        run(world["repo"], "config", f"branch.{branch}.merge", f"refs/heads/{branch}")
        run(world["repo"], "config", f"branch.{branch}.pushRemote", ".")
    assert mod.main(args) == 0
    assert "CONTAINED" in capsys.readouterr().out


def test_moved_ref_is_unclassified_until_rerecorded(world, capsys):
    mod = world["mod"]
    args = ["--private-dir", str(world["private"]), "--ledger", str(world["ledger"])]
    mod.main([*args, "--write-ledger"])
    run(world["repo"], "branch", "-f", "old-topic", world["o2"])
    assert mod.main(args) == 1
    assert "unclassified old-lineage ref refs/heads/old-topic" in capsys.readouterr().out


def test_purged_blob_absent_from_private_fails(world, capsys):
    mod = world["mod"]
    run(world["repo"], "checkout", "-q", "old-topic")
    commit(world["repo"], {"secret/record.md": "never published\n"}, "edit record", "2026-06-04T10:00:00")
    assert mod.main(["--private-dir", str(world["private"]), "--ledger", str(world["ledger"]), "--write-ledger"]) == 1
    assert "B: 1 purged blob(s) have no hash match in limen--private" in capsys.readouterr().out


def test_ref_names_never_carry_object_ids():
    mod = load()
    abbrev = mod.public_ref_name("refs/tags/archive/pr-2543-detached-67afecedd1ab-20260828")
    assert "67afecedd1ab" not in abbrev and abbrev.endswith("-20260828")
    full = mod.public_ref_name("refs/limen/retired-worktrees/x/" + "ab12" * 10)
    assert "ab12ab12" not in full
    assert mod.public_ref_name("refs/heads/fix/portable-acceptance-20261003").endswith("-20261003")
