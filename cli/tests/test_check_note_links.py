"""Contracts for scripts/check-note-links.py — the predicate for citations that point at nothing.

This gate is the generalization of the defect behind ``IF-GATEKEEPER-INERT``: the root cause of
the six-week ``ClaudeCode.app is damaged`` loop lived in ``[[macos-tcc-gatekeeper-dialogs-solved]]``,
cited from five registry surfaces and written nowhere. A citation that resolves and one that
dangles are byte-identical at the call site, so nothing could tell them apart.

These tests build a whole fake repo in ``tmp_path``. Asserting against the live tree would only
prove the gate passes *today*; it would not prove the gate still BITES — and a ratchet that has
stopped biting is indistinguishable from a clean estate, which is precisely the failure this gate
exists to catch.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-note-links.py"


def _mod():
    spec = importlib.util.spec_from_file_location("check_note_links", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _mod()


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    """A real git repo (the scanner reads `git ls-files`, so untracked files are invisible)."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    for rel, body in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


def cite(slug: str) -> str:
    """Build a citation without ever WRITING one in this file's source.

    This gate scans every tracked file — including its own tests. A fixture written literally
    becomes a real dangling citation the moment the file is committed, and the gate fails on
    its own test data.

    Found exactly that way, and only after committing: every green run before then had this
    file still UNTRACKED, so `git ls-files` could not see it and its seven fixture slugs were
    invisible. The gate was correct throughout; the measurement was of a tree that did not yet
    contain the thing being measured. Same shape as the `[[macos-tcc-gatekeeper-dialogs-solved]]`
    defect one level down: what you cannot see, you score green.
    """
    return "[" + "[" + slug + "]" + "]"


# ── the slug grammar: pure, so these can never be flaky ────────────────────────────────


@pytest.mark.parametrize(
    "slug,is_note",
    [
        ("macos-tcc-gatekeeper-dialogs-solved", True),
        ("derive-never-pin", True),
        ("a-b", True),
        # Single-token — deliberately OUT of scope, reported as `unclassified`, never gated.
        ("link", False),
        ("redirects", False),
        # Redaction placeholders in corpus/censor surfaces are not note citations.
        ("PERSON_1", False),
        ("ORG_X", False),
    ],
)
def test_note_slug_grammar(slug, is_note):
    assert bool(M.NOTE_SLUG.match(slug)) is is_note


def test_python_list_of_lists_is_not_a_citation():
    """`HASH_CASES = [[0], [1, 2]]` in check-danse.py is live source, not a knowledge citation.

    A gate that flags real code teaches people to ignore it, which is worse than no gate.
    """
    found = M.CITATION.findall("HASH_CASES = [[0], [1, 2], [20170620, 7, 401]]")
    assert [f for f in found if M.NOTE_SLUG.match(f)] == []


# ── resolution ─────────────────────────────────────────────────────────────────────────


def test_citation_resolves_to_a_file_stem_in_any_directory(tmp_path):
    """How [[macos-tcc-gatekeeper-dialogs-solved]] resolves to docs/architecture/<slug>.md."""
    root = _repo(
        tmp_path,
        {
            "scripts/thing.sh": f"# see {cite('some-real-note')} for the root cause\n",
            "docs/architecture/some-real-note.md": "the note\n",
        },
    )
    scanned = M.scan(root)
    assert "some-real-note" in scanned["resolved"]
    assert scanned["dangling"] == {}


def test_dangling_citation_is_caught_and_names_every_citer(tmp_path):
    """THE HEADLINE. This is the six-week defect, reproduced in miniature."""
    root = _repo(
        tmp_path,
        {
            "scripts/effector.sh": f"# root cause: {cite('written-nowhere')}\n",
            "institutio/governance/sensors.yaml": f"note: see {cite('written-nowhere')}\n",
            "his-hand-levers.json": '{"note": "' + cite("written-nowhere") + '"}\n',
        },
    )
    scanned = M.scan(root)
    assert set(scanned["dangling"]) == {"written-nowhere"}
    # Every citer is named, because "which surfaces believed this?" is the actionable half.
    assert scanned["dangling"]["written-nowhere"] == [
        "his-hand-levers.json",
        "institutio/governance/sensors.yaml",
        "scripts/effector.sh",
    ]


def test_untracked_note_does_not_resolve(tmp_path):
    """A note that exists on disk but is not committed is not a home.

    Rule #2: "on disk" = not done. The next session clones and the note is gone again.
    """
    root = _repo(tmp_path, {"scripts/thing.sh": f"# {cite('local-only-note')}\n"})
    (root / "local-only-note.md").write_text("not added to git\n", encoding="utf-8")
    scanned = M.scan(root)
    assert "local-only-note" in scanned["dangling"]


def test_vendored_and_generated_trees_are_not_scanned(tmp_path):
    """A dangling link in node_modules is not a governance signal about this estate."""
    root = _repo(
        tmp_path,
        {
            "node_modules/pkg/readme.md": f"{cite('vendor-note-nobody-owns')}\n",
            "web/app/out/index.md": f"{cite('generated-note')}\n",
        },
    )
    assert M.scan(root)["cited"] == {}


def test_binary_and_unscanned_suffixes_are_skipped(tmp_path):
    root = _repo(tmp_path, {"assets/blob.bin": f"{cite('not-a-citation-here')}\n"})
    assert M.scan(root)["cited"] == {}


# ── the ratchet ────────────────────────────────────────────────────────────────────────


def test_baselined_slug_passes_and_fresh_one_fails():
    scanned = {"dangling": {"old-debt": ["a.md"], "brand-new": ["b.md"]}}
    split = M.verdict(scanned, ["old-debt"])
    assert split["fresh"] == ["brand-new"]
    assert split["stale"] == []


def test_stale_baseline_line_fails_so_the_ratchet_can_only_shrink():
    """Once the note is written, its baseline line must go.

    Without this, the baseline silently accumulates permission: a slug could be written,
    deleted again, and re-dangle years later with the gate still green.
    """
    scanned = {"dangling": {}}
    split = M.verdict(scanned, ["note-that-now-exists"])
    assert split["stale"] == ["note-that-now-exists"]


def test_verdict_is_pure_and_needs_no_filesystem():
    """`verdict` touches neither git nor disk, so the ratchet half can never be flaky."""
    assert M.verdict({"dangling": {}}, []) == {"fresh": [], "stale": []}


# ── the live estate ────────────────────────────────────────────────────────────────────


def test_live_repo_is_green_at_its_baseline():
    """The shipped state: exit 0, with the 49 pre-existing dangling slugs recorded."""
    out = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "OK — every gated citation resolves" in out.stdout


def test_ratchet_and_ideal_are_different_questions_with_different_exit_codes():
    """The split that check D of check-ideal-forms.py forced, and was right to force.

    Bare = the CI ratchet: "did this change make it worse?" — 0 at the baseline, or it would
    block every PR on inherited debt. ``--ideal`` = IF-NOTE-HOMED's probe: "does the estate cite
    nothing into a void?" — 1 while ANY slug dangles, baselined or not.

    A single exit code cannot answer both. Collapsing them would have published a green ideal
    form over 49 dangling citations, which is the ledger's own named failure: *measuring the
    wrong question is worse than declaring the vacuum*.
    """
    ratchet = subprocess.run([sys.executable, str(CHECK)], capture_output=True, text=True, cwd=str(ROOT), check=False)
    ideal = subprocess.run(
        [sys.executable, str(CHECK), "--ideal"], capture_output=True, text=True, cwd=str(ROOT), check=False
    )
    assert ratchet.returncode == 0, ratchet.stdout
    assert ideal.returncode == 1, ideal.stdout
    assert "distance-remains" in ideal.stdout


def test_ideal_probe_would_go_green_only_on_an_empty_baseline():
    """`at-ideal` has exactly one meaning: nothing dangles. Proven on a repo where none does."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = _repo(
            Path(td),
            {"scripts/x.sh": f"# {cite('a-real-note')}\n", "docs/a-real-note.md": "home\n"},
        )
        scanned = M.scan(root)
        assert scanned["dangling"] == {}
        assert M.verdict(scanned, []) == {"fresh": [], "stale": []}


def test_this_file_introduces_no_citations_of_its_own():
    """The gate scans its own tests, so fixtures must be BUILT (`cite()`), never written literally.

    This is a regression test for a bug that actually shipped into a commit: seven fixture slugs
    were written as literals, and every local run was green because the file was still UNTRACKED
    and `git ls-files` could not see it. The gate was right the whole time — it was measuring a
    tree that did not yet contain the thing being measured.
    """
    scanned = M.scan(ROOT)
    mine = sorted(s for s, citers in scanned["dangling"].items() if any("test_check_note_links" in c for c in citers))
    assert mine == [], f"fixture slugs leaked into the tracked tree as real citations: {mine}"


def test_the_note_this_gate_was_born_from_resolves():
    """IF-GATEKEEPER-INERT's own note must never dangle again — it is the whole reason."""
    scanned = M.scan(ROOT)
    assert "macos-tcc-gatekeeper-dialogs-solved" in scanned["resolved"]
    assert "macos-tcc-gatekeeper-dialogs-solved" not in M.load_baseline(M.BASELINE)
