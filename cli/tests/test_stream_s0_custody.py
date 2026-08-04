"""s0-corpus-custody's settlement predicate — proves the domain done, not merely that a checker is green.

This is the `predicate_command` for exactly one stream. It exists because the registry's shared
predicates cannot settle anything: `check-corpora.py` is s0's, but `check-convergence.py` serves
s3/s6/s7 and `check-atom-homing.py` serves s1/s2, so a green run there says "some axis is healthy",
never "THIS domain is done" (check J refuses such a command).

s0's mission was three items. Each is asserted here against declared data and the real checker, so
settlement is a proof rather than an assertion:

  1. the store is addressable through declared data          -> institutio/governance/custody.yaml
  2. an unresolvable root is RED, degrading to declared data -> check-corpora.py's UNACCOUNTED rule
  3. a reclaim verb a cold session can execute               -> scripts/arca.sh restore

Deliberately store-free: the corpus is archived off-host and absent in CI, so every assertion reads
declared data or source, never the filesystem of a runner. A test that only passed where the drive
is mounted would be the "vacuously true on a runner" failure item 2 itself warns about.
"""

import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CUSTODY = ROOT / "institutio" / "governance" / "custody.yaml"
CORPORA_CHECK = ROOT / "scripts" / "check-corpora.py"
ARCA = ROOT / "scripts" / "arca.sh"
STORE = "conversations-private"


def _roots():
    return (yaml.safe_load(CUSTODY.read_text()) or {}).get("roots") or {}


# ── item 1: addressable through declared data ──────────────────────────────────────


def test_the_evacuated_store_has_a_custody_record():
    """The defect s0 named was a public registry pointing at a path nobody could open.

    The fix is NOT a custody field in corpora.yaml — that would be the second source of truth
    check-corpora.py's check D forbids. custody.yaml owns the record and points BACK at corpora.yaml.
    """
    root = _roots().get(STORE)
    assert root, f"custody.yaml declares no root for {STORE}"
    assert root.get("class") == "archive", f"{STORE} is not declared archived: {root.get('class')!r}"
    assert root.get("vault"), f"{STORE} names no vault to reclaim from"
    assert root.get("custody_label"), f"{STORE} carries no custody label to resolve receipts by"


def test_the_custody_record_points_back_at_the_public_registry():
    """`referenced_by` is what keeps the two registries from drifting into disagreement."""
    refs = _roots().get(STORE, {}).get("referenced_by") or []
    assert any("corpora.yaml" in str(r) for r in refs), (
        f"{STORE}'s custody record does not reference corpora.yaml — the link that makes the public "
        f"registry's unresolvable root explainable rather than merely broken. Got: {refs}"
    )


# ── item 2: an unresolvable root is RED, on declared data ──────────────────────────


def test_an_unaccounted_root_fails_rather_than_being_advisory():
    """The precise claim s0 was filed over: check-corpora.py 'never asserted a root RESOLVES'.

    Asserted against source, not by mutating the registry: UNACCOUNTED must reach `fail`, while
    ARCHIVED degrades to an advisory. Both halves matter — failing on ARCHIVED would make a
    correctly-evacuated store red forever, and advising on UNACCOUNTED is the original bug.
    """
    src = CORPORA_CHECK.read_text()
    assert "reference_state.UNACCOUNTED" in src, "check-corpora.py no longer consults the resolver"
    unaccounted = src.index("reference_state.UNACCOUNTED")
    archived = src.index("reference_state.ARCHIVED")
    window = src[unaccounted:archived]
    assert 'fail("B"' in window, "an UNACCOUNTED root no longer FAILS — this is the s0 defect returning"


def test_the_verdict_is_declared_data_not_a_filesystem_probe(tmp_path: Path):
    """Must run store-free in CI. If the verdict came from a disk probe it would be vacuously true
    on every runner, which is exactly what s0's mission item 2 prohibited."""
    isolated_home = tmp_path / "ci-home"
    isolated_home.mkdir()
    proc = subprocess.run(
        [sys.executable, str(CORPORA_CHECK)],
        cwd=ROOT,
        env={
            **os.environ,
            "HOME": str(isolated_home),
            # Changing HOME must not hide dependencies installed in this interpreter's
            # original user site-packages (the portable macOS verifier uses that layout).
            "PYTHONPATH": os.pathsep.join(path for path in sys.path if path),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "archived off-host" in proc.stdout, (
        "check-corpora.py no longer reports the store as archived from its receipts — "
        "the verdict must come from declared custody data, not from whether a drive is mounted"
    )


# ── item 3: a reclaim verb a cold session can execute ──────────────────────────────


def test_a_reclaim_verb_exists_and_is_documented():
    """Asserted against SOURCE, never by invoking arca.sh.

    Nothing here may execute that script. Its verbs act on the real private estate — `backup` sweeps
    every ~/Workspace/_*-private store, encrypts it, and pushes ciphertext — so a settlement probe
    that ran it would be exactly the side-effecting predicate the argv guard exists to prevent.
    (Whether a BARE invocation is safe is a separate defect with its own fix and its own test in
    cli/tests/test_arca_usage.py; it is not this domain's to prove.)
    """
    src = ARCA.read_text()
    assert "restore)" in src, "arca.sh no longer dispatches a restore verb"
    assert "arca.sh restore <store>" in src, "the restore verb is undocumented — a cold session cannot find it"
