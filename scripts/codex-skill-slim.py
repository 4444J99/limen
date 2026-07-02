#!/usr/bin/env python3
"""codex-skill-slim.py — distill Codex skill/plugin descriptions to fit the skills budget.

The pain: Codex warns "skill descriptions were shortened to fit the 2% skills context
budget" every session and then mangles descriptions on its own. The session-noise-containment
doctrine (domus-genoma reliquary, Rule 1) BANS the obvious "fix" — disabling plugins/skills —
because that reduces capability to silence noise. And letting the notice ride is rug-sweeping.

The third path (his directive 2026-07-02): make the descriptions THINNER. Keep EVERY skill;
distill each description to a meaning-preserving lead so the total fits the budget and Codex
never has to shorten anything. This is "distillation, not reduction."

DURABILITY: the fat lives in `~/.codex/plugins/cache/**` (marketplace caches) which REVERT on
refresh, so this is a REPAIR organ, not a one-shot edit (containment Rule 6): idempotent, run
every beat, re-distilling anything that reverted to fat. A backup ledger + `--restore` is the
revert guard (Rule 10); `--check` is standing detection (exit 1 when anything is over-cap) so a
reversion surfaces in the beat log — never hidden.

Modes:
  (no flag)   dry-run report — rank every description, show what WOULD be slimmed. Safe.
  --apply     write the distilled descriptions (atomic, validated, backed up first).
  --check     exit 1 if any tracked description exceeds the cap (detection; for the beat/CI).
  --restore   put every original description back from the backup ledger (revert guard).
  --quiet     one summary line instead of per-entry lines (used by the beat).

FAIL-OPEN: no ~/.codex, no config, a torn file — skip it and exit 0 (never break the beat).
Never prints secrets; descriptions are public plugin metadata, but logs stay counts-only under
--quiet. Read-only outside --apply/--restore.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
CACHE = CODEX_HOME / "plugins" / "cache"
LEDGER = CODEX_HOME / ".skill-slim" / "backup.json"
CAP = int(os.environ.get("LIMEN_CODEX_SLIM_CAP") or 240)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# Single-line YAML frontmatter description:  `description: <value>`  (we SKIP block scalars).
_DESC_LINE = re.compile(r"^(description:[ \t]*)(\S.*)$")
# Dangling connectors to trim off a cut tail so it reads as a clean clause, not "…such as".
_TRAIL_WORD = re.compile(r"\s+(?:and|or|the|an?|to|with|for|of|such|as|by|in|on|at|that|when)$", re.I)


def _strip_trailing(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"[\s,;:]+$", "", s)
        s = _TRAIL_WORD.sub("", s)
    return s


def distill(text: str, cap: int = CAP) -> str:
    """Thin `text` under `cap`, preserving the informative lead (title + aliases + purpose).

    Whitespace/paragraphs collapse to single spaces (that is where plugin bloat hides). Whole
    sentences are greedily kept until the next overflows; then any remaining budget is filled with
    the head of the next dropped sentence so the "when to use" routing signal survives. If the
    first sentence alone overflows, hard-cut at a word boundary. Already-thin text is unchanged.
    """
    flat = " ".join(text.split())
    if len(flat) <= cap:
        return text.strip()
    sents = _SENT_SPLIT.split(flat)
    out = ""
    idx = 0
    for i, sentence in enumerate(sents):
        if not out:
            out = sentence
            idx = i + 1
        elif len(out) + 1 + len(sentence) <= cap:
            out += " " + sentence
            idx = i + 1
        else:
            break
    if len(out) > cap:  # first sentence itself too long → cut at a word boundary
        cut = out[:cap]
        i = cut.rfind(" ")
        out = cut[:i] if i > 40 else cut
    elif idx < len(sents):  # room left → keep the head of the next sentence (the purpose lead)
        remaining = cap - len(out) - 1
        if remaining > 24:
            head = sents[idx][:remaining]
            k = head.rfind(" ")
            if k > 12:
                head = head[:k]
            if head:
                out = f"{out} {head}"
    return _strip_trailing(out).strip()


def enabled_plugins(config: Path) -> list[tuple[str, str]]:
    """(name, marketplace) for every enabled plugin in config.toml. Empty on any read error."""
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for key, val in (data.get("plugins") or {}).items():
        if isinstance(val, dict) and val.get("enabled", False) and "@" in key:
            name, _, market = key.rpartition("@")
            out.append((name, market))
    return out


def _latest_version_dir(plugin_dir: Path) -> Path | None:
    subs = [p for p in plugin_dir.glob("*") if p.is_dir()]
    return sorted(subs)[-1] if subs else None


def targets() -> list[dict]:
    """Every distillable description: plugin.json `description` + SKILL.md `description:` lines.

    Each target: {kind, id, path, field, get(), set(new)} where field is 'json:description'
    (plugin.json) or 'yaml:description' (single-line SKILL.md frontmatter).
    """
    out: list[dict] = []

    def add_plugin_json(pj: Path, pid: str) -> None:
        try:
            d = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(d.get("description"), str):
            out.append({"kind": "plugin.desc", "id": pid, "path": pj, "field": "json:description"})

    def add_skill_md(sm: Path, sid: str, kind: str) -> None:
        out.append({"kind": kind, "id": sid, "path": sm, "field": "yaml:description"})

    # Enabled plugins: their plugin.json + bundled skills.
    for name, market in enabled_plugins(CODEX_HOME / "config.toml"):
        pdir = CACHE / market / name
        ver = _latest_version_dir(pdir)
        if not ver:
            continue
        for cand in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            pj = ver / cand
            if pj.is_file():
                add_plugin_json(pj, name)
                break
        for sm in (ver / "skills").glob("*/SKILL.md"):
            add_skill_md(sm, f"{name}:{sm.parent.name}", "plug.skill")

    # ~/.codex/skills — user + bundled .system skills.
    for sm in (CODEX_HOME / "skills").glob("**/SKILL.md"):
        kind = "sys.skill" if f"{os.sep}.system{os.sep}" in str(sm) else "user.skill"
        add_skill_md(sm, sm.parent.name, kind)
    return out


def _unwrap_scalar(raw: str) -> str | None:
    """Return the inner text of a single-line YAML scalar, or None if it is a quoted value that
    does not close on this line (a multi-line scalar we must not touch)."""
    if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
        body = raw[1:-1]
        if raw[0] == '"':
            body = body.replace('\\"', '"').replace("\\\\", "\\")
        return body
    if raw[:1] in "\"'":
        return None  # opening quote with no matching close on this line → multi-line; skip
    return raw


def _get(t: dict) -> str | None:
    """Current description value for a target, or None if unreadable / a skipped block scalar."""
    try:
        text = t["path"].read_text(encoding="utf-8")
    except Exception:
        return None
    if t["field"] == "json:description":
        try:
            return json.loads(text).get("description")
        except Exception:
            return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = _DESC_LINE.match(line)
        if m:
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            # A following indented, non-key line means a YAML block scalar → skip (don't corrupt).
            if nxt[:1] in (" ", "\t") and not _DESC_LINE.match(nxt.strip()):
                return None
            return _unwrap_scalar(m.group(2).strip())
    return None


def _set(t: dict, new: str) -> bool:
    """Atomically write `new` as the target's description. Validates before replacing."""
    path: Path = t["path"]
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    if t["field"] == "json:description":
        try:
            d = json.loads(text)
            d["description"] = new
            rendered = json.dumps(d, indent=2, ensure_ascii=False) + "\n"
            json.loads(rendered)  # paranoia: must round-trip
        except Exception:
            return False
    else:
        # Always emit a double-quoted, escaped scalar — valid YAML regardless of the original
        # style, and it can never leave an unterminated quote from a mid-string cut.
        esc = new.replace("\\", "\\\\").replace('"', '\\"')
        lines = text.splitlines(keepends=True)
        done = False
        for i, line in enumerate(lines):
            m = _DESC_LINE.match(line.rstrip("\n"))
            if m:
                eol = "\n" if line.endswith("\n") else ""
                lines[i] = f'{m.group(1)}"{esc}"{eol}'
                done = True
                break
        if not done:
            return False
        rendered = "".join(lines)
    tmp = path.with_suffix(path.suffix + ".slim-tmp")
    try:
        tmp.write_text(rendered, encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        return False
    return True


def _load_ledger() -> dict:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_ledger(led: dict) -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(json.dumps(led, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _key(t: dict) -> str:
    return f"{t['path']}::{t['field']}"


def run(mode: str, quiet: bool) -> int:
    tgts = targets()
    if not tgts:
        if not quiet:
            print("codex-skill-slim: no Codex skills/plugins found (nothing to do)")
        return 0

    rows = []
    for t in tgts:
        cur = _get(t)
        if cur is None:
            continue
        rows.append((len(cur), t, cur, distill(cur)))
    rows.sort(key=lambda r: r[0], reverse=True)
    total = sum(r[0] for r in rows)
    over = [r for r in rows if r[0] > CAP]

    if mode == "check":
        # Standing detection: any over-cap description means the budget has drifted / reverted.
        if over:
            saved = sum(r[0] - len(r[3]) for r in over)
            print(
                f"codex skill budget: {len(over)} description(s) over {CAP} chars "
                f"(total {total}B; {saved}B recoverable) — run codex-skill-slim.py --apply",
                file=sys.stderr,
            )
            return 1
        print(f"codex skill budget: ok ({total}B across {len(rows)} entries, all ≤{CAP})")
        return 0

    if mode == "restore":
        led = _load_ledger()
        restored = 0
        for t in tgts:
            k = _key(t)
            if k in led:
                if _set(t, led[k]):
                    restored += 1
        _save_ledger({})
        print(f"codex-skill-slim: restored {restored} original description(s)")
        return 0

    if mode == "report":
        print(
            f"codex skill/plugin description budget: {total}B across {len(rows)} entries "
            f"(cap {CAP}); {len(over)} over-cap"
        )
        for b, t, _cur, new in rows:
            flag = "SLIM →%3d" % len(new) if b > CAP else "ok      "
            print(f"  {b:5d}B  {flag}  {t['kind']:<11} {t['id']}")
        if over:
            saved = sum(r[0] - len(r[3]) for r in over)
            print(f"  → --apply would recover {saved}B ({total}→{total - saved}B), keeping every skill")
        return 0

    # mode == apply
    led = _load_ledger()
    changed = 0
    saved = 0
    for b, t, cur, new in rows:
        if b <= CAP or new == cur or not new:
            continue
        k = _key(t)
        led.setdefault(k, cur)  # preserve the FIRST-seen original as the restore point
        if _set(t, new):
            changed += 1
            saved += b - len(new)
            if not quiet:
                print(f"  slimmed {t['kind']:<11} {t['id']}: {b}→{len(new)}B")
    if changed:
        _save_ledger(led)
    new_total = total - saved
    if quiet:
        if changed:
            print(f"  codex-skill-slim: distilled {changed} description(s), {total}→{new_total}B (every skill kept)")
    else:
        print(
            f"codex-skill-slim: distilled {changed} description(s); budget {total}→{new_total}B "
            f"across {len(rows)} entries; every skill preserved"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="write the distilled descriptions")
    g.add_argument("--check", action="store_true", help="exit 1 if any description exceeds the cap")
    g.add_argument("--restore", action="store_true", help="restore original descriptions from the ledger")
    ap.add_argument("--quiet", action="store_true", help="one summary line (for the beat)")
    args = ap.parse_args()
    if not CODEX_HOME.is_dir():
        if not args.quiet:
            print("codex-skill-slim: no CODEX_HOME (nothing to do)")
        return 0
    mode = "apply" if args.apply else "check" if args.check else "restore" if args.restore else "report"
    try:
        return run(mode, args.quiet)
    except Exception as exc:  # fail-open: never break the beat
        if not args.quiet:
            print(f"codex-skill-slim: skipped ({exc})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
