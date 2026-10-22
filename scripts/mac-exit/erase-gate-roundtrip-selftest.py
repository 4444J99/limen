#!/usr/bin/env python3
"""Round trip: the REAL sweep and the REAL prover feed the REAL readiness predicate's proof binding.

WHY: round 1 shipped a predicate whose self-test wrote the prover's tips.tsv itself, in the predicate's own format, while
the real prover wrote another (short branch names). Every assertion passed and no real PROVEN-ALL verdict could ever bind
(INT-5). A self-test that fabricates its producer's output proves nothing about the producer. This one builds a few
fixture repositories, sweeps them with git-sweep.sh, proves them with prove-remote-held.py, and asks
check-exit-ready.py's binding (`proof_unbound`) about every checkout.

A fixture remote is a path on this disk, so the real proof carries the TRUST-REMOTE-UNDER gap and the binding refuses it
at the gap step. That step is only reached after the checkout's repository label and common dir have joined, so reaching
it proves those joins. With only the gaps set aside, every pushed checkout must then fail at the offsite step, which is
only reached after every keyed ref (branches, tags, detached HEADs, per-worktree refs) was found, equal and proven; and a
checkout committed to after the proof must fail as moved. Two negative controls show the test can see the round-1
defect: tips.tsv rewritten to short names must not bind, and tips.tsv without its #END row must be refused.

usage: erase-gate-roundtrip-selftest.py [--keep]        exit 0 PASS, 1 FAIL
"""

from __future__ import annotations

import dataclasses
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "init.defaultBranch=main", *args],
        cwd=cwd,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} in {cwd}: {proc.stderr.strip()[:300]}")
    return proc.stdout


def commit(repo: Path, name: str) -> None:
    (repo / name).write_text(f"{name}\n")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name)


def load_predicate():
    spec = importlib.util.spec_from_file_location("check_exit_ready", HERE / "check-exit-ready.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check-exit-ready.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


class Checks:
    def __init__(self) -> None:
        self.total, self.failed = 0, []

    def expect(self, name: str, ok: bool, detail: str = "") -> None:
        self.total += 1
        if not ok:
            self.failed.append(name)
            print(f"  FAIL {name} {detail[:400]}")


def build(root: Path) -> dict[str, Path]:
    remote, work = root / "remote" / "r.git", root / "work"
    remote.parent.mkdir(parents=True)
    work.mkdir()
    git(root, "init", "-q", "--bare", str(remote))
    pushed = work / "pushed"
    pushed.mkdir()
    git(pushed, "init", "-q")
    commit(pushed, "a.txt")
    git(pushed, "remote", "add", "origin", str(remote))
    git(pushed, "push", "-q", "-u", "origin", "main")
    git(pushed, "tag", "v1")
    git(pushed, "push", "-q", "origin", "v1")
    # a linked worktree on its own pushed branch, holding a per-worktree ref (refs/bisect/ is per-worktree)
    linked = work / "pushed-wt"
    git(pushed, "worktree", "add", "-q", "-b", "side", str(linked))
    commit(linked, "b.txt")
    git(linked, "push", "-q", "-u", "origin", "side")
    git(linked, "update-ref", "refs/bisect/good", "HEAD")
    detached = work / "detached"
    git(root, "clone", "-q", str(remote), str(detached))
    git(detached, "checkout", "-q", "--detach", "HEAD")
    moved = work / "moved"
    git(root, "clone", "-q", str(remote), str(moved))
    return {"remote_root": remote.parent, "work": work, "pushed": pushed, "linked": linked, "detached": detached, "moved": moved}


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, env=GIT_ENV, capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL, timeout=900)


def main() -> int:
    keep = "--keep" in sys.argv[1:]
    checks = Checks()
    root = Path(tempfile.mkdtemp(prefix="erase-gate-roundtrip-")).resolve()
    started = time.time()
    try:
        fx = build(root)
        sweep_dir, proof = root / "sweep", root / "proof"
        swept = run(["bash", str(HERE / "git-sweep.sh"), str(sweep_dir), str(fx["work"])])
        checks.expect("the real sweep runs", swept.returncode == 0, swept.stderr)
        checks.expect("the real sweep writes its roots file (§12)", (sweep_dir / "git.roots").is_file())
        proved = run(
            [
                sys.executable,
                str(HERE / "prove-remote-held.py"),
                "--tsv",
                str(sweep_dir / "git.tsv"),
                "--out-dir",
                str(proof),
                "--no-pr-proof",
                "--trust-remote-under",
                str(fx["remote_root"]),
                "--deadline",
                "300",
            ]
        )
        # contract 8: exit 0 only when every repository is PROVEN-ALL with no gap; a path remote always carries the
        # TRUST-REMOTE-UNDER gap, so a complete run over these fixtures exits 1 and still writes every file in full
        checks.expect(
            "the real prover finishes and exits 1, not 0: every proof carries the TRUST-REMOTE-UNDER gap (contract 8)",
            proved.returncode == 1 and all((proof / f).read_text().rstrip("\n").split("\n")[-1].startswith("#END rows=") for f in ("remote-held.tsv", "tips.tsv")),
            proved.stdout[-400:] + proved.stderr[-400:],
        )
        cer = load_predicate()
        held = cer.load_remote_held(proof / "remote-held.tsv")
        ctx = dataclasses.replace(cer.mk_ctx_stub(), remote_held=proof / "remote-held.tsv", now=time.time())
        trust, problems = cer.proof_trust(ctx, held)
        checks.expect("the predicate reads the real remote-held.tsv and tips.tsv without a problem", not problems, str(problems))

        def state(path: Path, run_ctx=ctx):
            # repo_state is built once per predicate run (cached in the run's ctx): a later look needs a new run's ctx
            common = os.path.realpath(git(path, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
            main_checkout = os.path.realpath(git(path, "rev-parse", "--absolute-git-dir").strip()) == common
            return cer.repo_state(run_ctx, str(path), common, main_checkout)

        bound = ("pushed", "linked", "detached", "moved")
        for name in bound:
            why = cer.proof_unbound(trust, str(fx[name]), state(fx[name]))
            checks.expect(
                f"{name}: the label and common dir join; the proof is refused only for its TRUST-REMOTE-UNDER gap (§4)",
                why.startswith("the proof has documented gaps") and "TRUST-REMOTE-UNDER" in why,
                why,
            )
        no_gaps = dataclasses.replace(trust, gaps={})
        offsite = "no remote of this repository resolves"
        for name in bound:
            why = cer.proof_unbound(no_gaps, str(fx[name]), state(fx[name]))
            checks.expect(
                f"{name}: every branch, tag, detached HEAD and per-worktree ref is in the real tips.tsv under the §2 key",
                why.startswith(offsite),
                why,
            )
        commit(fx["moved"], "after-the-proof.txt")
        later = dataclasses.replace(cer.mk_ctx_stub(), remote_held=proof / "remote-held.tsv", now=time.time())
        why = cer.proof_unbound(no_gaps, str(fx["moved"]), state(fx["moved"], later))
        checks.expect("a commit made after the proof unbinds the checkout (moved)", "moved since the proof" in why, why)

        # negative control 1: the round-1 format (short branch names) must not bind
        tips_text = (proof / "tips.tsv").read_text()
        checks.expect("control: the real tips.tsv carries full refnames", "\trefs/heads/main\t" in tips_text)
        short = root / "short"
        short.mkdir()
        shutil.copy2(proof / "remote-held.tsv", short / "remote-held.tsv")
        (short / "tips.tsv").write_text(tips_text.replace("\trefs/heads/", "\t").replace("\trefs/tags/", "\t"))
        short_trust, _ = cer.proof_trust(dataclasses.replace(ctx, remote_held=short / "remote-held.tsv"), held)
        why = cer.proof_unbound(dataclasses.replace(short_trust, gaps={}), str(fx["pushed"]), state(fx["pushed"]))
        checks.expect("control: short branch names (the round-1 prover format) do not bind", "is not in the proof" in why, why)

        # negative control 2: a tips.tsv cut short (no #END row) is refused, never read as complete (§3)
        cut = root / "cut"
        cut.mkdir()
        shutil.copy2(proof / "remote-held.tsv", cut / "remote-held.tsv")
        (cut / "tips.tsv").write_text("".join(ln for ln in tips_text.splitlines(keepends=True) if not ln.startswith("#END")))
        _cut_trust, cut_problems = cer.proof_trust(dataclasses.replace(ctx, remote_held=cut / "remote-held.tsv"), held)
        checks.expect("control: a tips.tsv without its #END row is input-unusable", any(p.code == "input-unusable" for p in cut_problems), str(cut_problems))
    except Exception as exc:  # noqa: BLE001  a crashing fixture is a failed test, reported
        checks.failed.append(f"crashed: {type(exc).__name__}: {exc}")
        print(f"  FAIL crashed: {type(exc).__name__}: {exc}")
    finally:
        if keep:
            print(f"fixtures kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)
    print(f"RESULT: {'PASS' if not checks.failed else 'FAIL'} ({checks.total} checks, {len(checks.failed)} failed, {time.time() - started:.0f}s)")
    return 0 if not checks.failed else 1


if __name__ == "__main__":
    sys.exit(main())
