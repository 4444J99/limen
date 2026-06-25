# Hooks — Full Excavation & Implementation Plan

*Authored 2026-06-25. Read-only excavation complete; **nothing built or wired**. This document is the report + plan the build will execute on approval.*

The originating pain (verbatim): *"shouldn't there be hooks that do all of the shit i keep repeating and copy and pasting over and over again?"* — i.e. the session-orientation context re-pasted every session should be auto-injected by a Claude Code hook. Governing instruction: *"we've built many hooks before — so excavate fully and totally first before building; create a report and full plan for implementation."*

---

## Part A — Excavation report (verified ground truth)

Method: full `git log` hook-creation history + `--diff-filter=D` deletion sweep, every harness-loadable `settings*.json`, the enabled plugin's `hooks.json`, and a disk-wide hook-script find. All claims below are verified against files on disk, not memory.

### A.1 The complete authored-hook inventory — with TRUE load status

The harness loads hooks from exactly two places: **`~/.claude/settings.json`** (user) and **`<project>/.claude/settings.json`** (+ `.local.json`). Anything else in the repo (e.g. `container/claude/settings.json`) is a *deploy template the harness never reads*.

| # | Hook script | Event | Declared in | **Actually loaded?** | Versioned? |
|---|---|---|---|---|---|
| 1 | `~/.claude/hooks/allow-trusted-cd-git.sh` | PreToolUse / Bash | `~/.claude/settings.json` (real file) | ✅ **LIVE** | ❌ no (user-level only) |
| 2 | `~/.claude/hooks/insights-capture.sh` | SessionEnd | `~/.claude/settings.json` | ✅ **LIVE** | ❌ no (user-level only) |
| 3 | `scripts/hooks/lint-edited-file.sh` | PostToolUse / Write\|Edit | `container/claude/settings.json` (**template**) | ❌ **DORMANT** — not in any loaded settings | ✅ yes |
| 4 | `scripts/hooks/session-closeout.sh` | (SessionEnd, per its header) | **nowhere** — no settings.json declares it | ❌ **DORMANT** — consumed only via the quicken log convention | ✅ yes |

Plus, not ours: the **`claude-code-warp` plugin** `hooks.json` registers **six** events — SessionStart, UserPromptSubmit, Stop, Notification, PermissionRequest, PostToolUse — all **notification-only** (pipe to `warp-notify.sh`; they inject no model context). Loaded via `enabledPlugins` in user settings → LIVE but inert for context.

Harness-internal: `~/.claude/session-env/<id>/sessionstart-hook-0.sh` is auto-generated plumbing (`export CLAUDE_CODE_VERSION=…`), written by warp's `on-session-start.sh`. The `.git/hooks/*.sample` files in cloned repos are noise.

### A.2 Corrections to my earlier verbal report (all now verified)

1. **"No SessionStart/UserPromptSubmit hook anywhere" was wrong.** Both events are occupied — by the warp plugin (notification-only). The true gap is narrower: **no OUR-authored *context-injecting* hook** on them. Because hooks merge across sources, ours will coexist with warp's.
2. **Missed the warp plugin's entire 6-event surface** on the first pass.
3. **The lint hook is NOT live.** I had called it "wired." Verified: every loadable `settings*.json` has zero `lint-edited-file` references; it exists only in the `container/claude/settings.json` **template**, which the harness never loads. It is dormant — the same status as `session-closeout.sh`. (`~/.claude/settings.json` is currently a **real file**, not the `migrate.sh` symlink into the runtime container — so the template never reached a loaded path.)
4. **`session-closeout.sh` is built but unwired** — its header says "SessionEnd hook," it writes `logs/session-closeout.jsonl`, and `scripts/quicken.py` *reads* that log — but no settings declares it. Producer disconnected from a present consumer.

### A.3 Hook-creation history ("the many hooks before")

`--diff-filter=D` returned nothing hook-related → **no hook was ever created-then-deleted**. "Many hooks before" = exactly the four authored scripts above, created in:

- `741cf17` (#180) — charter + `/closeout` skill + `lint-edited-file.sh` (first hook)
- `5dc339b` (#197) — "activate lint hook" settings change (the human-gated arming precedent)
- `69dbf30` (#189) — quicken closeout → `session-closeout.sh`
- `6721da7` / `1f06950` (#202) — `allow-trusted-cd-git.sh` + project allowlist

> Net: of four authored hooks, **only two are actually live** (both user-level, both unversioned). The two versioned repo-side hooks are dormant.

---

## Part B — The authoritative hook contract (docs-cited)

From `https://code.claude.com/docs/en/hooks-guide.md`, confirmed this session:

- **SessionStart injection:** `exit 0` + **plain text on stdout** → added to context. (Structured form also valid: `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"…"}}`.) **Never mix** plain text and JSON. Matchers: `startup | resume | clear | compact`. Type must be `command` (no `prompt`/`agent` type for SessionStart).
- **Fail-open by design:** for SessionStart, even `exit 2` only prints stderr to the user and **cannot block** the session. Any non-zero is non-blocking. So a SessionStart hook is structurally incapable of breaking a session.
- **Cross-source merge:** all hooks on an event run in parallel; identical commands dedupe; every source's `additionalContext`/stdout concatenates. → our hook **coexists** with warp's SessionStart.
- **Env/stdin:** `CLAUDE_PROJECT_DIR` is available; stdin JSON includes `session_id`, `cwd`, `transcript_path`, `source`.
- **Limits/gotchas:** keep output well under ~50 KB (our digest ≈ 1–2 KB). UserPromptSubmit has a 30 s timeout (irrelevant to us — we use SessionStart, not per-prompt).

---

## Part C — Design: the orientation organ

**Principle:** the daemon already computes orienting state every beat; the session should *read* it, not recompute it. `omni-view.py` is a ~1 s **HTML renderer** (writes `web/app/out/omni.html`) — wrong tool to shell out to at every boot. Instead:

```
 heartbeat / on-demand           SessionStart                model context
 ┌─────────────────────┐         ┌──────────────────┐        ┌───────────┐
 │ scripts/             │  writes │ scripts/hooks/   │ stdout │  injected │
 │  session-orient.py   ├────────►│ session-orient.sh├───────►│  at boot  │
 │ (lean, read-only,    │ logs/   │ (trivial cat,    │        └───────────┘
 │  PII-free digest)    │ session-│  fail-open,      │
 └─────────────────────┘ orient. │  exit 0 always)  │
                          md      └──────────────────┘
```

- **`scripts/session-orient.py`** — lean (<300 ms; reads only small persisted artifacts, **never** invokes the HTML renderer). Prints a compact PII-free markdown digest to stdout **and** persists it to `logs/session-orientation.md` (so the daemon can pre-warm it for instant `resume`). Fails open: a missing/torn input yields an empty section, never a crash (same discipline as `omni-view.py`).
- **`scripts/hooks/session-orient.sh`** — the SessionStart hook. Runs the generator under a hard `timeout`; on any failure, emits the last-good `logs/session-orientation.md` if present, else nothing. **Always `exit 0`.**

### C.1 What the digest contains (all PII-free, all from on-disk sources)

| Source on disk | Digest line |
|---|---|
| memory `MEMORY.md` north-star | the one-line revenue/north-star anchor |
| `his-hand-levers.json` (18 KB) | count of open levers + top N **titles/IDs** (already PII-free in the registry) |
| `logs/organ-health.json` | rungs green/total + any `needs_human` |
| `logs/health-organ-state.json` | health organ **liveness + counts only** — never content (firewall) |
| `tasks.yaml` | board status mix (open/done counts) |
| `git` | current branch, ahead/behind `main`, dirty flag |
| `EVERY-ASK-LEDGER.md` (head) | pointer line: "present-over-past cov session …" |

### C.2 PII firewall compliance (non-negotiable)

`logs/` is committed and `capture.sh` auto-pushes to the **public** origin. Therefore the digest is **counts-only, PII-free by construction** — it echoes health-organ *liveness*, never any chart content; it names lever **IDs/titles** that already live PII-free in the committed registry. The generator **hardcodes no medical literal** (the `health-pii-in-generator-code` rule: the firewall guards the generator, not just its output). Before first commit: `grep` the generator for medical terms and scan the committed blob, per the firewall recipe.

---

## Part D — Exact implementation artifacts (to be created on approval)

### D.1 `scripts/hooks/session-orient.sh` (full)

```bash
#!/usr/bin/env bash
# SessionStart context-injection hook — emits a PII-free orientation digest to stdout.
# Fail-open BY CONSTRUCTION: any error → emit nothing → exit 0. A SessionStart hook
# cannot block a session even on exit 2 (per the Claude Code hooks contract).
# Activated by a one-line SessionStart entry in a HARNESS-LOADED settings.json (Part E).
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-}"
[ -z "$ROOT" ] && ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)"
[ -z "$ROOT" ] && exit 0                       # not in a project → no-op
GEN="$ROOT/scripts/session-orient.py"
DIGEST="$ROOT/logs/session-orientation.md"

# Primary: regenerate fresh (lean + read-only) under a hard timeout; the generator
# prints the digest to stdout AND refreshes $DIGEST. No-op cleanly outside limen.
if command -v python3 >/dev/null 2>&1 && [ -f "$GEN" ]; then
  timeout 5 python3 "$GEN" 2>/dev/null && exit 0
fi
# Fallback: emit the last good digest the daemon left behind.
[ -f "$DIGEST" ] && cat "$DIGEST"
exit 0
```

### D.2 `scripts/session-orient.py` (spec / skeleton)

```python
#!/usr/bin/env python3
"""session-orient.py — the PII-free session-orientation digest.

Reads ONLY small persisted artifacts (never the 1s HTML renderer). Prints a compact
markdown digest to stdout AND writes logs/session-orientation.md. Every section FAILS
OPEN — a missing/torn input yields an empty section, never a crash.

PII FIREWALL: counts-only. Echoes NO chart/health content; hardcodes NO medical literal.
"""
import json, os, subprocess
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))

def _json(p, default):
    try: return json.loads(Path(p).read_text())
    except Exception: return default

def section_north_star() -> str: ...      # one line from memory MEMORY.md
def section_levers()    -> str: ...        # open count + top N titles from his-hand-levers.json
def section_organs()    -> str: ...        # green/total + needs_human from logs/organ-health.json
def section_health()    -> str: ...        # liveness + counts ONLY from logs/health-organ-state.json
def section_board()     -> str: ...        # open/done counts from tasks.yaml
def section_git()       -> str: ...        # branch, ahead/behind main, dirty

def main():
    parts = [f(  ) for f in (section_north_star, section_levers, section_organs,
                             section_health, section_board, section_git)]
    digest = "## Session orientation (auto)\n\n" + "\n".join(p for p in parts if p)
    print(digest)                                   # → injected as context
    out = ROOT / "logs" / "session-orientation.md"  # → daemon pre-warm / fallback
    try: out.write_text(digest)
    except Exception: pass

if __name__ == "__main__":
    main()
```

### D.3 Daemon pre-warm (optional, cheap)

Add a beat gate (e.g. `C_ORIENT`, or fold into an existing beat) that runs `session-orient.py` once per heartbeat so `resume` reads an already-fresh `logs/session-orientation.md` without paying even the 300 ms. Not required for correctness — the hook regenerates on demand — but it matches the autopoiesis "compute on the daemon" stance.

---

## Part E — Activation (his hand, one reversible paste)

Hook *config* changes are a security boundary — Claude Code treats arming a hook as human-gated. I build + dry-run; **you** paste one block. This is the #197 precedent.

**Where it must go to actually fire:** a **harness-loaded** settings file — NOT `container/claude/settings.json` (the template the harness never reads). Two options:

- **Recommended — universal (`~/.claude/settings.json`, the real file):** fires in *every* session, every limen worktree and the main checkout — which is the point ("the shit I repeat **every** session"). The script self-guards (`exit 0` outside a project that has `scripts/session-orient.py`), so it's a safe no-op in unrelated projects.
- **Narrow (`<project>/.claude/settings.json`):** limen-only, but must be added per checkout/worktree.

The block (merges alongside the existing PreToolUse + SessionEnd hooks):

```json
"SessionStart": [
  { "matcher": "startup|resume",
    "hooks": [ { "type": "command",
                 "command": "$CLAUDE_PROJECT_DIR/scripts/hooks/session-orient.sh" } ] }
]
```

**Reversibility:** delete the block to disarm; the hook can't block a session even while armed; the generator is read-only. Fully reversible.

---

## Part F — Cleanup items the excavation surfaced (fold into the same PR)

1. **Dormant lint hook** (`lint-edited-file.sh`): decide its fate — either *arm* it (add its PostToolUse block to a loaded settings file, same as above) or *retire* the dead template in `container/claude/settings.json`. Right now it's neither live nor removed.
2. **Dangling `session-closeout.sh`:** wire it (one SessionEnd line) so quicken's `logs/session-closeout.jsonl` actually gets fed, **or** retire it. Producer currently disconnected from a present consumer.
3. **Unversioned user-level hooks** (`allow-trusted-cd-git.sh`, `insights-capture.sh`): they exist only under `~/.claude/hooks/` — outside git, so `capture.sh` never backs them up. Copy them into `scripts/hooks/` (versioned, capture-backed) and point the user settings at the repo copies. Closes the durability gap.

---

## Part G — Definition of done (executable predicate)

A `done.sh` for this work asserts:

1. `scripts/hooks/session-orient.sh` and `scripts/session-orient.py` exist and `python3 scripts/session-orient.py` exits 0, prints a digest, and writes `logs/session-orientation.md`.
2. **PII-free proof:** the generated `logs/session-orientation.md` and the generator source contain **no** medical literal (grep deny-list) — fails closed if any appears.
3. **Idempotent:** two consecutive generator runs produce byte-identical output (modulo the live counts), no crash on missing inputs (simulate by pointing `LIMEN_ROOT` at an empty dir → still exit 0, empty digest).
4. **Fail-open proof:** `CLAUDE_PROJECT_DIR=/nonexistent scripts/hooks/session-orient.sh` exits 0 and emits nothing.
5. Lint + the relevant slice of `scripts/verify-whole.sh` pass.
6. The activation block is **not** auto-applied — `done.sh` confirms it's documented for his paste, not silently written into a loaded settings file.

---

## Part H — Non-goals / risks

- **Non-goal:** building or arming anything before approval; touching `~/.claude/settings.json` myself (his paste).
- **Non-goal:** UserPromptSubmit injection — SessionStart covers the "every session" pain without per-prompt cost.
- **Risk (mitigated):** PII leak via `logs/` → mitigated by counts-only digest + generator scan + the firewall recipe.
- **Risk (mitigated):** boot latency → mitigated by the lean generator + hard timeout + daemon pre-warm.
- **Risk (mitigated):** the hook silently not firing because it was placed in the unloaded `container/` template → mitigated by Part E targeting a harness-loaded settings file explicitly.

---

*Build order on approval: (1) write the two scripts + `done.sh`; (2) dry-run the generator and paste its sample output here; (3) hand you the exact one-block settings paste; (4) optionally wire the daemon pre-warm + tackle the three Part F cleanups. No hook armed until you say so.*

---

## Part I — Build outcome (2026-06-25, approved "all go — full permissions")

**Scope decision (changed from Part E):** activation targets the **committed, git-tracked `.claude/settings.json`** (limen-scoped), **not** the user-level `~/.claude/settings.json`. Verified facts that drove it: `.claude/settings.json` *is* tracked in limen (main + every worktree); `~/.claude` is **not** git/chezmoi-managed. Committed project settings give versioned + capture-backed + limen-scoped activation in one move, and avoid repointing the two **user-level** cross-project hooks (which must keep firing everywhere). The orientation digest is 100% limen-specific, so "universal" scope would only no-op elsewhere anyway.

**Built & verified (all green via `scripts/done-session-orient.sh`, exit 0):**

| Artifact | State |
|---|---|
| `scripts/session-orient.py` | ✅ lean, read-only, PII-free counts-only generator; ruff-clean; idempotent; fails open per section |
| `scripts/hooks/session-orient.sh` | ✅ SessionStart reader; `timeout`-guarded (macOS-safe); clean no-op outside a project; always `exit 0` |
| `scripts/done-session-orient.sh` | ✅ the executable predicate (artifacts · PII deny-list · idempotent · fail-open · lint · activation report) |
| `scripts/hooks/insights-capture.sh` | ✅ **Part F.3** — versioned backup copy of the live user-level hook (byte-identical) |
| sample digest | 766 bytes, counts-only, PII-free (north star · 12 levers · 2/11 organs · health counts · board · git · pointers) |

**Part F dispositions:**
- **F.1 (lint hook):** resolved by *arming* — a `PostToolUse Write|Edit` entry in the activation block below (advisory, always `exit 0`).
- **F.2 (closeout hook):** resolved by *wiring* — a `SessionEnd` entry in the activation block; feeds quicken's `logs/session-closeout.jsonl`.
- **F.3 (unversioned user hooks):** `allow-trusted-cd-git.sh` was *already* versioned in `scripts/hooks/` (byte-identical to live); only `insights-capture.sh` was missing → now committed. **Not** repointed: both stay on absolute `~/.claude/hooks/` paths in user settings so they keep firing in all projects.

**The one his-hand step — activation is harness-gated.** Writing hook entries into any `settings.json` is blocked by the Claude Code auto-mode classifier (the #197 security boundary), independent of verbal permission. The exact block to paste into **`.claude/settings.json`** (alongside the existing `permissions`) is the three-hook `"hooks"` object: `SessionStart startup|resume → session-orient.sh`, `PostToolUse Write|Edit → lint-edited-file.sh`, `SessionEnd → session-closeout.sh`, each via `$CLAUDE_PROJECT_DIR/scripts/hooks/…`. After paste, `scripts/done-session-orient.sh` reports `ACTIVATION: WIRED`, then the PR commits + merges (docs/scripts only — not a deploy-trigger path). Fully reversible: delete the `"hooks"` block to disarm.
