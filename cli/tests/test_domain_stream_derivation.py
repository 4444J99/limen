"""The operator's LIFE/WORK DOMAINS are session streams — derived from the channel roster.

THE DEFECT THESE TESTS PIN — the third wrong altitude. "What session streams do I open? (~6-10)"
was answered by this registry twice at the wrong level: hand-authored governance phases (s0-s10 —
engineering plumbing), then collaborator lanes (one domain's interior). The operator's 2026-07-30
correction: the streams are LIFE/WORK DOMAINS — email/comms, finance, job applications… — and the
roster has been canonical in code since 2026-07-02 (`limen.workstream.derived_channels()`: meta
process lanes + one channel per organ-ladder.json pillar, the operator's vocabulary as aliases).
The repair is derivation at the DOMAIN unit: derive-domain-streams.py projects one
`family: domain` row + one cartridge per openable channel, ordered by `open_rank` (the launcher's
RAM bound opens the FIRST N rows, so order is priority), and check N holds the projection to the
roster on every pr-gate.

What must stay true, in order of how expensive it was to learn:
  * the SET is the roster — a new organ pillar IS a new domain row with no code edit
    (the "never need him to speak again" property);
  * machinery lanes (prompt-parity, observation, sovereignty) never grow a launch surface;
  * the priority head is the operator-ratified 9; tail domains follow; on-demand meta lanes last;
  * a cartridge whose channel no longer derives is removed by the generator, not left to rot;
  * the derived rows/cartridges cannot drift from the roster in EITHER direction;
  * domain rows outrank constellation (the consulting interior) and governance in the ready set;
  * a domain never settles by trailer — `Settles: correspondence` must not delete a life lane;
  * open_rank is roster-derived: any other family declaring it is hand-written queue-jumping;
  * a channel handle colliding with a foreign family's id is REFUSED, never silently shadowed;
  * nothing this generator writes can carry contact data into the public tree.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DERIVE = ROOT / "institutio" / "governance" / "derive-domain-streams.py"
CHECK = ROOT / "scripts" / "check-session-streams.py"


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


G = _load(DERIVE, "derive_domain_streams")
M = _load(CHECK, "check_session_streams_for_domains")


# ── a synthetic organ ladder: stable against future edits to the real one ────────────
#
# Yields (with the real meta lanes): priority head correspondence/financial/contributions,
# one tail organ (gardening — a pillar the policy has never heard of), one machinery pillar
# (observation — must be excluded), and the on-demand meta lanes.

LADDER = {
    "organs": [
        {"organ": "Treasury", "pillar": "financial", "macro": "money in, debt down"},
        {"organ": "Hortus", "pillar": "gardening", "macro": "grow things"},
        {"organ": "Watch", "pillar": "observation", "macro": "system watching itself"},
    ]
}

STREAMS_MINIMAL = "schema_version: 0.1\n\nstreams:\n"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "institutio/governance").mkdir(parents=True)
    (tmp_path / "docs/continuations").mkdir(parents=True)
    (tmp_path / "organ-ladder.json").write_text(json.dumps(LADDER))
    (tmp_path / G.STREAMS_REL).write_text(STREAMS_MINIMAL)
    return tmp_path


def _run(mode, root):
    return subprocess.run(
        [sys.executable, str(DERIVE), mode, "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


# ── derivation scope and order ───────────────────────────────────────────────────────


def test_machinery_never_grows_a_launch_surface(root):
    """A session never "opens the prompt-parity domain" — process/system lanes are served by the
    beat and the fleet, and a launch cartridge for one would put plumbing back in the answer to
    "what streams do I open?" (the exact defect the domain family closes)."""
    assert _run("--write", root).returncode == 0
    streams = (root / G.STREAMS_REL).read_text()
    for machinery in G.MACHINERY:
        assert f"  {machinery}:" not in streams
        assert not (root / "docs/continuations" / machinery).exists()


def test_priority_head_then_new_pillar_tail_then_on_demand_meta(root):
    """The launch order IS the policy: ratified head (roster ∩ OPEN_PRIORITY), then every organ
    channel the policy has never heard of (a NEW pillar lands with no code edit — the
    never-speak-again property), then the on-demand meta lanes, open_rank 1..N."""
    assert _run("--write", root).returncode == 0
    streams = (root / G.STREAMS_REL).read_text()
    order = [
        line.strip().rstrip(":")
        for line in streams.splitlines()
        if line.startswith("  ") and line.rstrip().endswith(":") and not line.strip().startswith("#")
    ]
    assert order == ["correspondence", "financial", "contributions", "gardening", "conductor", "substrate"]
    for rank, handle in enumerate(order, 1):
        assert f"  {handle}:\n    family: domain\n    open_rank: {rank}\n" in streams
    assert (root / "docs/continuations/gardening/intent.md").exists()


def test_stale_generated_cartridge_is_removed_but_hand_authored_kept(root):
    """A cartridge whose channel no longer derives is generator debt; leaving it on disk
    re-creates the two-registries defect one directory over. Hand-authored cartridges (no
    GENERATED mark — including the constellation family's, which carries a DIFFERENT mark) are
    never this generator's to touch."""
    assert _run("--write", root).returncode == 0
    stale = root / "docs/continuations/gardening-old/intent.md"
    stale.parent.mkdir(parents=True)
    stale.write_text(f"<!-- {G.GENERATED_MARK} -->\n# gardening-old — a channel that left the roster\n")
    hand = root / "docs/continuations/s0-something/intent.md"
    hand.parent.mkdir(parents=True)
    hand.write_text("# s0-something — hand-authored governance cartridge\n")
    foreign = root / "docs/continuations/ada/intent.md"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("<!-- GENERATED by organs/consulting/constellation/derive-streams.py -->\n# ada\n")
    check = _run("--check", root)
    assert check.returncode == 1, check.stdout
    assert _run("--write", root).returncode == 0
    assert not stale.exists()
    assert not stale.parent.exists()
    assert hand.exists()
    assert foreign.exists()
    assert _run("--check", root).returncode == 0


def test_id_collision_with_a_foreign_family_is_refused(root):
    """yaml.safe_load keeps only the LAST duplicate key, so a channel handle colliding with a
    hand-authored (or constellation) row would silently shadow one of them. Refused loudly, with
    nothing half-written."""
    (root / G.STREAMS_REL).write_text(
        STREAMS_MINIMAL + "  financial:\n    family: governance\n    title: an impostor\n"
    )
    proc = _run("--write", root)
    assert proc.returncode == 1
    assert "REFUSING" in proc.stderr
    assert not (root / "docs/continuations/financial").exists()


# ── parity: the property check N enforces on every pr-gate ──────────────────────────


def test_write_then_check_is_parity(root):
    assert _run("--write", root).returncode == 0
    check = _run("--check", root)
    assert check.returncode == 0, check.stdout + check.stderr


def test_a_hand_edited_derived_row_is_drift(root):
    """THE REGRESSION GUARD. Hand-editing a projection must be a red check, or the roster and the
    launcher quietly diverge — the exact two-registries defect this family closes."""
    _run("--write", root)
    streams_path = root / G.STREAMS_REL
    streams_path.write_text(streams_path.read_text().replace("open_rank: 1", "open_rank: 7", 1))
    check = _run("--check", root)
    assert check.returncode == 1
    assert "DRIFT" in check.stdout


def test_a_ladder_edit_unmatched_by_regeneration_is_drift_too(root):
    """Drift is bidirectional: a new organ pillar (= a new domain) appearing in the ladder while
    the projection stands still is the same defect as the projection being hand-edited."""
    _run("--write", root)
    ladder = root / "organ-ladder.json"
    data = json.loads(ladder.read_text())
    data["organs"].append({"organ": "Ludus", "pillar": "play", "macro": "games and rest"})
    ladder.write_text(json.dumps(data))
    assert _run("--check", root).returncode == 1
    assert _run("--write", root).returncode == 0
    assert _run("--check", root).returncode == 0
    assert (root / "docs/continuations/play/intent.md").exists()


def test_operator_notes_survive_regeneration(root):
    _run("--write", root)
    cart = root / "docs/continuations/correspondence/intent.md"
    text = cart.read_text()
    assert G.NOTES_BEGIN in text
    cart.write_text(text.replace(G.NOTES_BEGIN, G.NOTES_BEGIN + "\ntriage before drafting, always.", 1))
    ladder = root / "organ-ladder.json"
    data = json.loads(ladder.read_text())
    data["organs"][0]["macro"] = "money in, debt down, runway up"
    ladder.write_text(json.dumps(data))
    _run("--write", root)
    regenerated = cart.read_text()
    assert "triage before drafting, always." in regenerated
    assert "runway up" in (root / "docs/continuations/financial/intent.md").read_text()


# ── the leak guard: nothing here may carry contact data into the public tree ────────


@pytest.mark.parametrize(
    "leak",
    [
        "reach the treasurer at money@example.com",
        "call 212-555-0143 for balances",
        "posts as @treasuryhandle",
    ],
)
def test_contact_data_is_refused_not_written(root, leak):
    ladder = root / "organ-ladder.json"
    data = json.loads(ladder.read_text())
    data["organs"][0]["macro"] = leak
    ladder.write_text(json.dumps(data))
    proc = _run("--write", root)
    assert proc.returncode == 1
    assert "REFUSING" in proc.stderr
    assert "streams:" in (root / G.STREAMS_REL).read_text()
    assert not (root / "docs/continuations/financial").exists()


def test_dates_and_shas_do_not_false_positive_the_leak_guard():
    for benign in ("ratified 2026-07-30", "commit 558d3828c39", "runway 8h at 16:30"):
        for _label, pat in G.LEAK_PATTERNS:
            assert not pat.search(benign), (benign, pat.pattern)


# ── ordering and settlement semantics in the checker ─────────────────────────────────


def test_domain_outranks_constellation_outranks_governance_in_the_ready_order():
    """The operator's life/work domains are the answer to "what streams do I open?" — the
    collaborator interior and the plumbing follow. Within the domain family, open_rank decides
    (the launcher's RAM bound opens the FIRST N rows), never the alphabet."""
    rows = [
        ("zeta-domain", {"family": "domain", "open_rank": 2}),
        ("s0-something", {"family": "governance"}),
        ("ada", {"family": "constellation", "register_tier": "T1"}),
        ("alpha-domain", {"family": "domain", "open_rank": 1}),
    ]
    assert [sid for sid, _ in M._family_order(rows)] == [
        "alpha-domain",
        "zeta-domain",
        "ada",
        "s0-something",
    ]


def test_a_domain_never_settles_by_trailer():
    """A domain is the operator's recurring life/work lane; its lifecycle is the roster's. One
    `Settles: correspondence` commit must not be able to delete the mail lane from the launcher
    while the roster still derives it."""
    assert M._settled("correspondence", {"family": "domain"}) is False


def test_open_rank_is_refused_on_non_domain_rows():
    """open_rank orders the ready set, so a hand-authored row carrying it would be queue-jumping —
    the same guard register_tier already has, applied to the domain family's ordering word."""
    M.failures.clear()
    fake = {
        "x-lane": {
            "family": "governance",
            "open_rank": 1,
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
            "note": "a fake row exercising the open_rank family guard, nothing more here",
        }
    }
    M.run_checks(fake)
    assert any("open_rank is roster-derived" in f for f in M.failures)
    M.failures.clear()


# ── the committed state of THIS repo is parity — what check N asserts on pr-gate ────


def test_the_real_derivation_is_current():
    proc = _run("--check", ROOT)
    assert proc.returncode == 0, (
        "committed domain rows/cartridges have drifted from the channel roster — run "
        "`python3 institutio/governance/derive-domain-streams.py --write`\n" + proc.stdout
    )


def test_the_real_roster_yields_the_ratified_nine_as_the_priority_head():
    """The operator's count ("somewhere between 6-10") is the priority head — 9 domains, ranks
    1-9, in the ratified order. The tail and meta lanes follow, machinery is absent."""
    records = G.load_channels(ROOT)
    head = [r["handle"] for r in records if r["priority"]]
    assert head == list(G.OPEN_PRIORITY)
    assert 6 <= len(head) <= 10
    handles = {r["handle"] for r in records}
    assert handles.isdisjoint(set(G.MACHINERY))
