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

The fourth thing this guards is delivery: every frame the score names must exist
as a plate at every tier, or the flat state renders with holes on a machine that
is not this one.

    scripts/check-danse.py            # exit 0 iff all four hold
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


# ── 2/3. the clock, evaluated by node ──────────────────────────────────────────

CLOCK_PROBE = """
import { state, PERIOD } from "%s";
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
console.log(JSON.stringify({ seeds: seeds.length, flatAtZero, flatAtPeriod, impure, everLeaves, PERIOD }));
"""


def check_clock() -> None:
    # A real file, not stdin: node resolves the module's relative imports against
    # the script's own path. In a worktree `.git` is a file, so it cannot go there.
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as fh:
        fh.write(CLOCK_PROBE % (ENGINE / "clock.js"))
        probe = Path(fh.name)
    try:
        out = subprocess.run([node(), probe], capture_output=True, text=True, check=False)
        if out.returncode != 0:
            check("clock evaluates", False, out.stderr.strip().splitlines()[-1] if out.stderr else "node failed")
            return
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

    missing = []
    for tier in manifest["tiers"]:
        for fid in sorted(named):
            if not (CORPUS / "plates" / tier / f"{fid}.webp").is_file():
                missing.append(f"{tier}/{fid}")
    check("every scored frame has a plate at every tier", not missing, f"{len(missing)} missing, e.g. {missing[:3]}")

    room = CORPUS / manifest["room"]["file"]
    check("the recovered room plate ships", room.is_file(), str(room.relative_to(ROOT)))

    # Frames that are not from the locked-off camera break the shared-projector
    # premise. Reported, not failed: one is in the corpus and the 2017 solve used
    # it, so failing here would only make the check unrunnable.
    odd = [f["id"] for f in manifest["frames"] if not f["source"].lower().endswith((".jpg", ".jpeg"))]
    if odd:
        NOTE.append(
            f"{len(odd)} frame(s) not from the camera roll: {', '.join(odd)} "
            f"— projective texturing assumes one 2017 camera; these are not registered to it"
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
    check_clock()
    check_purity()
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
