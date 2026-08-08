"""The phase receipt must carry what the phase announced.

A separate file from its siblings for the reason test_diurnal_ledger.py states: test_diurnal.py is
organised as a growing tail, so two branches that both append a case conflict textually.

What is under test: emit() built the sidecar with `"scored": ctx.get("scored", [])` hardcoded, but
the midday branch writes its scoring to ctx["midflight"] — so every midday receipt persisted
`claims: []` and `scored: []`, and ctx["drift"] was never written at all. Meanwhile the push
notification, built from ctx["drift"] a few lines earlier in the same function, went out saying
"2 drift".

Measured on the live root: logs/diurnal/2026-08-07-midday.json is 539 bytes with zero claims and
zero scored, byte-for-byte the same empty shell as 2026-08-06's, while the morning receipt beside it
holds 6 claims and docs/diurnal/2026-08-07.md names both drifted claims in prose
("open_levers ... 68 → 73", "open_prs ... 1293 → 1297").

So the information was never lost — it was lost TO MACHINES. A human reading the markdown could
answer "which two?"; a consumer reading the JSON read zero drift out of a run that alerted on two.
That is the quiet failure mode: an empty list is a valid answer, so nothing reports an error. These
cases pin the asymmetry shut.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diurnal.py"
REGISTRY = ROOT / "institutio" / "governance" / "diurnal.yaml"


@pytest.fixture()
def mod():
    spec = importlib.util.spec_from_file_location("diurnal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["diurnal"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "logs" / ".voice").mkdir(parents=True)
    (tmp_path / "logs" / ".voice" / "drain").write_text("")
    (tmp_path / "institutio" / "governance").mkdir(parents=True)
    (tmp_path / "institutio" / "governance" / "diurnal.yaml").write_text(
        REGISTRY.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


def _sidecar(root: Path, phase: str) -> dict:
    paths = sorted((root / "logs" / "diurnal").glob(f"*-{phase}.json"))
    assert paths, f"no {phase} sidecar was written"
    return json.loads(paths[-1].read_text(encoding="utf-8"))


# One drifted claim and one held one. The SCORING is not what is under test here — that is
# test_diurnal_claims.py's job, and reproducing a real `missed` verdict would mean pinning a live
# section's metric into this fixture, which couples these cases to whichever sections happen to
# render a number. Stubbing score_claims isolates the actual defect: emit() persisting the wrong
# ctx key.
#
# The stub returns the fields these cases READ (`text`/`was`/`now` for the drift line, `verdict` for
# the split, `section` to look like a claim) plus `acted_when`, which real claims carry. It is
# deliberately NOT billed as "the exact shape score_claims produces": the real rows are
# `{**claim, now, verdict}` over whatever build_claims emitted — on the live root that includes `id`
# and `metric` — so a comment claiming exactness would itself drift the moment build_claims gains a
# field, which is the same silent-divergence class these cases exist to pin.
_SCORED = [
    {
        "section": "only you",
        "text": "only you: open_levers falls below 68",
        "was": 68,
        "now": 73,
        "verdict": "missed",
        "acted_when": "metric_decreased",
    },
    {
        "section": "organ liveness",
        "text": "organ liveness: not_green falls below 3",
        "was": 3,
        "now": 2,
        "verdict": "held",
        "acted_when": "metric_decreased",
    },
]


# The claims the stubbed scoring is nominally ABOUT. A bare tmp_path root renders no section with a
# live metric, so build_claims legitimately emits nothing there — and a morning with no claims makes
# midday's "which claims was this about?" honestly empty. Stubbing both ends keeps the fixture
# world coherent: real claims in the morning receipt, a scoring of them at midday.
_CLAIMS = [
    {
        "section": "only you",
        "text": "only you: open_levers falls below 68",
        "was": 68,
        "acted_when": "metric_decreased",
    },
    {
        "section": "organ liveness",
        "text": "organ liveness: not_green falls below 3",
        "was": 3,
        "acted_when": "metric_decreased",
    },
]


@pytest.fixture()
def scored(mod, monkeypatch):
    monkeypatch.setattr(mod, "build_claims", lambda *a, **k: list(_CLAIMS))
    monkeypatch.setattr(mod, "score_claims", lambda claims, rendered: list(_SCORED))
    return _SCORED


def test_the_midday_receipt_carries_its_scoring_instead_of_an_empty_list(mod, root, scored):
    """The defect, at the surface that showed it: midday scored claims and recorded none.

    Pre-fix this asserted `[] == 2` — the sidecar read ctx["scored"], which midday never sets.
    """
    assert mod.emit(root, "morning", dry_run=False) == 0
    assert mod.emit(root, "midday", dry_run=False) == 0

    midday = _sidecar(root, "midday")
    assert len(midday["scored"]) == len(scored), "midday scored these claims and persisted an empty list"
    assert midday["claims"], "the receipt must say which claims this phase was about"


def test_midday_records_the_drift_it_announced(mod, root, scored):
    """`drift` is what the notification counts. A receipt that omits it cannot answer 'which two?'."""
    assert mod.emit(root, "morning", dry_run=False) == 0
    assert mod.emit(root, "midday", dry_run=False) == 0

    midday = _sidecar(root, "midday")
    assert "drift" in midday, "midday announced a drift count with no durable record of what drifted"
    # Exactly the `missed` one — a held claim is not drift.
    assert len(midday["drift"]) == 1
    line = midday["drift"][0]
    assert "worsened" in line and "68" in line and "73" in line, f"drift line must stand alone: {line!r}"


def test_the_other_phases_carry_no_drift_key_because_only_midday_derives_one(mod, root, scored):
    """Absence is meaningful here, not missing data — the same discipline `engaged` uses.

    A `drift: []` on a morning row would read as "nothing drifted" when the truth is "this phase
    does not measure drift", which is the exact confusion the ledger's engaged-key comment records.
    """
    assert mod.emit(root, "morning", dry_run=False) == 0
    assert "drift" not in _sidecar(root, "morning")

    assert mod.emit(root, "evening", dry_run=False) == 0
    assert "drift" not in _sidecar(root, "evening")


def test_claims_is_the_same_TYPE_in_every_phase(mod, root, scored, monkeypatch):
    """One key, one type. The first fix for the empty-receipt defect introduced this one.

    The sidecar reconstructed midday's claims from the scored rows as `s["text"]` — plain STRINGS —
    while morning wrote claim DICTS under the identical key (live receipt: `acted_when`, `id`,
    `metric`, `section`, `text`, `was`). Nothing raised, because a list of strings is a perfectly
    valid list.

    It is a trap rather than a cosmetic split: `score_claims()` indexes `c["section"]`, and midday
    consumes the morning receipt through exactly that path. Any consumer that fed a midday receipt
    back the same way — a backfilled phase, an evening reading a midday prior — gets
    `TypeError: string indices must be integers`, at a call site whose inputs look fine.
    """
    real_claims = [{"section": "s1", "text": "t1", "was": 1, "acted_when": "metric_decreased"}]
    monkeypatch.setattr(mod, "build_claims", lambda *a, **k: list(real_claims))

    assert mod.emit(root, "morning", dry_run=False) == 0
    assert mod.emit(root, "midday", dry_run=False) == 0
    assert mod.emit(root, "evening", dry_run=False) == 0

    types = {}
    for phase in ("morning", "midday", "evening"):
        claims = _sidecar(root, phase)["claims"]
        assert claims, f"{phase} receipt recorded no claims"
        types[phase] = type(claims[0]).__name__

    assert set(types.values()) == {"dict"}, f"claims type differs by phase: {types}"


def test_the_evening_receipt_still_carries_its_own_scoring(mod, root, scored):
    """The fix derives the key from the phase; the evening's existing behaviour must not shift."""
    assert mod.emit(root, "morning", dry_run=False) == 0
    assert mod.emit(root, "evening", dry_run=False) == 0

    evening = _sidecar(root, "evening")
    assert len(evening["scored"]) == len(scored), "the evening scores claims and must record that"
