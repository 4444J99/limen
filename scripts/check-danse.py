#!/usr/bin/env python3
"""danse: the invariants the engine is built on, checked without a GPU.

Three claims carry the piece. Two of them are checkable with arithmetic alone,
and this is where they bind — a plan may record a decision, it may never be its
only home.

  1. PROJECTIVE TEXTURING, NOT PER-PLANE UVs. Every fragment addresses its pixel
     through one shared projector matrix, which only works because the 2017 score
     partitions the frame exactly: no gaps, no overlaps, every tile inside the
     frustum. A hole in that partition is a hole in the room. Checked here.
     (The GPU half — that continuity survives arbitrary geometry — is probe.html.)

  2. THE FLATTENING IS THE CAMERA, NOT `projK`. Corrected from the original plan,
     which had `projK` as the film's spine. At divergence 0 the render is the 2017
     composite no matter how the planes are arranged, so the reveal is a MOVE, not
     a uniform sweep. Checked here as `divergence(seed, 0) == 0` exactly, for many
     seeds, and as the return: the same is true again one PERIOD later.

  3. THE ENGINE IS A PURE f(seed, t). No accumulated state anywhere in engine/.
     Checked here by evaluating the clock twice, out of order, and requiring
     bit-identical output — and by grepping engine/ for the state that would break
     it.

  4. THE PROGRAM PARTITIONS TIME. `render/program.json` declares the film as
     movements. They must tile [0, duration) end to end — no gaps, no overlaps —
     for exactly the reason the score must tile the frame: a hole in the partition
     is a hole in the film, and an offline renderer would render it as one without
     complaining. Same arithmetic, one axis down.

The fifth thing this guards is delivery: every frame the score names must exist
as a plate at every SHIPPED tier, or the flat state renders with holes on a
machine that is not this one — and every frame that is not registered to the 2017
camera must be withheld from generated cuts.

    scripts/check-danse.py            # exit 0 iff all five hold
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "apps" / "danse"
CORPUS = APP / "corpus"
ENGINE = APP / "engine"
PROGRAM = APP / "render" / "program.json"

FAIL: list[str] = []
NOTE: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok  ' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAIL.append(name)


def load(path: Path):
    return json.loads(path.read_text())


# ── 1. the score partitions the frame exactly ──────────────────────────────────


def check_partition(score: dict) -> None:
    w, h = score["target"]["w"], score["target"]["h"]
    cover = bytearray(w * h)
    overlap = 0
    outside = 0

    for tile in score["tiles"]:
        x0, y0, x1, y1 = tile["px"]
        if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
            outside += 1
            continue
        for y in range(y0, y1):
            row = y * w
            for x in range(x0, x1):
                if cover[row + x]:
                    overlap += 1
                cover[row + x] = 1

    gaps = len(cover) - sum(cover)
    check("score covers every pixel", gaps == 0, f"{gaps} uncovered of {w * h}")
    check("score tiles never overlap", overlap == 0, f"{overlap} doubly-covered pixels")
    check("every tile inside the frame", outside == 0, f"{outside} degenerate or out of bounds")

    # The rect form is what the engine actually places; it must agree with px.
    worst = 0.0
    for tile in score["tiles"]:
        px = tile["px"]
        want = [px[0] / w, px[1] / h, px[2] / w, px[3] / h]
        worst = max(worst, max(abs(a - b) for a, b in zip(tile["rect"], want)))
    check("rect agrees with px", worst < 1e-3, f"worst disagreement {worst:.2e}")


# ── 4. the program partitions time ─────────────────────────────────────────────


def check_program(program: dict, grammar_cuts: set[str]) -> None:
    moves = program["movements"]

    cursor = 0.0
    gaps, overlaps = [], []
    for m in moves:
        if m["t0"] > cursor:
            gaps.append(f"{cursor}→{m['t0']}")
        elif m["t0"] < cursor:
            overlaps.append(f"{m['id']} at {m['t0']} < {cursor}")
        cursor = m["t1"]
    check("movements leave no gap", not gaps, ", ".join(gaps) or f"{len(moves)} movements, no dead air")
    check("movements never overlap", not overlaps, ", ".join(overlaps))
    check(
        "movements end exactly at duration",
        cursor == program["duration"],
        f"end {cursor}s vs declared {program['duration']}s",
    )

    named = {m["cut"] for m in moves}
    unknown = sorted(named - grammar_cuts)
    check(
        "every movement names a cut the grammar serves",
        not unknown,
        f"unknown: {', '.join(unknown)}" if unknown else ", ".join(sorted(named)),
    )

    # A window is a crop of the same timeline, never a re-edit. If one runs past
    # the end, the renderer would silently deliver short.
    bad = []
    for name, w in (program.get("windows") or {}).items():
        if name == "_doc":
            continue
        if w["t0"] < 0 or w["t1"] > program["duration"] or w["t1"] <= w["t0"]:
            bad.append(name)
    check("every window lies inside the program", not bad, ", ".join(bad))

    # Times Square Arts' Midnight Moment is not "about three minutes". It is 170
    # seconds, and a submission that is 171 is rejected without a conversation.
    mm = (program.get("windows") or {}).get("midnight-moment")
    if mm:
        span = mm["t1"] - mm["t0"]
        check("midnight-moment is exactly 170s", span == 170, f"{span}s")

    # The one runtime that is graded: the master. 6:20–7:00 clears every cap on
    # the parallel ladder, and 6:30 is the declared target.
    master = (program.get("windows") or {}).get("master")
    if master:
        span = master["t1"] - master["t0"]
        check("master runtime is 6:20–7:00", 380 <= span <= 420, f"{span // 60:.0f}:{span % 60:02.0f}")


# ── 2/3. the clock, evaluated by node ──────────────────────────────────────────

CLOCK_PROBE = """
import { readFileSync } from "node:fs";
import { state, PERIOD } from "%(clock)s";
import { validate } from "%(program)s";
import { CUTS } from "%(grammar)s";

const seeds = [20170620, 1, 2, 7919, 2147483647, 305419896];
let flatAtZero = 0, flatAtPeriod = 0, impure = 0, everLeaves = 0;
for (const s of seeds) {
  if (state(s, 0).divergence === 0) flatAtZero++;
  if (state(s, PERIOD).divergence === 0) flatAtPeriod++;
  // Out of order on purpose: a stateful clock gives a different answer the
  // second time, and evaluating t ascending would hide exactly that.
  const late = state(s, 37.25), early = state(s, 3.5), lateAgain = state(s, 37.25);
  if (JSON.stringify(late) !== JSON.stringify(lateAgain)) impure++;
  if (early.divergence >= 0 && late.divergence > 0) everLeaves++;
}

// ── the programmed clock ───────────────────────────────────────────────────────
const program = JSON.parse(readFileSync("%(programJson)s", "utf8"));
let programError = null;
try { validate(program); } catch (e) { programError = e.message; }

const seed = program.seed;
const N = 1560;                       // every quarter-second of the 6:30
let impureProgram = 0, outOfRange = 0, assemblyFlat = true, assemblySamples = 0;
const epochs = new Set();
for (let i = 0; i <= N; i++) {
  const t = (i / N) * program.duration;
  const a = state(seed, t, program);
  // Out of order again: sample t, then a far-away t, then t once more.
  state(seed, program.duration - t, program);
  const b = state(seed, t, program);
  if (JSON.stringify(a) !== JSON.stringify(b)) impureProgram++;
  const ok =
    a.divergence >= -1e-9 && a.divergence <= 1 &&
    a.spread >= -1e-9 && a.spread <= 1 &&
    a.projK >= -1e-9 && a.projK <= 1 &&
    a.turnover >= -1e-9 &&
    Math.abs(a.azimuth) <= 1.5 && Math.abs(a.elevation) <= 1;
  if (!ok) outOfRange++;
  // The 2017 composite is only a reproduction while the camera is exactly on
  // axis. If ASSEMBLY drifts off zero at all, what the film shows is a homage.
  if (a.movement === "ASSEMBLY") {
    assemblySamples++;
    if (a.divergence !== 0 || a.spread !== 0) assemblyFlat = false;
  }
  if (a.movement === "RESEED") epochs.add(a.epoch);
}
const reseedMovement = program.movements.find((m) => m.id === "RESEED");
const declaredEpochs = (reseedMovement?.reseeds ?? []).length;

console.log(JSON.stringify({
  seeds: seeds.length, flatAtZero, flatAtPeriod, impure, everLeaves, PERIOD,
  programError, impureProgram, outOfRange, assemblyFlat, assemblySamples,
  epochs: epochs.size, declaredEpochs, cuts: CUTS,
}));
"""


def check_clock() -> dict:
    # A real file, not stdin: node resolves the module's relative imports against
    # the script's own path. In a worktree `.git` is a file, so it cannot go there.
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(
            CLOCK_PROBE
            % {
                "clock": ENGINE / "clock.js",
                "program": ENGINE / "program.js",
                "grammar": ENGINE / "grammar.js",
                "programJson": PROGRAM,
            }
        )
        probe = Path(fh.name)
    try:
        out = subprocess.run([node(), probe], capture_output=True, text=True, check=False)
        if out.returncode != 0:
            check("clock evaluates", False, out.stderr.strip().splitlines()[-1] if out.stderr else "node failed")
            return {}
        r = json.loads(out.stdout)
    finally:
        probe.unlink(missing_ok=True)

    check("flat at t=0 for every seed", r["flatAtZero"] == r["seeds"], f"{r['flatAtZero']}/{r['seeds']}")
    check(
        "flat again one period later",
        r["flatAtPeriod"] == r["seeds"],
        f"{r['flatAtPeriod']}/{r['seeds']} at t={r['PERIOD']}s",
    )
    check("the room does open", r["everLeaves"] == r["seeds"], f"{r['everLeaves']}/{r['seeds']}")
    check("clock is pure — same t, same state", r["impure"] == 0, f"{r['impure']} seeds disagreed with themselves")
    return r


def check_film(r: dict) -> None:
    """The programmed clock: the same purity, held to the film's declared arc."""
    check("the program validates", not r["programError"], r["programError"] or "danse.program.v1")
    check(
        "programmed clock is pure across the whole film",
        r["impureProgram"] == 0,
        f"{r['impureProgram']} of 1561 quarter-seconds disagreed with themselves",
    )
    check(
        "every channel stays in range for 6:30",
        r["outOfRange"] == 0,
        f"{r['outOfRange']} samples out of range",
    )
    check(
        "ASSEMBLY holds the camera exactly on axis",
        r["assemblyFlat"] and r["assemblySamples"] > 0,
        f"{r['assemblySamples']} samples at divergence 0 — the composite is reproduced, not evoked",
    )
    check(
        "RESEED restarts as many times as it declares",
        r["epochs"] == r["declaredEpochs"],
        f"{r['epochs']} epochs observed, {r['declaredEpochs']} declared",
    )


def node() -> str:
    return "node"


# The three things that would make f(seed, t) a lie. `performance.now` and
# `Date.now` make the render depend on when it ran; `requestAnimationFrame` inside
# engine/ would put a loop where a function belongs.
FORBIDDEN = (
    (re.compile(r"\brequestAnimationFrame\b"), "requestAnimationFrame"),
    (re.compile(r"\bDate\.now\b"), "Date.now"),
    (re.compile(r"\bperformance\.now\b"), "performance.now"),
    (re.compile(r"\bMath\.random\b"), "Math.random"),
)


def check_purity() -> None:
    hits = []
    for js in sorted(ENGINE.glob("*.js")):
        text = js.read_text()
        for rx, label in FORBIDDEN:
            if rx.search(text):
                hits.append(f"{js.name}:{label}")
    check("no wall-clock or entropy inside engine/", not hits, ", ".join(hits))


# ── 4. every frame the score names is deliverable ──────────────────────────────


def check_delivery(score: dict, manifest: dict) -> None:
    ids = {f["id"] for f in manifest["frames"]}
    named = {Path(layer["src"]).stem for tile in score["tiles"] for layer in tile["layers"]}
    check("every scored frame is in the manifest", named <= ids, f"missing {sorted(named - ids)[:4]}")

    # A `local` tier (the 3264px film plates) exists only on the machine that
    # built it and is gitignored on purpose. Requiring it here would fail every
    # checkout that has not rendered a film.
    shipped = [name for name, spec in manifest["tiers"].items() if not spec.get("local")]
    missing = []
    for tier in shipped:
        for fid in sorted(named):
            if not (CORPUS / "plates" / tier / f"{fid}.webp").is_file():
                missing.append(f"{tier}/{fid}")
    check(
        "every scored frame has a plate at every shipped tier",
        not missing,
        f"{len(missing)} missing, e.g. {missing[:3]}" if missing else f"tiers: {', '.join(shipped)}",
    )

    room = CORPUS / manifest["room"]["file"]
    check("the recovered room plate ships", room.is_file(), str(room.relative_to(ROOT)))

    # Projective texturing addresses every fragment through the 2017 camera's
    # matrix. A frame shot on anything else is registered to nothing — it may
    # appear in the solved score, because the 2017 cut genuinely used one, but a
    # generated cut reaching for it would sample a photograph of a phone screen
    # as though it were the room.
    declared = [f for f in manifest["frames"] if "registered" in f]
    total = len(manifest["frames"])
    check(
        "every frame declares whether it is registered to the 2017 camera",
        len(declared) == total,
        f"{len(declared)}/{total}" + ("" if len(declared) == total else " — rebuild with pipeline/4_corpus.py"),
    )
    strangers = [f["id"] for f in manifest["frames"] if f.get("registered") is False]
    orphans = [fid for fid in strangers if fid not in named]
    check(
        "unregistered frames are only ever there because the 2017 cut used them",
        not orphans,
        f"{', '.join(orphans)} is unregistered AND unused — drop it"
        if orphans
        else (f"{', '.join(strangers)} — in the score, withheld from generated cuts" if strangers else "none"),
    )


def main() -> int:
    if not (CORPUS / "score-2017.json").is_file():
        print("no corpus — run apps/danse/pipeline/4_corpus.py first", file=sys.stderr)
        return 1
    score = load(CORPUS / "score-2017.json")
    manifest = load(CORPUS / "manifest.json")

    print("danse invariants\n")
    print(" the score partitions the frame")
    check_partition(score)
    print("\n the clock is a pure f(seed, t) that returns to flat")
    probe = check_clock()
    check_purity()
    if PROGRAM.is_file():
        print("\n the program partitions time")
        check_program(load(PROGRAM), set(probe.get("cuts", [])))
        if probe:
            check_film(probe)
    else:
        NOTE.append(f"no film program at {PROGRAM.relative_to(ROOT)} — the piece runs free, nothing is cut")
    print("\n the corpus is deliverable")
    check_delivery(score, manifest)

    for n in NOTE:
        print(f"\n  note: {n}")

    print()
    if FAIL:
        print(f"danse: {len(FAIL)} invariant(s) broken — {', '.join(FAIL)}")
        return 1
    print("danse: every invariant holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
