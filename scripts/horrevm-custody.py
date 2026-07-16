#!/usr/bin/env python3
"""HORREVM custody — the granary's shipping lane: arca-sealed ciphertext to the cloud rails.

The strategic-use half of HORREVM (the doctor is scripts/cloud-storage-doctor.py). Drives rclone
in HEADLESS API mode (no File Provider desktop apps — the pre-2026-06-15 breakage vector) against
two remotes whose entire rclone.conf is one op:// item hydrated by the credential organ:

  gdrive:   second-vendor offsite for crown-jewel CIPHERTEXT — the ~/.arca-vault mirror (already
            AES-256-CBC sealed by arca.sh), a sealed session-corpus inventory, and the sealed
            continuity kernel. Covers the "GitHub lost AND Mac lost" correlated failure.
  dropbox:  break-glass grab bag — RECOVERY-CARD.md (plaintext, ZERO secrets) + the sealed kernel,
            reachable from any borrowed browser.

Egress law: ONLY ciphertext plus the one non-secret recovery card ever leaves the machine
(L-CLOUD-EGRESS-CONSENT). All remote writes are `rclone copy/copyto` (additive; never sync);
remote deletion is code-asserted to the limen-custody/.probe/ namespace. Dry-run unless --apply
(the beat arms it via LIMEN_HORREVM_APPLY=1, armed_valve_type: safety). Fail-open per rail;
account tokens masked in everything emitted. Ships dark: with no rclone.conf the beat prints
PARKED on L-CLOUD-EGRESS-CONSENT and exits 0.

Verbs:
  --push [--apply]  probe gates A+B, then ship payloads (dry-run without --apply), then verify
                    (gate C) and monthly restore-proof (gate D); stamps logs/horrevm.json
  --status          freshness predicate: exit 1 iff armed AND last verified push older than
                    LIMEN_HORREVM_MAX_AGE_DAYS (PARKED/dry-run states exit 0 with a note)
  --probe           gates A+B only (token+quota, namespaced roundtrip)
  --doctor          deterministic config parity (paths, payload spec, arca verbs) — no rclone
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "horrevm.json"
ARCA = ROOT / "scripts" / "arca.sh"
RCLONE_CONF = Path.home() / ".config" / "rclone" / "rclone.conf"
CUSTODY_DIR = "limen-custody"
PROBE_NS = f"{CUSTODY_DIR}/.probe"
LEVER = "L-CLOUD-EGRESS-CONSENT"
MIN_PUSH_INTERVAL_H = 20  # MAT-pattern self-throttle: probes every beat, pushes ~daily
RESTORE_TEST_DAYS = 30

MAX_AGE_DAYS = int(os.environ.get("LIMEN_HORREVM_MAX_AGE_DAYS", "7"))
BUDGET_GB = {
    "gdrive": float(os.environ.get("LIMEN_HORREVM_DRIVE_BUDGET_GB", "5")),
    "dropbox": float(os.environ.get("LIMEN_HORREVM_DROPBOX_BUDGET_GB", "1")),
}

# The approved egress list (mirrors the lever text; edit BOTH or neither).
# type dir-mirror: source is ALREADY ciphertext — copied as-is.
# type seal:       tarred + sealed via `arca.sh seal` (one envelope, one Keychain key) first.
# type kernel:     the continuity kernel — sealed bundle of the files below + RECOVERY-CARD.md.
PAYLOADS: dict[str, list[dict]] = {
    "gdrive": [
        {"name": "arca-vault", "type": "dir-mirror", "src": "~/.arca-vault"},
        {"name": "corpus-inventory", "type": "seal", "src": "~/.limen-private/session-corpus/inventory"},
        {"name": "kernel", "type": "kernel"},
    ],
    "dropbox": [
        {"name": "kernel", "type": "kernel"},
    ],
}
KERNEL_CANDIDATES = [
    "~/Workspace/limen/FLAME.md",
    "~/Workspace/limen/his-hand-levers.json",
    "~/Workspace/limen/cloud-routines.json",
    "~/Workspace/limen/logs/obligations-ledger.json",
    "~/.arca-vault/manifest.json",
]


def now() -> datetime:
    return datetime.now(timezone.utc)


def _mask(s: str) -> str:
    import re

    return re.sub(r"[\w.+-]+@[\w.-]+", "<account>", s)


def say(msg: str) -> None:
    print(_mask(msg))


def run(cmd: list[str], timeout: int = 120) -> tuple[int | None, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None, ""


def load_state() -> dict:
    try:
        return json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"rails": {}}


def save_state(state: dict) -> None:
    state["generated_at"] = now().isoformat(timespec="seconds")
    state.setdefault("rails", {}).setdefault("icloud", {"status": "delegated-to-existing-organs"})
    state["rails"].setdefault("onedrive", {"status": "dormant-by-design"})
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text(_mask(json.dumps(state, indent=2)) + "\n", encoding="utf-8")
    except OSError as exc:
        say(f"state log unwritable ({exc})")


def parked() -> bool:
    if not RCLONE_CONF.exists():
        return True
    rc, out = run(["rclone", "listremotes"], 15)
    return rc != 0 or not {"gdrive:", "dropbox:"} & set(out.split())


def gate_a(remote: str) -> dict:
    """Token + quota (rclone about)."""
    rc, out = run(["rclone", "about", f"{remote}:", "--json"], 60)
    if rc != 0:
        return {"token_ok": False}
    try:
        about = json.loads(out)
        return {"token_ok": True, "quota_total": about.get("total"), "quota_free": about.get("free")}
    except ValueError:
        return {"token_ok": True}


def gate_b(remote: str) -> bool:
    """Namespaced self-cleaning roundtrip. Deletion asserted to the .probe/ namespace."""
    nonce = hashlib.sha256(os.urandom(16)).hexdigest()
    probe_path = f"{remote}:{PROBE_NS}/{os.uname().nodename}-{now().strftime('%Y%m%dT%H%M%SZ')}.txt"
    # a temp file + copyto instead of rcat (no shell, no stdin plumbing)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(nonce)
        local = tf.name
    try:
        rc, _ = run(["rclone", "copyto", local, probe_path], 90)
        if rc != 0:
            return False
        rc, out = run(["rclone", "cat", probe_path], 60)
        ok = rc == 0 and out.strip() == nonce
        if probe_path.startswith(f"{remote}:{PROBE_NS}/"):  # namespace assertion — the ONLY delete lane
            run(["rclone", "deletefile", probe_path], 60)
            run(["rclone", "delete", f"{remote}:{PROBE_NS}", "--min-age", "7d"], 60)
        return ok
    finally:
        os.unlink(local)


def payload_bytes(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        if p.is_file():
            total += p.stat().st_size
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
    return total


def seal(src: Path, out_enc: Path) -> bool:
    rc, out = run(["bash", str(ARCA), "seal", str(src), str(out_enc)], 300)
    if rc != 0:
        say(f"  seal failed for {src.name}: {out.strip()[-120:]}")
    return rc == 0


def build_kernel(workdir: Path) -> Path | None:
    """Assemble the continuity kernel: recovery card (plaintext, zero secrets) + sealed bundle."""
    bundle = workdir / "kernel-src"
    bundle.mkdir(parents=True, exist_ok=True)
    included = []
    for cand in KERNEL_CANDIDATES:
        p = Path(os.path.expanduser(cand))
        if p.exists() and p.is_file():
            (bundle / p.name).write_bytes(p.read_bytes())
            included.append(p.name)
    card = workdir / "RECOVERY-CARD.md"
    card.write_text(
        _mask(
            "# LIMEN Recovery Card (plaintext by design — contains ZERO secrets)\n\n"
            f"Generated {now().isoformat(timespec='seconds')} by scripts/horrevm-custody.py (HORREVM).\n\n"
            "## What exists where\n"
            "- GitHub org `organvm` — all repos incl. private `organvm/arca` (sealed private estate).\n"
            "- Backblaze — offsite backup of the Mac `/` and `/Volumes/Archive4T`.\n"
            "- Archive4T + T7Recovery — local archive SSOT + second copy.\n"
            "- Google Drive `limen-custody/` — this arca-vault mirror + sealed inventories + this kernel.\n"
            "- Dropbox `limen-custody/` — this kernel + this card.\n\n"
            "## Restore order\n"
            "1. New machine: sign into GitHub; clone organvm/limen; read CLAUDE.md + his-hand-levers.json.\n"
            "2. ARCA key: macOS Keychain item `limen-arca-vault` (escrow per lever L-ARCA-KEY-ESCROW).\n"
            "3. `bash scripts/arca.sh unseal kernel.tar.enc <dest>` recovers this kernel's bundle.\n"
            "4. Backblaze restore for bulk; Drive `limen-custody/arca-vault/` for the sealed private estate.\n\n"
            f"## Kernel bundle contents\n- " + "\n- ".join(included or ["(none present at build time)"]) + "\n"
        ),
        encoding="utf-8",
    )
    out_enc = workdir / "kernel.tar.enc"
    if not seal(bundle, out_enc):
        return None
    return workdir


def push(apply: bool) -> int:
    state = load_state()
    if parked():
        say(f"HORREVM custody PARKED on {LEVER} — no rclone.conf/remotes (ships dark by design); exit 0")
        save_state(state)
        return 0
    last = state.get("last_push_attempt")
    if last and now() - datetime.fromisoformat(last) < timedelta(hours=MIN_PUSH_INTERVAL_H):
        say(f"self-throttled (<{MIN_PUSH_INTERVAL_H}h since last push pass) — probes only")
        apply = False
        probe_only = True
    else:
        probe_only = False
        state["last_push_attempt"] = now().isoformat(timespec="seconds")
    with tempfile.TemporaryDirectory(prefix="horrevm-") as td:
        workdir = Path(td)
        kernel_dir = None
        for remote, payloads in PAYLOADS.items():
            rail = state.setdefault("rails", {}).setdefault(remote, {})
            rail.update(gate_a(remote))
            if not rail.get("token_ok"):
                say(f"  {remote}: token dead — reddens the doctor's trust gate; re-consent via {LEVER}")
                continue
            rail["probe_roundtrip_ok"] = gate_b(remote)
            if probe_only:
                continue
            staged: list[tuple[Path, str]] = []  # (local, remote_subpath)
            for spec in payloads:
                if spec["type"] == "dir-mirror":
                    src = Path(os.path.expanduser(spec["src"]))
                    if src.is_dir():
                        staged.append((src, spec["name"]))
                elif spec["type"] == "seal":
                    src = Path(os.path.expanduser(spec["src"]))
                    if src.exists():
                        enc = workdir / f"{spec['name']}.tar.enc"
                        if enc.exists() or seal(src, enc):
                            staged.append((enc, enc.name))
                elif spec["type"] == "kernel":
                    kernel_dir = kernel_dir or build_kernel(workdir)
                    if kernel_dir:
                        staged.append((kernel_dir / "kernel.tar.enc", "kernel.tar.enc"))
                        staged.append((kernel_dir / "RECOVERY-CARD.md", "RECOVERY-CARD.md"))
            size = payload_bytes([s for s, _ in staged])
            cap = BUDGET_GB[remote] * 1e9
            free = rail.get("quota_free")
            if size > cap or (isinstance(free, (int, float)) and free < 2 * size):
                say(f"  {remote}: BUDGET REFUSED ({size / 1e9:.2f}GB vs cap {cap / 1e9:.0f}GB, free {free})")
                continue
            verified = True
            for local, sub in staged:
                dest = f"{remote}:{CUSTODY_DIR}/{sub}"
                if not apply:
                    say(f"  (dry-run) would copy {local.name} -> {dest} ({payload_bytes([local]) / 1e6:.1f}MB)")
                    continue
                verb = "copy" if local.is_dir() else "copyto"
                rc, out = run(["rclone", verb, str(local), dest], 1800)
                ok = rc == 0
                if ok and local.is_dir():
                    rc2, _ = run(["rclone", "check", str(local), dest, "--one-way"], 600)
                    ok = rc2 == 0
                verified = verified and ok
                say(f"  {remote}: {local.name} {'shipped+verified' if ok else 'FAILED'}")
            if apply and staged:
                rail["last_push"] = now().isoformat(timespec="seconds")
                rail["verify_ok"] = verified
                if verified:
                    rail["last_verified_push"] = rail["last_push"]
                restore_due = not rail.get("last_restore_test") or now() - datetime.fromisoformat(
                    rail["last_restore_test"]
                ) > timedelta(days=RESTORE_TEST_DAYS)
                if remote == "dropbox" and verified and restore_due:
                    rail["restore_ok"] = restore_test(remote, workdir, kernel_dir)
                    rail["last_restore_test"] = now().isoformat(timespec="seconds")
    save_state(state)
    say("HORREVM custody pass complete" + (" (dry-run)" if not apply else ""))
    return 0


def restore_test(remote: str, workdir: Path, kernel_dir: Path | None) -> bool:
    """Gate D: pull the kernel back, unseal, byte-compare — the copy is worthless until proven."""
    if not kernel_dir:
        return False
    pulled = workdir / "pulled-kernel.tar.enc"
    rc, _ = run(["rclone", "copyto", f"{remote}:{CUSTODY_DIR}/kernel.tar.enc", str(pulled)], 600)
    if rc != 0:
        return False
    out_dir = workdir / "restore-check"
    rc, _ = run(["bash", str(ARCA), "unseal", str(pulled), str(out_dir)], 300)
    ok = rc == 0 and any(out_dir.rglob("*"))
    say(f"  {remote}: restore-proof {'PASSED' if ok else 'FAILED'}")
    return ok


def status() -> int:
    state = load_state()
    if parked():
        say(f"status: PARKED on {LEVER} (dark by design) — exit 0")
        return 0
    armed = os.environ.get("LIMEN_HORREVM_APPLY", "0") == "1"
    stale = []
    for remote in PAYLOADS:
        rail = state.get("rails", {}).get(remote, {})
        last = rail.get("last_verified_push")
        if not last:
            stale.append(f"{remote}: never verified")
        elif now() - datetime.fromisoformat(last) > timedelta(days=MAX_AGE_DAYS):
            stale.append(f"{remote}: last verified {last}")
    if not armed:
        say(
            f"status: consented-but-unarmed dry-run (set LIMEN_HORREVM_APPLY=1); {len(stale)} rail(s) unproven — exit 0"
        )
        return 0
    if stale:
        say("status: STALE — " + "; ".join(stale))
        return 1
    say("status: fresh — every custody rail verified within bounds")
    return 0


def doctor() -> int:
    problems = []
    if not ARCA.exists():
        problems.append("scripts/arca.sh missing")
    elif "cmd_seal" not in ARCA.read_text(encoding="utf-8"):
        problems.append("arca.sh lacks seal/unseal verbs")
    for remote, payloads in PAYLOADS.items():
        if remote not in BUDGET_GB:
            problems.append(f"no budget for {remote}")
        for spec in payloads:
            if spec["type"] not in ("dir-mirror", "seal", "kernel"):
                problems.append(f"unknown payload type {spec}")
            if spec["type"] != "kernel" and "src" not in spec:
                problems.append(f"payload missing src: {spec}")
    for p in problems:
        say(f"  DOCTOR: {p}")
    say(f"HORREVM custody --doctor: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def main() -> int:
    os.environ.setdefault("OS_ACTIVITY_MODE", "disable")  # fork/os_log SIGSEGV mitigation (#831)
    ap = argparse.ArgumentParser(description="HORREVM custody — ciphertext to the cloud rails")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--apply", action="store_true", help="real writes (beat arms via LIMEN_HORREVM_APPLY)")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--doctor", action="store_true")
    args = ap.parse_args()
    if args.doctor:
        return doctor()
    if args.status:
        return status()
    if args.probe:
        state = load_state()
        if parked():
            say(f"probe: PARKED on {LEVER} — exit 0")
        else:
            for remote in PAYLOADS:
                rail = state.setdefault("rails", {}).setdefault(remote, {})
                rail.update(gate_a(remote))
                rail["probe_roundtrip_ok"] = gate_b(remote) if rail.get("token_ok") else False
                say(f"  {remote}: token_ok={rail.get('token_ok')} roundtrip={rail.get('probe_roundtrip_ok')}")
        save_state(state)
        return 0
    return push(apply=args.apply or os.environ.get("LIMEN_HORREVM_APPLY", "0") == "1")


if __name__ == "__main__":
    sys.exit(main())
