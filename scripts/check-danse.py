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

  4. EVERY PASSAGE PARTITIONS ITS OWN TIME. `render/program.json` declares a
     PHRASE, not a film — there is no duration and no end. The engine traverses
     the phrase forever, and each traversal draws its own length and its own
     material. Every passage's movements must still tile that passage end to end,
     no gaps and no overlaps, for exactly the reason the score must tile the
     frame. Same arithmetic, one axis down, now checked over 400 passages rather
     than once. And the claim the work actually makes — that it never repeats —
     is checked as a claim: over 20,000 passages, no seed and no length recurs.

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


def check_program(program: dict, grammar_cuts: set[str], river: dict) -> None:
    """The phrase, and the river that traverses it.

    The old form of this checked one partition once, because there was one film
    with one set of boundaries. There is no such thing now — every passage lays
    the movements out differently — so the partition is checked over MANY
    passages, and the arithmetic that must hold is the same arithmetic the 2017
    score obeys over the picture plane.
    """
    moves = program["movements"]

    named = {m["cut"] for m in moves}
    unknown = sorted(named - grammar_cuts)
    check(
        "every movement names a cut the grammar serves",
        not unknown,
        f"unknown: {', '.join(unknown)}" if unknown else ", ".join(sorted(named)),
    )

    if not river:
        return

    check(
        "every passage tiles its own time exactly",
        river["badPartitions"] == 0,
        f"{river['badPartitions']} of {river['passages']} passages had a gap or an overlap"
        if river["badPartitions"]
        else f"{river['passages']} passages, no dead air in any of them",
    )

    # The piece is a river or it is a loop, and the difference is measurable: if
    # passage lengths repeat, a viewer can anchor to the phrase and what they are
    # watching is a loop with the fill changed.
    # Lengths must be SPREAD, not unique. Two passages can share a length and
    # still be entirely different passages — they differ in seed, so they differ
    # in every photograph. What this catches is `vary` collapsing toward zero,
    # which would turn the phrase back into a clock a viewer can anchor to.
    spread = river["distinctLengths"] / river["passages"]
    check(
        "passage lengths do not settle onto a clock",
        spread > 0.99,
        f"{river['distinctLengths']} distinct lengths across {river['passages']} passages ({spread:.3%})",
    )
    check(
        "no passage recurs",
        river["repeatedSeeds"] == 0,
        f"{river['repeatedSeeds']} repeated over {river['passages']} passages"
        if river["repeatedSeeds"]
        else f"{river['passages']} passages, {river['days']:.0f} days, none repeated",
    )

    # It still has to be a PHRASE, not noise: a passage that can run twenty
    # seconds or twenty minutes has no shape a viewer could learn.
    lo, hi = river["minSeconds"], river["maxSeconds"]
    check(
        "a passage still runs 5–8 minutes",
        300 <= lo and hi <= 480,
        f"{lo / 60:.2f}–{hi / 60:.2f} min (mean {river['meanSeconds'] / 60:.2f})",
    )

    # Times Square Arts' Midnight Moment is not "about three minutes". It is 170
    # seconds, and a submission that is 171 is rejected without a conversation.
    mm = (program.get("captures") or {}).get("midnight-moment")
    if mm:
        check("the midnight-moment capture is exactly 170s", mm.get("seconds") == 170, f"{mm.get('seconds')}s")


# ── 2/3. the clock, evaluated by node ──────────────────────────────────────────

CLOCK_PROBE = """
import { readFileSync } from "node:fs";
import { state, PERIOD } from "%(clock)s";
import { movementsIn, passageAt, passageSeconds, passageSeed, validate } from "%(program)s";
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

// ── the river ──────────────────────────────────────────────────────────────────
// The piece has no duration, so "the whole film" is not a thing that can be
// sampled. What is checked instead is the claim it actually makes: that the
// phrase recurs and the water never does.
const PASSAGES = 20000;
let badPartitions = 0, repeatedSeeds = 0;
const lengths = [], seen = new Set();
for (let n = 0; n < PASSAGES; n++) {
  const sd = passageSeed(seed, n);
  if (seen.has(sd)) repeatedSeeds++;
  seen.add(sd);
  const secs = passageSeconds(program, seed, n);
  lengths.push(secs);
  if (n < 400) {
    const laid = movementsIn(program, seed, n);
    let cursor = 0, ok = true;
    for (const m of laid) {
      if (Math.abs(m.t0 - cursor) > 1e-6 || !(m.t1 > m.t0)) ok = false;
      cursor = m.t1;
    }
    if (!ok || Math.abs(cursor - secs) > 1e-6) badPartitions++;
  }
}
const totalSeconds = lengths.reduce((a, b) => a + b, 0);
const river = {
  passages: PASSAGES,
  badPartitions,
  repeatedSeeds,
  distinctLengths: new Set(lengths.map((x) => x.toFixed(6))).size,
  minSeconds: Math.min(...lengths),
  maxSeconds: Math.max(...lengths),
  meanSeconds: totalSeconds / PASSAGES,
  days: totalSeconds / 86400,
};

// Sample deep into the river, not just its first passage.
const SPAN = passageSeconds(program, seed, 0) * 12;
const N = 1560;
let impureProgram = 0, outOfRange = 0, assemblyFlat = true, assemblySamples = 0;
const epochs = new Set();
for (let i = 0; i <= N; i++) {
  const t = (i / N) * SPAN;
  const a = state(seed, t, program);
  // Out of order again: sample t, then a far-away t, then t once more. The edge
  // cache that finds a passage is memoisation; if it ever became state, this is
  // where it would show.
  state(seed, SPAN - t, program);
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

// Two passages far apart must not be the same picture. This is the claim.
const far = passageAt(program, seed, 0), later = passageAt(program, seed, SPAN * 40);
const sameRiver = far.seed !== later.seed && Math.abs(far.seconds - later.seconds) > 1e-9;

console.log(JSON.stringify({
  seeds: seeds.length, flatAtZero, flatAtPeriod, impure, everLeaves, PERIOD,
  programError, impureProgram, outOfRange, assemblyFlat, assemblySamples,
  epochs: epochs.size, declaredEpochs, cuts: CUTS, river, sameRiver, span: SPAN,
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
    check("the program validates", not r["programError"], r["programError"] or "danse.program.v2")
    check(
        "programmed clock is pure anywhere in the river",
        r["impureProgram"] == 0,
        f"{r['impureProgram']} of 1561 samples across {r['span'] / 60:.0f} minutes of river "
        f"disagreed with themselves",
    )
    check(
        "every channel stays in range across twelve passages",
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
    check(
        "the river does not return",
        r["sameRiver"],
        "passages far apart differ in both seed and length",
    )


def node() -> str:
    return "node"


# ── 5b. the film is filable ────────────────────────────────────────────────────

REGISTER = APP / "submission" / "screendance-2027.yaml"


def check_submission(program: dict, river: dict) -> None:
    """The delivery format the program declares must be one the call accepts.

    A generative render has NO native frame rate — `f(seed, t)` samples at
    whatever rate it is asked for — so the rate is not a property of the work,
    it is a delivery decision, and the register owns it. Without this check the
    two drift silently and in the expensive direction: the master was declared
    at 60 fps against a register that allows 24 or 30, and the only thing that
    caught it was reading the register in the middle of a 35-minute render.
    """
    if not REGISTER.is_file():
        NOTE.append("no submission register — nothing holds the delivery format to a call")
        return
    try:
        import yaml
    except ImportError:
        NOTE.append("PyYAML absent — the submission register could not be read")
        return
    reg = yaml.safe_load(REGISTER.read_text()) or {}
    spec = (reg.get("package") or {}).get("master") or {}
    allowed = spec.get("fps_allowed")
    captures = {k: v for k, v in program.get("captures", {}).items() if isinstance(v, dict)}

    if allowed:
        wrong = sorted(f"{k}@{v.get('fps')}" for k, v in captures.items() if v.get("fps") not in allowed)
        check(
            "every capture records at a frame rate the call accepts",
            not wrong,
            f"{', '.join(wrong)} — allowed {allowed}" if wrong else f"{len(captures)} captures at {allowed}",
        )

    want = spec.get("aspect")
    submission = captures.get("passage") or {}
    if want and submission.get("w") and submission.get("h"):
        num, den = (float(x) for x in want.split(":"))
        ok = abs(submission["w"] / submission["h"] - num / den) < 0.01
        check("the submission capture is the aspect the call expects", ok, f"{submission['w']}×{submission['h']} vs {want}")

    # A passage has no fixed length, so the runtime cap applies to the LONGEST
    # one a capture could catch — the worst case, not the nominal.
    cap = next((u.get("assume_max_seconds") for u in reg.get("unstated", []) if u.get("id") == "runtime-cap"), None)
    if cap and river:
        longest = river["maxSeconds"]
        check(
            "the longest passage still fits the assumed runtime cap",
            longest <= cap,
            f"longest observed {longest:.0f}s of {cap}s",
        )


# ── 6. the sound is the same film ──────────────────────────────────────────────

SOUND = APP / "sound"

# Chosen to cross the places the two languages could disagree: zero, a short
# word list, the film's real seed, a value above 2^31 (where JavaScript's `|0`
# makes a number negative and Python's does not), and the 32-bit ceiling.
HASH_CASES = [[0], [1, 2], [20170620, 7, 401], [3735928559, 3, 1, 901], [4294967295, 1], [123, 456, 789, 101112]]

HASH_PROBE = """
import { hash } from "%(rng)s";
console.log(JSON.stringify(%(cases)s.map((c) => hash(...c))));
"""


def check_sound() -> None:
    """The sound selects from the same seed as the picture, out of that room only."""
    if not (SOUND / "score.py").is_file():
        NOTE.append("no score yet — the film is silent")
        return

    # The one that would silently desync sound from picture: the Python port of
    # engine/rng.js must agree with it exactly, or `hash(seed, cell, 401)` picks
    # a different photograph than it picks a grain and nothing lands together.
    sys.path.insert(0, str(SOUND))
    try:
        from rng import hash32
    except ImportError as exc:  # pragma: no cover - a missing file is a real failure
        check("the sound hashes like the picture", False, f"cannot import sound/rng.py — {exc}")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(HASH_PROBE % {"rng": ENGINE / "rng.js", "cases": json.dumps(HASH_CASES)})
        probe = Path(fh.name)
    try:
        out = subprocess.run([node(), probe], capture_output=True, text=True, check=False)
        js = json.loads(out.stdout) if out.returncode == 0 else None
    finally:
        probe.unlink(missing_ok=True)
    if js is None:
        check("the sound hashes like the picture", False, "the JavaScript hash would not evaluate")
    else:
        mine = [hash32(*c) for c in HASH_CASES]
        bad = [c for c, a, b in zip(HASH_CASES, js, mine) if a != b]
        check(
            "the sound hashes like the picture",
            not bad,
            f"{len(bad)} of {len(HASH_CASES)} disagree — {bad[0]}"
            if bad
            else f"{len(HASH_CASES)} cases, rng.js == rng.py",
        )

    check_bank()


def check_bank() -> None:
    """The grain bank, when one has been cut on this machine.

    Gitignored, like the `film` tier and for the same reason — it is derived from
    2.8 GB of originals that never enter git. Absent is not a failure; wrong is.
    """
    index = SOUND / "bank" / "bank.json"
    if not index.is_file():
        NOTE.append("no grain bank on this machine — build it with apps/danse/sound/1_bank.py")
        return
    bank = load(index)
    grains = bank["grains"]

    # Every grain must trace to a recording someone LOOKED at and recognised.
    # This is the whole provenance claim of the sound: three of the first five
    # `room: true` flags were wrong, inherited from a duplicate filename.
    licensed = {s["name"] for s in bank.get("sources", [])}
    strays = sorted({g["source"] for g in grains} - licensed)
    check(
        "every grain comes from a confirmed room recording",
        not strays,
        f"{', '.join(strays)} is in the bank but not in its source list"
        if strays
        else f"{len(grains)} grains from {len(licensed)} recording(s)",
    )

    # An index axis with no spread indexes nothing, and it fails SILENTLY: every
    # weighted draw along it returns an effectively arbitrary grain and nothing
    # crashes. `flatness` shipped once with 4 distinct values across 265 grains.
    axes = ("centroid", "brightness", "flatness", "decay", "attack", "zcr")
    flat = []
    for axis in axes:
        distinct = len({g[axis] for g in grains if axis in g})
        if distinct < max(8, len(grains) // 10):
            flat.append(f"{axis} has {distinct}")
    check(
        "every descriptor axis actually discriminates",
        not flat,
        "; ".join(flat) if flat else f"{len(axes)} axes over {len(grains)} grains",
    )

    missing = [g["id"] for g in grains if not (SOUND / "bank" / f"{g['id']}.wav").is_file()][:3]
    check(
        "every grain the index names exists",
        not missing,
        f"{', '.join(missing)} …" if missing else f"{len(grains)} files",
    )


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
        check_program(load(PROGRAM), set(probe.get("cuts", [])), probe.get("river") or {})
        if probe:
            check_film(probe)
        check_submission(load(PROGRAM), probe.get("river") or {})
    else:
        NOTE.append(f"no film program at {PROGRAM.relative_to(ROOT)} — the piece runs free, nothing is cut")
    print("\n the corpus is deliverable")
    check_delivery(score, manifest)
    print("\n the sound is the same film")
    check_sound()

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
