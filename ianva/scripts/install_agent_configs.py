#!/usr/bin/env python3
"""Apply the generated "point at ianva" entry to every agent's real config.

Reuses ianva.gen.build_entries() so there is exactly ONE source of truth for the entries.
Safety rules (this writes into the user's global configs — a gated, his-hand action):
  * DRY RUN by default. Nothing is written without --apply.
  * Every target file is backed up (file.ianva-bak.<timestamp>) before any change.
  * JSON merges are surgical: only the "ianva" key under mcpServers / mcp is set; all other
    content is preserved. If a JSON/JSONC file can't be parsed, that agent is SKIPPED (never
    corrupted) with a clear message.
  * Idempotent: re-running replaces the ianva entry in place, never duplicates it.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ianva.config import load_config  # noqa: E402
from ianva.gen import Endpoint, build_entries  # noqa: E402
from ianva import creds  # noqa: E402


def _redact(text: str) -> str:
    """Never echo a bearer token to stdout — redact any 'Bearer <tok>' before display."""
    return re.sub(r"(Bearer\s+)\S+", r"\1****", text)


STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")


def backup(path: Path) -> None:
    if path.exists():
        bak = path.with_suffix(path.suffix + f".ianva-bak.{STAMP}")
        shutil.copy2(path, bak)
        print(f"    backed up -> {bak.name}")


def _load_jsonc(text: str):
    """Tolerant JSON/JSONC load: strip /* */ and full-line // comments and trailing commas, then parse.

    Only WHOLE-LINE // comments are stripped — never inline — so a value like "http://host" is
    never corrupted. Trailing-comma removal lets real JSONC (e.g. opencode.jsonc) parse instead of
    being silently skipped."""
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        no_block = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        no_line = re.sub(r"(?m)^\s*//.*$", "", no_block)
        no_trailing = re.sub(r",(\s*[}\]])", r"\1", no_line)
        return json.loads(no_trailing or "{}")


def apply_json(path: Path, top_key: str, entry: dict, apply: bool) -> None:
    print(f"  {path}  (key: {top_key}.ianva)")
    data: dict = {}
    had_comments = False
    if path.exists():
        raw = path.read_text()
        had_comments = bool(re.search(r"(?m)^\s*//", raw) or "/*" in raw)
        try:
            data = _load_jsonc(raw)
        except json.JSONDecodeError:
            print("    SKIP — file isn't parseable JSON/JSONC; leaving it untouched.")
            return
    if not isinstance(data, dict):
        print("    SKIP — top level isn't an object; leaving it untouched.")
        return
    existing = data.get(top_key)
    if not isinstance(existing, dict):
        existing = {}
    if existing.get("ianva") == entry:
        print("    unchanged")
        return
    existing["ianva"] = entry
    data[top_key] = existing
    warn = "  ⚠ comments will be dropped (backup saved)" if had_comments else ""
    if not apply:
        print(f"    would write (dry run){warn}")
        return
    if had_comments:
        print("    ⚠ this file has comments; the rewrite will not preserve them (a backup is saved first).")
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print("    written")


def apply_toml_codex(path: Path, rendered: str, apply: bool) -> None:
    print(f"  {path}  ([mcp_servers.ianva])")
    text = path.read_text() if path.exists() else ""
    if "[mcp_servers.ianva]" in text:
        # idempotent: replace the existing ianva table
        text = re.sub(r"(?ms)^\[mcp_servers\.ianva\].*?(?=^\[|\Z)", "", text).rstrip() + "\n"
    if not apply:
        print("    would append the [mcp_servers.ianva] table (dry run)")
        return
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sep = "" if text.endswith("\n") or not text else "\n"
    path.write_text(text + sep + "\n" + rendered.rstrip() + "\n")
    print("    written")


def apply_claude(rendered: str, apply: bool) -> None:
    print("  claude mcp (via CLI)")
    if not apply:
        print(f"    would run: {_redact(rendered)} (dry run)")
        return
    # idempotent: drop any prior entry, ignore if absent
    subprocess.run(["claude", "mcp", "remove", "--scope", "user", "ianva"], capture_output=True, text=True)
    # shlex.split (not str.split) so a quoted --header "Authorization: Bearer <tok>" stays one arg
    r = subprocess.run(shlex.split(rendered), capture_output=True, text=True)
    print(f"    {'ok' if r.returncode == 0 else 'FAILED'}: {_redact((r.stdout or r.stderr).strip()[:200])}")


def main() -> int:
    ap = argparse.ArgumentParser(description="point every agent at ianva (backup-first, idempotent)")
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry run)")
    ap.add_argument("--only", help="comma-separated agent keys to limit to")
    args = ap.parse_args()

    cfg = load_config()
    ep = Endpoint(**cfg.endpoint_kwargs())
    ep.bearer = creds.bearer_token() or ""  # authenticated gateway → entries carry the header
    only = set(args.only.split(",")) if args.only else None

    mode = "APPLY" if args.apply else "DRY RUN (use --apply to write)"
    print(f"ianva install-agent-configs — {mode}")
    print(f"endpoint: {ep.url()}\n")

    for e in build_entries(ep):
        if only and e.key not in only:
            continue
        print(f"[{e.label}]")
        if e.fmt in {"json_mcpservers", "json_stdio_mcpservers"}:
            if e.payload is None:
                raise RuntimeError(f"{e.key} JSON renderer returned no structured payload")
            apply_json(Path(e.path), "mcpServers", e.payload["mcpServers"]["ianva"], args.apply)
        elif e.fmt == "json_opencode":
            if e.payload is None:
                raise RuntimeError(f"{e.key} JSON renderer returned no structured payload")
            apply_json(Path(e.path), "mcp", e.payload["mcp"]["ianva"], args.apply)
        elif e.fmt == "toml_codex":
            apply_toml_codex(Path(e.path), e.rendered, args.apply)
        elif e.fmt == "claude_cli":
            apply_claude(e.rendered, args.apply)
        print()

    if not args.apply:
        print("Nothing was changed. Re-run with --apply to write (every file is backed up first).")
    else:
        print("Done. Restart each agent (or the daemon) to pick up the new MCP endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
