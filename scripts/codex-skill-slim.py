#!/usr/bin/env python3
"""codex-skill-slim.py — distill Codex skill/plugin descriptions to fit the skills budget.

The pain: Codex warns "skill descriptions were shortened to fit the 2% skills context
budget" every session and then mangles descriptions on its own. The session-noise-containment
doctrine (domus-genoma reliquary, Rule 1) BANS the obvious "fix" — disabling plugins/skills —
because that reduces capability to silence noise. And letting the notice ride is rug-sweeping.

The third path (his directive 2026-07-02): make the descriptions THINNER. Keep EVERY skill;
distill each description to a meaning-preserving lead so the total fits the budget and Codex
never has to shorten anything. This is "distillation, not reduction."

GROUND TRUTH (corrected 2026-07-03): Codex loads skill metadata from EVERY cached marketplace
plugin — not just the ones enabled in config.toml — plus `~/.codex/skills` and
`~/.codex/memories/skills`. Its own render log proves it: `budget_limit=5440 total_skills=133`
with only 9 plugins enabled. So this organ enumerates the FULL loaded set, and the cap is
DERIVED from Codex's live per-skill allowance (budget ÷ skill-count), never a hardcoded number —
the earlier 240-char / enabled-only version was scoped to ~17 of the 133 skills and left the
warning firing. Slimming below Codex's own allowance is what makes truncation stop.

DURABILITY: the fat lives in `~/.codex/plugins/cache/**` (marketplace caches) which REVERT on
refresh, so this is a REPAIR organ, not a one-shot edit (containment Rule 6): idempotent, run
every beat, re-distilling anything that reverted to fat. A backup ledger + `--restore` is the
revert guard (Rule 10); `--check` is standing detection so a reversion surfaces in the beat log —
never hidden.

`--check` is deliberately NOT self-referential (the failure that shipped once: a green byte-count
that only proved we agreed with ourselves). It couples TWO signals: (1) predictive — anything over
the derived cap will be truncated on Codex's next render; (2) confirmatory — Codex's OWN render log
(`logs_2.sqlite`) as an independent witness: if Codex truncated AFTER our last real slim (ledger
mtime), the cap was silently too loose and we exit 1 EVEN IF every description looks under-cap. The
witness overrides the proxy, so a false-green cannot recur.

Modes:
  (no flag)   dry-run report — rank every description, show what WOULD be slimmed. Safe.
  --apply     write the distilled descriptions (atomic, validated, backed up first).
  --check     exit 1 if any tracked description exceeds the cap OR Codex's log shows it truncated
              since the last slim (predictive proxy + ground-truth witness; for the beat/CI).
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
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
CACHE = CODEX_HOME / "plugins" / "cache"
LEDGER = CODEX_HOME / ".skill-slim" / "backup.json"
LOGDB = CODEX_HOME / "logs_2.sqlite"

# The cap is DERIVED from Codex's live per-skill budget, not pinned. LIMEN_CODEX_SLIM_CAP is an
# explicit override / escape-hatch only; unset (the default) means "derive from ground truth".
CAP_OVERRIDE = os.environ.get("LIMEN_CODEX_SLIM_CAP")
_MARGIN = 0.9  # sit safely UNDER Codex's per-skill allowance so it never has to truncate
_MIN_CAP, _MAX_CAP = 60, 240  # clamp the derived cap to a sane, human-readable band
_DEFAULT_BUDGET_TOKENS = 5440  # Codex's observed 2% skills budget (fallback when logs are absent)
_CHARS_PER_TOKEN = 4.0  # rough tokenizer ratio (fallback; the log's own numbers override this)
_DEFAULT_CAP = 150  # last-resort cap when neither logs nor an enumerated count are available

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# Single-line YAML frontmatter description:  `description: <value>`  (we SKIP block scalars).
_DESC_LINE = re.compile(r"^(description:[ \t]*)(\S.*)$")
# Dangling connectors to trim off a cut tail so it reads as a clean clause, not "…such as".
_TRAIL_WORD = re.compile(r"\s+(?:and|or|the|an?|to|with|for|of|such|as|by|in|on|at|that|when)$", re.I)


def _strip_trailing(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        # Trailing whitespace, punctuation, and dangling openers/connectors left by a mid-clause cut
        # (a lone "—", "(", "/", "&", ":" reads as broken; sentence-enders . ! ? are kept).
        s = re.sub(r"[\s,;:—–\-()\[\]{}/&|]+$", "", s)
        s = _TRAIL_WORD.sub("", s)
    return s


def distill(text: str, cap: int = _DEFAULT_CAP) -> str:
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


def codex_skill_budget() -> dict | None:
    """Codex's own per-skill budget, read from its TUI render log (ground truth). None on failure.

    Codex emits `truncated skill metadata to fit skills context budget budget_limit=… total_skills=…
    truncated_description_chars_per_skill=…` whenever it shortens descriptions. That line IS the
    budget: `truncated_description_chars_per_skill` is the exact per-skill char allowance for the
    current skill count. Opened read-only + immutable so a live Codex never blocks on us; fail-open.
    """
    if not LOGDB.is_file():
        return None
    try:
        import sqlite3

        con = sqlite3.connect(f"file:{LOGDB}?mode=ro&immutable=1", uri=True, timeout=1.5)
        try:
            row = con.execute(
                "SELECT ts, feedback_log_body FROM logs "
                "WHERE feedback_log_body LIKE '%truncated skill metadata%' "
                "ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        finally:
            con.close()
    except Exception:
        return None
    if not row or not row[1]:
        return None
    body = row[1]

    def _num(key: str) -> int | None:
        m = re.search(rf"{key}=(\d+)", body)
        return int(m.group(1)) if m else None

    try:
        ts = int(row[0]) if row[0] is not None else None
    except (TypeError, ValueError):
        ts = None
    return {
        "ts": ts,  # epoch of Codex's most recent truncation — the enactment witness
        "budget_tokens": _num("budget_limit"),
        "total_skills": _num("total_skills"),
        "chars_per_skill": _num("truncated_description_chars_per_skill"),
    }


def derive_cap(n_skills: int) -> int:
    """The char cap to distill every loaded description under, DERIVED from Codex's live budget.

    Codex divides a fixed char budget across the skills it loads and truncates any description over
    its share. So the cap that guarantees zero truncation is `char_budget ÷ N × margin`, where N is
    the WORST-CASE skill count — the larger of Codex's logged `total_skills` and our own enumerated
    skill count (the full on-disk cache). Codex can only ever load skills that exist on disk, so
    dividing by that ceiling means no subset it picks today, and no plugin it caches tomorrow, can
    overflow. `char_budget` comes straight from the render log (`chars_per_skill × total_skills`);
    the token-ratio fallback is only for when no truncation has ever been logged.

    Priority: explicit LIMEN_CODEX_SLIM_CAP override → derived worst-case cap → safe constant.
    Clamped to [60, 240].
    """
    if CAP_OVERRIDE:
        try:
            return max(_MIN_CAP, int(CAP_OVERRIDE))
        except ValueError:
            pass
    b = codex_skill_budget() or {}
    cps, logged_n, tokens = b.get("chars_per_skill"), b.get("total_skills"), b.get("budget_tokens")
    if cps and logged_n:
        char_budget = cps * logged_n  # exact: Codex's own per-skill allowance × its skill count
    else:
        char_budget = (tokens or _DEFAULT_BUDGET_TOKENS) * _CHARS_PER_TOKEN
    n = max(n_skills or 1, logged_n or 0)  # worst-case: whichever skill count is larger
    return max(_MIN_CAP, min(_MAX_CAP, int(char_budget / n * _MARGIN)))


def enabled_plugins(config: Path) -> list[tuple[str, str]]:
    """(name, marketplace) for every enabled plugin in config.toml. Empty on any read error.

    Retained for diagnostics only — `targets()` no longer filters by enablement, because Codex
    loads every cached plugin's metadata into the budget regardless of this flag.
    """
    try:
        import tomllib

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
    """Every distillable description Codex LOADS into its skills budget — the FULL set.

    Codex ingests skill metadata from every cached marketplace plugin regardless of the config.toml
    `enabled` flag (confirmed against its render log: 133 skills loaded from 9 enabled plugins),
    plus `~/.codex/skills` and `~/.codex/memories/skills`. Enumerating a superset is safe — slimming
    a description Codex happens not to load costs nothing. Each target: {kind, id, path, field}.
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

    # Every cached plugin across every marketplace — Codex loads them all, enabled or not.
    if CACHE.is_dir():
        for market in sorted(CACHE.iterdir()):
            if not market.is_dir() or market.name.startswith("."):
                continue
            for pdir in sorted(market.iterdir()):
                if not pdir.is_dir() or pdir.name.startswith("."):
                    continue
                ver = _latest_version_dir(pdir) or pdir
                for cand in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
                    pj = ver / cand
                    if pj.is_file():
                        add_plugin_json(pj, f"{market.name}/{pdir.name}")
                        break
                for sm in (ver / "skills").glob("*/SKILL.md"):
                    add_skill_md(sm, f"{pdir.name}:{sm.parent.name}", "plug.skill")

    # ~/.codex/skills — user + bundled .system skills.
    for sm in (CODEX_HOME / "skills").glob("**/SKILL.md"):
        kind = "sys.skill" if f"{os.sep}.system{os.sep}" in str(sm) else "user.skill"
        add_skill_md(sm, sm.parent.name, kind)

    # ~/.codex/memories/skills — memory-scoped skills.
    for sm in (CODEX_HOME / "memories" / "skills").glob("**/SKILL.md"):
        add_skill_md(sm, sm.parent.name, "mem.skill")
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

    # Codex's budget metric is `total_skills`, so derive the cap against the SKILL count (SKILL.md
    # descriptions), not the skill+plugin.json total. plugin.json descriptions are slimmed too, but
    # they do not drive the per-skill divisor.
    n_skills = sum(1 for t in tgts if t["field"] == "yaml:description")
    cap = derive_cap(n_skills)

    rows = []
    for t in tgts:
        cur = _get(t)
        if cur is None:
            continue
        rows.append((len(cur), t, cur, distill(cur, cap)))
    rows.sort(key=lambda r: r[0], reverse=True)
    total = sum(r[0] for r in rows)
    over = [r for r in rows if r[0] > cap]

    if mode == "check":
        # Two COUPLED signals, so a green here means what the USER sees — not a proxy for it.
        #   (1) PREDICTIVE (proxy): any description over the derived cap will be truncated on Codex's
        #       next render — drift/reversion caught before it happens.
        #   (2) CONFIRMATORY (ground truth): Codex's OWN render log — did it truncate AFTER our last
        #       real slim? This is the independent witness that catches a cap silently gone too loose
        #       (the exact false-green that shipped once: descriptions "under cap" yet Codex truncated
        #       anyway because its budget shrank or its skill count grew past what we enumerate). The
        #       ledger's mtime is the "last real slim" instant (written only when --apply changes a
        #       description); a truncation newer than that is Codex telling us the proxy was wrong.
        b = codex_skill_budget() or {}
        trunc_ts = b.get("ts")
        try:
            applied_at = LEDGER.stat().st_mtime if LEDGER.is_file() else None
        except OSError:
            applied_at = None
        truncated_after_slim = bool(trunc_ts and applied_at and trunc_ts > applied_at)
        emitted = ""
        if trunc_ts:
            import time as _time

            when = _time.strftime("%Y-%m-%dT%H:%MZ", _time.gmtime(trunc_ts))
            emitted = (
                f"; Codex last truncated {when} ({b.get('total_skills')} skills @ "
                f"{b.get('chars_per_skill')} chars/skill)"
                + (" — AFTER the last slim" if truncated_after_slim else " — none since the last slim")
            )
        if over or truncated_after_slim:
            reasons = []
            if over:
                saved = sum(r[0] - len(r[3]) for r in over)
                reasons.append(f"{len(over)} of {len(rows)} description(s) over {cap} chars ({saved}B recoverable)")
            if truncated_after_slim:
                # Ground truth overrides the proxy: Codex truncated even though our cap said fine.
                reasons.append(
                    "Codex truncated AFTER the last slim — derived cap too loose (budget shrank / skills grew)"
                )
            print(
                f"codex skill budget: {'; '.join(reasons)} (total {total}B){emitted} — run codex-skill-slim.py --apply",
                file=sys.stderr,
            )
            return 1
        print(f"codex skill budget: ok ({total}B across {len(rows)} entries, all ≤{cap}){emitted}")
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
            f"(derived cap {cap}); {len(over)} over-cap"
        )
        for b, t, _cur, new in rows:
            flag = "SLIM →%3d" % len(new) if b > cap else "ok      "
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
        if b <= cap or new == cur or not new:
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
            f"across {len(rows)} entries (cap {cap}); every skill preserved"
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
