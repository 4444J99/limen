#!/usr/bin/env python3
"""Is the ScreenDance package filable? Exit 0 ⟺ yes.

The register (`screendance-2027.yaml`) holds every fact about the call. This holds
none of them — it reads them. That separation is the point: a requirement can only
be wrong in one place, and it announces the date it was last checked.

Three kinds of check, and they fail differently on purpose:

    machine    ffprobe / PIL measure the artifact         PASS | FAIL
    attested   a human asserts it in package/attest.yaml  PASS | FAIL | MISSING
    unstated   the call never said; a phone call closes   OPEN

An OPEN blocking unknown is not a warning. It exits non-zero, because "we assumed
6:30 was fine" is exactly the failure that is only discovered after the deadline.

    ./check.py                        # register-level: deadline + open unknowns
    ./check.py --package .work/submission
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

HERE = Path(__file__).resolve().parent
REGISTER = HERE / "screendance-2027.yaml"

PASS, FAIL, OPEN, SKIP = "PASS", "FAIL", "OPEN", "SKIP"
GLYPH = {PASS: "\033[32m ok \033[0m", FAIL: "\033[31mFAIL\033[0m", OPEN: "\033[33mOPEN\033[0m", SKIP: "skip"}

VIDEO_SUFFIXES = {".mov", ".mp4", ".mxf", ".m4v"}


class Report:
    """Results, and the exit code they imply."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []

    def add(self, section: str, name: str, status: str, detail: str = "") -> None:
        self.rows.append((section, name, status, detail))

    def print(self) -> None:
        section = None
        for sec, name, status, detail in self.rows:
            if sec != section:
                print(f"\n\033[1m{sec}\033[0m")
                section = sec
            print(f"  [{GLYPH[status]}] {name}" + (f" — {detail}" if detail else ""))

    @property
    def failures(self) -> int:
        return sum(1 for _, _, s, _ in self.rows if s in (FAIL, OPEN))


# ── measurement ────────────────────────────────────────────────────────────────


def probe(path: Path) -> dict | None:
    """Video geometry and duration, or None if ffprobe is unavailable."""
    if not shutil.which("ffprobe"):
        return None
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return None
    data = json.loads(out.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    num, _, den = (stream.get("r_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    return {
        "width": stream.get("width"),
        "height": stream.get("height"),
        "fps": round(fps, 3),
        "seconds": float((data.get("format") or {}).get("duration") or 0.0),
    }


def image_size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def words(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="replace").split())


def find_one(root: Path, stem: str) -> Path | None:
    """The single file whose stem matches, of any video extension."""
    hits = [p for p in root.iterdir() if p.is_file() and p.stem == stem and p.suffix.lower() in VIDEO_SUFFIXES]
    return hits[0] if len(hits) == 1 else None


# ── register-level checks (no package needed) ──────────────────────────────────


def check_deadline(reg: dict, rep: Report) -> None:
    d = reg["deadline"]
    wall = datetime.fromisoformat(d["hard_wall"])
    now = datetime.now(ZoneInfo("America/New_York"))
    left = wall - now
    days = left.days + left.seconds / 86400

    if days < 0:
        rep.add("deadline", "hard wall", FAIL, f"passed {abs(days):.1f} days ago ({d['stated']})")
        return
    # The register's wall is already the cautious reading of an ambiguous "EST" on a
    # date when Miami runs EDT. Report against that, never against the stated string.
    rep.add("deadline", "hard wall", PASS, f"{days:.1f} days left → {wall:%a %d %b %H:%M %Z}")

    target = datetime.fromisoformat(d["target_file_date"] + "T12:00:00-04:00")
    tdays = (target - now).days
    status = PASS if tdays >= 0 else OPEN
    rep.add(
        "deadline",
        "target file date",
        status,
        f"{d['target_file_date']} ({tdays:+d} days) — file early; panel sees timestamps",
    )


def check_unknowns(reg: dict, rep: Report) -> None:
    """The call is silent on these. Blocking ones exit non-zero; the rest report
    what stands in for the missing answer — evidence where we found some, a bare
    assumption where we did not — so the two never read alike."""
    for item in reg.get("unstated", []):
        if item.get("blocking", False):
            rep.add("unpublished by the call", item["id"], OPEN, item["resolve"])
            continue
        detail = (
            f"de-blocked by evidence — {item['evidence']}"
            if "evidence" in item
            else f"assuming {item.get('assume', item.get('assume_master', 'default'))}"
        )
        rep.add("unpublished by the call", item["id"], SKIP, detail)


# ── package checks ─────────────────────────────────────────────────────────────


def check_attestations(reg: dict, root: Path, rep: Report) -> None:
    path = root / "attest.yaml"
    attested = yaml.safe_load(path.read_text()) if path.exists() else {}
    attested = attested or {}
    for req in reg["requirements"]:
        if req.get("check") != "manual":
            continue
        value = attested.get(req["id"])
        if value is True:
            rep.add("attested", req["id"], PASS, req["rule"])
        elif value is False:
            rep.add("attested", req["id"], FAIL, req["rule"])
        else:
            rep.add("attested", req["id"], FAIL, f"unattested in attest.yaml — {req['rule']}")


def check_master(spec: dict, reg: dict, root: Path, rep: Report) -> None:
    path = find_one(root, "master")
    if not path:
        rep.add("package", "master", FAIL, "no unique master.<mov|mp4|mxf> in package")
        return
    info = probe(path)
    if not info:
        rep.add("package", "master", OPEN, f"{path.name} present; ffprobe unavailable — cannot verify")
        return

    w, h, fps, secs = info["width"], info["height"], info["fps"], info["seconds"]
    rep.add("package", "master present", PASS, f"{path.name} · {w}×{h} · {fps}fps · {secs / 60:.2f} min")

    ratio = (w / h) if h else 0
    want = 16 / 9
    ok_aspect = abs(ratio - want) < 0.01
    rep.add("package", "aspect 16:9", PASS if ok_aspect else FAIL, f"{ratio:.4f}")

    ok_fps = any(abs(fps - f) < 0.5 for f in spec["fps_allowed"])
    rep.add("package", "frame rate", PASS if ok_fps else FAIL, f"{fps} — allowed {spec['fps_allowed']}")

    cap = next((u.get("assume_max_seconds") for u in reg.get("unstated", []) if u["id"] == "runtime-cap"), None)
    if cap:
        # OPEN, not PASS: the cap is our assumption, not the festival's stated rule.
        status = OPEN if secs > cap else PASS
        rep.add(
            "package",
            "runtime vs assumed cap",
            status,
            f"{secs:.0f}s vs assumed {cap}s — cap is UNCONFIRMED, call {reg['phone']}",
        )


def check_screener(spec: dict, root: Path, rep: Report) -> None:
    path = find_one(root, "screener")
    if not path:
        rep.add("package", "screener", FAIL, "no unique screener.<mov|mp4> in package")
        return
    info = probe(path)
    if not info:
        rep.add("package", "screener", OPEN, f"{path.name} present; ffprobe unavailable")
        return
    ok = (info["height"] or 0) >= spec["min_height"]
    rep.add(
        "package",
        "screener",
        PASS if ok else FAIL,
        f"{path.name} · {info['width']}×{info['height']} (min height {spec['min_height']})",
    )


def check_stills(spec: dict, root: Path, rep: Report, exempt: set[str] = frozenset()) -> None:
    folder = root / "stills"
    if not folder.is_dir():
        rep.add("package", "stills", FAIL, "no stills/ directory")
        return

    pattern = re.compile(spec["filename_pattern"])
    files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith("."))
    named = [p for p in files if pattern.match(p.name)]
    # The origin photograph lives here too and is checked by name elsewhere; it is
    # not a seed still and must not read as a naming violation.
    misnamed = [p.name for p in files if not pattern.match(p.name) and p.name not in exempt]

    ok_count = len(named) >= spec["count_min"]
    rep.add(
        "package",
        "stills count",
        PASS if ok_count else FAIL,
        f"{len(named)} conforming of {len(files)} (min {spec['count_min']})"
        + (f"; misnamed: {', '.join(misnamed[:4])}" if misnamed else ""),
    )

    if spec.get("distinct_seeds"):
        seeds = {p.stem.lower() for p in named}
        ok = len(seeds) == len(named)
        rep.add("package", "stills distinct seeds", PASS if ok else FAIL, f"{len(seeds)} distinct of {len(named)}")

    undersized = []
    unmeasured = 0
    for p in named:
        size = image_size(p)
        if size is None:
            unmeasured += 1
        elif size[0] < spec["min_width"] or size[1] < spec["min_height"]:
            undersized.append(f"{p.name} {size[0]}×{size[1]}")
    if unmeasured:
        rep.add("package", "stills resolution", OPEN, f"{unmeasured} unmeasurable (Pillow missing?)")
    else:
        rep.add(
            "package",
            "stills resolution",
            FAIL if undersized else PASS,
            "; ".join(undersized[:4]) if undersized else f"all ≥ {spec['min_width']}×{spec['min_height']}",
        )


def check_origin_still(spec: dict, root: Path, rep: Report) -> None:
    path = root / "stills" / spec["filename"]
    rep.add(
        "package",
        "unaltered 2017 photograph",
        PASS if path.exists() else FAIL,
        f"stills/{spec['filename']}" + ("" if path.exists() else " — missing"),
    )


def check_trailer(spec: dict, root: Path, rep: Report) -> None:
    path = find_one(root, "trailer")
    if not path:
        rep.add("package", "trailer", SKIP, "optional, not staged")
        return
    info = probe(path)
    if not info:
        rep.add("package", "trailer", OPEN, "present; ffprobe unavailable")
        return
    ok = info["seconds"] <= spec["max_seconds"]
    rep.add("package", "trailer", PASS if ok else FAIL, f"{info['seconds']:.0f}s (max {spec['max_seconds']}s)")


def check_text(spec: dict, root: Path, rep: Report) -> None:
    folder = root / "text"
    for name, rule in spec.items():
        path = folder / f"{name}.txt"
        if not path.exists():
            rep.add("text", name, FAIL if rule.get("required") else SKIP, f"text/{name}.txt missing")
            continue
        n = words(path)
        lo, hi = rule["words_min"], rule["words_max"]
        rep.add("text", name, PASS if lo <= n <= hi else FAIL, f"{n} words (want {lo}–{hi})")


# ── entry ──────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", type=Path, help="staged submission directory")
    ap.add_argument("--register", type=Path, default=REGISTER)
    args = ap.parse_args()

    reg = yaml.safe_load(args.register.read_text())
    rep = Report()

    print(f"\033[1m{reg['call']}\033[0m — {reg['presenter']}")

    check_deadline(reg, rep)
    check_unknowns(reg, rep)

    if args.package:
        root = args.package
        if not root.is_dir():
            rep.add("package", "directory", FAIL, f"{root} does not exist")
        else:
            pkg = reg["package"]
            check_attestations(reg, root, rep)
            check_master(pkg["master"], reg, root, rep)
            check_screener(pkg["screener"], root, rep)
            check_stills(pkg["stills"], root, rep, exempt={pkg["origin_still"]["filename"]})
            check_origin_still(pkg["origin_still"], root, rep)
            check_trailer(pkg["trailer"], root, rep)
            check_text(pkg["text"], root, rep)
    else:
        rep.add("package", "not staged", OPEN, "re-run with --package <dir> once the cut exists")

    rep.print()

    n = rep.failures
    print()
    if n == 0:
        print("\033[32mSUBMITTABLE — every stated requirement met, no open blockers\033[0m")
        return 0
    print(f"\033[31mNOT SUBMITTABLE — {n} item(s) failing or open\033[0m")
    return 1


if __name__ == "__main__":
    sys.exit(main())
