"""The constellation PEOPLE are the operator's session streams — derived, never authored.

THE DEFECT THESE TESTS PIN — twice over. The operator's workstreams — collaborator domains, tiers
he accepted 2026-07-22 — live in organs/consulting/constellation/registry.yaml. The session-stream
registry was authored FRESH on 2026-07-29 without them ("what streams do I open?" answered with
internal governance plumbing); the first repair then derived from the right register at the WRONG
GRANULARITY — one stream per project, so "open my streams" opened three sibling sessions all
inside one person's domain (corrected 2026-07-30; the operator's own count "6-10" is the T1/T2
people count). The repair is derivation at the person unit: derive-streams.py projects one
`family: constellation` row + one cartridge per T1/T2 PERSON, every lane inside that cartridge,
and check M holds the projection to the register on every pr-gate.

What must stay true, in order of how expensive it was to learn:
  * ONE stream per person — a multi-project person is one row, never sibling rows;
  * a cartridge whose stream no longer derives is removed by the generator, not left to rot;
  * the derived rows/cartridges cannot drift from the register in EITHER direction;
  * T3 (protocol-first, operator's decision) never grows a launch surface;
  * T1 outranks T2 in the ready set — the launcher's RAM bound opens the FIRST N rows,
    so order is priority, not cosmetics;
  * a lane never settles by trailer — one `Settles: styx` landing would delete a recurring
    lane from the launcher forever while the register still lists it T1;
  * nothing this generator writes can carry contact data into the public tree.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DERIVE = ROOT / "organs" / "consulting" / "constellation" / "derive-streams.py"
CHECK = ROOT / "scripts" / "check-session-streams.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load(DERIVE, "derive_streams")
M = _load(CHECK, "check_session_streams_for_constellation")


# ── a synthetic register: stable against future edits to the real one ───────────────

REGISTER = """\
version: constellation.v1
owner: consulting
people:
  - slug: ada
    tier: T1
    engagement_ref: null
    funnel_instance_ref: null
    projects:
      - name: analytical-engine
        repo: organvm/analytical-engine
        related_repos: [organvm/analytical-engine-notes]
        keywords: [engine, difference]
        stage: building
        public_face_state: readme
        dossier: null
  - slug: grace
    tier: T2
    engagement_ref: null
    funnel_instance_ref: null
    projects:
      - name: compiler-lane
        repo: null
        keywords: [compiler, cobol]
        stage: idea
        public_face_state: none
        dossier: null
  - slug: linus
    tier: T3
    engagement_ref: null
    funnel_instance_ref: null
    projects:
      - name: kernel-lane
        repo: null
        keywords: [kernel]
        stage: idea
        public_face_state: none
        dossier: null
"""

STREAMS_MINIMAL = "schema_version: 0.1\n\nstreams:\n"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "organs/consulting/constellation").mkdir(parents=True)
    (tmp_path / "institutio/governance").mkdir(parents=True)
    (tmp_path / "docs/continuations").mkdir(parents=True)
    (tmp_path / G.REGISTER_REL).write_text(REGISTER)
    (tmp_path / G.STREAMS_REL).write_text(STREAMS_MINIMAL)
    return tmp_path


def _run(mode, root):
    return subprocess.run(
        [sys.executable, str(DERIVE), mode, "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


# ── derivation scope ─────────────────────────────────────────────────────────────────


def test_t3_never_grows_a_launch_surface(root):
    """Protocol-first is the operator's decision recorded in the register; a launch cartridge for
    a T3 domain would contradict the data it derives from."""
    assert _run("--write", root).returncode == 0
    streams = (root / G.STREAMS_REL).read_text()
    assert "  ada:" in streams
    assert "  grace:" in streams
    assert "  linus:" not in streams
    assert not (root / "docs/continuations/linus").exists()


def test_one_stream_per_person_never_per_project(root):
    """THE 2026-07-30 CORRECTION. A person with several projects is ONE domain row whose single
    cartridge carries every lane — never sibling rows that fragment the domain into per-repo
    sessions (rob's four repos opened as four sessions is the incident this pins)."""
    reg = root / G.REGISTER_REL
    reg.write_text(
        reg.read_text().replace(
            "  - slug: grace",
            """\
      - name: second-lane
        repo: organvm/second-lane
        keywords: [second]
        stage: idea
        public_face_state: none
        dossier: null
  - slug: grace""",
        )
    )
    assert _run("--write", root).returncode == 0
    streams = (root / G.STREAMS_REL).read_text()
    assert streams.count("  ada:") == 1
    assert "  analytical-engine:" not in streams
    assert "  second-lane:" not in streams
    cart = (root / "docs/continuations/ada/intent.md").read_text()
    assert "### analytical-engine" in cart
    assert "### second-lane" in cart
    # runway is the longest lane's: idea (1d) dominates building (1d) — and a register moving
    # every lane to a short stage shortens the domain with it.
    assert "runway: 1d" in streams


def test_stale_generated_cartridge_is_removed_but_hand_authored_kept(root):
    """A cartridge whose stream no longer derives (the old per-project ones) is generator debt;
    leaving it on disk re-creates the two-registries defect one directory over. Hand-authored
    cartridges (no GENERATED mark) are never the generator's to touch."""
    assert _run("--write", root).returncode == 0
    stale = root / "docs/continuations/analytical-engine/intent.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"<!-- {G.GENERATED_MARK} -->\n# analytical-engine — ada's lane\n")
    hand = root / "docs/continuations/s0-something/intent.md"
    hand.parent.mkdir(parents=True)
    hand.write_text("# s0-something — hand-authored governance cartridge\n")
    check = _run("--check", root)
    assert check.returncode == 1, check.stdout
    assert _run("--write", root).returncode == 0
    assert not stale.exists()
    assert not stale.parent.exists()
    assert hand.exists()
    assert _run("--check", root).returncode == 0


def test_rows_carry_family_and_register_tier(root):
    _run("--write", root)
    streams = (root / G.STREAMS_REL).read_text()
    assert streams.count("family: constellation") == 2
    assert "register_tier: T1" in streams
    assert "register_tier: T2" in streams


# ── parity: the property check M enforces on every pr-gate ──────────────────────────


def test_write_then_check_is_parity(root):
    assert _run("--write", root).returncode == 0
    check = _run("--check", root)
    assert check.returncode == 0, check.stdout + check.stderr


def test_a_hand_edited_derived_row_is_drift(root):
    """THE REGRESSION. Hand-editing a projection must be a red check, or the register and the
    launcher quietly diverge — which is exactly the two-registries defect this closes."""
    _run("--write", root)
    streams_path = root / G.STREAMS_REL
    streams_path.write_text(streams_path.read_text().replace("runway: 1d", "runway: 7d", 1))
    check = _run("--check", root)
    assert check.returncode == 1
    assert "DRIFT" in check.stdout


def test_a_register_edit_unmatched_by_regeneration_is_drift_too(root):
    """Drift is bidirectional: the register moving while the projection stands still is the same
    defect as the projection being hand-edited."""
    _run("--write", root)
    reg = root / G.REGISTER_REL
    reg.write_text(reg.read_text().replace("stage: building", "stage: mvp"))
    assert _run("--check", root).returncode == 1
    assert _run("--write", root).returncode == 0
    assert _run("--check", root).returncode == 0
    # stage mvp ⇒ runway 8h, per RUNWAY_BY_STAGE — the projection followed the register.
    assert "runway: 8h" in (root / G.STREAMS_REL).read_text()


def test_operator_notes_survive_regeneration(root):
    _run("--write", root)
    cart = root / "docs/continuations/ada/intent.md"
    text = cart.read_text()
    assert G.NOTES_BEGIN in text
    cart.write_text(text.replace(G.NOTES_BEGIN, G.NOTES_BEGIN + "\nada prefers loud failures.", 1))
    reg = root / G.REGISTER_REL
    reg.write_text(reg.read_text().replace("stage: building", "stage: mvp"))
    _run("--write", root)
    regenerated = cart.read_text()
    assert "ada prefers loud failures." in regenerated
    assert "mvp" in regenerated


# ── the leak guard: nothing here may carry contact data into the public tree ────────


@pytest.mark.parametrize(
    "leak",
    [
        "reach her at ada.lovelace@example.com",
        "call 212-555-0143 for details",
        "she posts as @adalovelace",
    ],
)
def test_contact_data_is_refused_not_written(root, leak):
    reg = root / G.REGISTER_REL
    reg.write_text(reg.read_text().replace("stage: building", f"stage: building\n        notes: {leak}"))
    proc = _run("--write", root)
    assert proc.returncode == 1
    assert "REFUSING" in proc.stderr
    # And nothing was half-written before the refusal.
    assert "streams:" in (root / G.STREAMS_REL).read_text()
    assert not (root / "docs/continuations/ada").exists()


def test_dates_and_shas_do_not_false_positive_the_leak_guard():
    for benign in ("operator-accepted 2026-07-22", "commit 3e0d16929af", "runway 8h at 16:30"):
        for _label, pat in G.LEAK_PATTERNS:
            assert not pat.search(benign), (benign, pat.pattern)


# ── ordering and settlement semantics in the checker ─────────────────────────────────


def test_t1_outranks_t2_outranks_governance_in_the_ready_order():
    rows = [
        ("zeta-lane", {"family": "constellation", "register_tier": "T2"}),
        ("s0-something", {"family": "governance"}),
        ("alpha-lane", {"family": "constellation", "register_tier": "T2"}),
        ("omega-lane", {"family": "constellation", "register_tier": "T1"}),
    ]
    assert [sid for sid, _ in M._family_order(rows)] == [
        "omega-lane",
        "alpha-lane",
        "zeta-lane",
        "s0-something",
    ]


def test_a_constellation_lane_never_settles_by_trailer():
    """A lane is recurring work; its lifecycle is the register's. One `Settles: <lane>` commit
    must not be able to delete it from the launcher while the register still lists it."""
    assert M._settled("styx", {"family": "constellation"}) is False


def test_register_tier_is_refused_on_governance_rows():
    """register_tier orders the ready set, so a hand-authored row carrying it would be
    queue-jumping. Only derived rows (whose bytes check M pins) may say it."""
    proc = subprocess.run(
        [sys.executable, str(CHECK)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout  # the real registry is coherent…
    # …and the rule exists (module-level assertion beats grepping source text: run the check body).
    M.failures.clear()
    fake = {
        "x-lane": {
            "family": "governance",
            "register_tier": "T1",
            "title": "t",
            "branch_prefix": "feat",
            "intent": "docs/continuations/x-lane/intent.md",
            "requires": [],
            "unblocks": [],
            "job_class": "synthesis",
            "predicate": "scripts/check-gates.py",
            "predicate_status": "existing",
            "runway": "8h",
            "owner_of_record": "institutio/governance/gates.yaml",
            "max_children": 2,
            "note": "a fake row exercising the register_tier family guard, nothing more",
        }
    }
    M.run_checks(fake)
    assert any("register_tier is register-derived" in f for f in M.failures)
    M.failures.clear()


# ── the committed state of THIS repo is parity — what check M asserts on pr-gate ────


def test_the_real_derivation_is_current():
    proc = _run("--check", ROOT)
    assert proc.returncode == 0, (
        "committed constellation rows/cartridges have drifted from the register — run "
        "`python3 organs/consulting/constellation/derive-streams.py --write`\n" + proc.stdout
    )
