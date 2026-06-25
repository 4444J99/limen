#!/usr/bin/env python3
"""creds-hydrate.py — the credential HYDRATION organ. One source of truth, auto-applied everywhere.

THE DISEASE this cures: you log into a vendor (gemini / opencode / codex / …) ONCE — and then a new
worktree, a fresh machine state, or a lapsed token makes you do it AGAIN. The credentials already
EXIST (minted once into 1Password: `op://Personal/Gemini API Key`, the Cloudflare token, the
GitHub tokens, …). The fleet just never READS from that source of truth at the point of use:
  - the value lands in ~/.limen.env but the daemon never loads it into the subprocess env
    (dispatch.py ran agent CLIs with env=None → they inherit a daemon env that lacks the key); and
  - OAuth/CLI tools want their auth in a tool-native file (~/.gemini, opencode auth.json) that a
    one-time login "elsewhere" wrote in a context this machine/worktree doesn't have.

THE CURE (this organ): 1Password is the ONE source of truth. On every beat / worktree-start / login,
hydrate idempotently + silently:
  1. `op read` each canonical credential,
  2. materialize it into ~/.limen.env (the env cache the daemon + dispatch._load_limen_env() read),
     and into each tool's native location where one is configured,
  3. never echo a value, chmod 600, atomic write, add-or-replace (re-runnable).
Token lapse self-heals: the next beat re-hydrates from 1Password. A fresh worktree/machine hydrates
from 1Password too — because 1Password is everywhere your login is. So you authenticate each service
exactly ONCE (the first mint into 1Password), and never re-enter a vendor login again.

The ONLY irreducible human atom left: the 1Password session must be unlocked (`op signin` /
Touch-ID / a service account) — a per-boot biometric touch at most, never a per-tool re-login.

Companion pieces (same PR):
  - dispatch._load_limen_env() — loads ~/.limen.env into os.environ so agent subprocesses inherit it.
  - metabolize.sh — sources ~/.limen.env and runs this organ each beat.
  - deploy/com.limen.creds-hydrate.plist — a launchd login agent (arming is your hand, like the watchdog).
  - route.py capacity census — the VERIFIER: after hydration every lane should read "up".

Fail-open by contract: any `op` error skips that one credential (logged by NAME only) and never crashes
the beat. Read-only by default (`--dry-run` prints the op://→target plan with NO secret reads); writes
only with `--apply`.

Usage:
  python3 scripts/creds-hydrate.py --dry-run     # print the plan (no reads, no writes) — default
  python3 scripts/creds-hydrate.py --check       # which canonical refs + targets are present (NAMES only)
  python3 scripts/creds-hydrate.py --apply        # op read → materialize into ~/.limen.env + tool files
  LIMEN_CREDS_MAP=/path/map.json python3 scripts/creds-hydrate.py --apply   # override the named map

The MAP is a NAMED, tweakable parameter (one entry per credential). Edit DEFAULT_MAP below or point
LIMEN_CREDS_MAP at a JSON file with the same shape.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ENV_FILE = Path(os.environ.get("LIMEN_ENV", str(Path.home() / ".limen.env")))

# --- THE NAMED MAP ----------------------------------------------------------------------------------
# One entry per credential. Derived from your 1Password inventory (`op item list`, names only).
#   ref:   a full op:// reference INCLUDING the field (op://<vault>/<item>/<field>). API_CREDENTIAL
#          items expose `credential`; LOGIN/PASSWORD items expose `password`. Tweak the field if a
#          --check shows it unreadable — the value is never printed, only its presence.
#   env:   env-var names to write into ~/.limen.env (most CLIs read these directly: gemini reads
#          GEMINI_API_KEY/GOOGLE_GENERATIVE_AI_API_KEY; codex/opencode read OPENAI/OPENROUTER; gh
#          reads GH_TOKEN/GITHUB_TOKEN).
#   file:  optional tool-native target {"path": "~/.x/auth.json", "template": "...{value}..."} for
#          tools that only read a file. Omit when env alone suffices.
#   enabled: set False to park an entry (e.g. claude — its token is owned by the credential-race
#          fix / Rung-0 self-heal; hydrating it here could fight that handler).
DEFAULT_MAP: list[dict] = [
    {
        "lane": "gemini",
        "ref": "op://Personal/Gemini API Key/credential",
        "env": ["GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"],
        "enabled": True,
    },
    {
        # Parked — PHANTOM env var, retired 2026-06-25 (session efb53173) after walking it to certainty.
        # codex authenticates via ChatGPT OAuth (`codex login`): ~/.codex/auth.json shows auth_mode=chatgpt,
        # live OAuth tokens, and OPENAI_API_KEY=null — codex never reads OPENAI_API_KEY. No fleet code reads
        # it either (grep of cli/src: zero consumers). And the user runs ChatGPT by subscription, never minted
        # an OpenAI API key, so op://Personal/OpenAI never resolved (17 failed reads across history, no alt
        # name ever existed). Hydrating it was a no-op chasing a key that does not and need not exist.
        # The codex lane is ALREADY UP via its own OAuth — disabling this changes nothing but the SKIP noise.
        # Enable only if the user ever mints a real OpenAI API key AND a tool is switched to key-auth.
        "lane": "codex/opencode (openai)",
        "ref": "op://Personal/OpenAI/credential",
        "env": ["OPENAI_API_KEY"],
        "enabled": False,
    },
    {
        # Parked — PHANTOM env var, retired 2026-06-25 (same investigation). opencode derives its model from
        # `opencode models` (see dispatch._opencode_model): paid tier comes from `opencode auth login` writing
        # opencode's OWN auth.json, else it falls back to a FREE coding model — it never reads OPENROUTER_API_KEY.
        # No fleet code reads OPENROUTER_API_KEY (grep of cli/src: zero consumers), no opencode provider auth
        # exists on this host, and op://Personal/OpenRouter API Key never resolved (only-ever-tried ref, always
        # failed). The opencode lane runs on its free model regardless. Enable only if an OpenRouter key is
        # minted AND opencode is configured to consume the env var.
        "lane": "opencode (openrouter)",
        "ref": "op://Personal/OpenRouter API Key/credential",
        "env": ["OPENROUTER_API_KEY"],
        "enabled": False,
    },
    {
        "lane": "gh/copilot/jules",
        "ref": "op://GitHub-Tokens/master-org-token-011726/password",
        "env": ["GH_TOKEN", "GITHUB_TOKEN"],
        "enabled": True,
    },
    {
        "lane": "cloudflare (wrangler deploy)",
        "ref": "op://Personal/Cloudflare API Token/credential",
        "env": ["CLOUDFLARE_API_TOKEN"],
        "enabled": True,
    },
    {
        # Parked: the Claude token is owned by the credential-race fix + Rung-0 self-heal
        # ([[claude-login-flap-credential-race]] / L-CLAUDE-AUTH). Enable only if that handler is retired.
        "lane": "claude",
        "ref": "op://Personal/Claude/password",
        "env": ["LIMEN_CLAUDE_AUTH_TOKEN"],
        "enabled": False,
    },
]


def load_map() -> list[dict]:
    """The map is a named param: env override → JSON file, else the built-in default."""
    override = os.environ.get("LIMEN_CREDS_MAP")
    if override:
        try:
            data = json.loads(Path(override).read_text())
            return data if isinstance(data, list) else data.get("map", [])
        except Exception as e:  # noqa: BLE001 — fail-open onto the default
            print(f"  warn: could not read LIMEN_CREDS_MAP={override} ({e}); using built-in map", file=sys.stderr)
    return DEFAULT_MAP


def have_op() -> bool:
    return shutil.which("op") is not None


def op_read(ref: str, timeout: int = 15) -> str | None:
    """Read ONE secret from 1Password. Returns the value (never printed) or None on any failure."""
    try:
        r = subprocess.run(
            ["op", "read", ref],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    val = (r.stdout or "").strip()
    return val or None


def _ensure_env_file() -> None:
    if not ENV_FILE.exists():
        ENV_FILE.touch()
    ENV_FILE.chmod(0o600)


def _env_has(key: str) -> bool:
    if not ENV_FILE.exists():
        return False
    for line in ENV_FILE.read_text().splitlines():
        s = line.strip()
        if s.startswith(f"{key}=") or s.startswith(f"export {key}="):
            # present AND non-empty
            return s.split("=", 1)[1].strip() not in ("", '""', "''")
    return False


def write_env(key: str, value: str) -> None:
    """Idempotent add-or-replace into ~/.limen.env — atomic, chmod 600, value NEVER echoed.
    Mirrors scripts/set-credential.sh so the two stay interchangeable."""
    _ensure_env_file()
    existing = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    kept = [ln for ln in existing if not (ln.strip().startswith(f"{key}=") or ln.strip().startswith(f"export {key}="))]
    kept.append(f"export {key}={value}")
    fd, tmp = tempfile.mkstemp(dir=str(ENV_FILE.parent))
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)  # 600
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(kept) + "\n")
        os.replace(tmp, ENV_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    ENV_FILE.chmod(0o600)


def write_tool_file(spec: dict, value: str) -> str:
    """Materialize a credential into a tool-native file. Returns the path written."""
    path = Path(os.path.expanduser(spec["path"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    content = spec.get("template", "{value}").replace("{value}", value)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent))
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    path.chmod(0o600)
    return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Hydrate fleet credentials from 1Password — once minted, never re-logged-in.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="op read → materialize into ~/.limen.env + tool files")
    g.add_argument("--check", action="store_true", help="report presence of canonical refs + env targets (names only)")
    g.add_argument("--dry-run", action="store_true", help="print the op://→target plan; NO reads, NO writes (default)")
    args = ap.parse_args()

    cred_map = [e for e in load_map() if e.get("enabled", True)]
    if not cred_map:
        print("creds-hydrate: map is empty (all entries disabled) — nothing to do")
        return 0

    if not have_op():
        print("creds-hydrate: `op` (1Password CLI) not found — install it, then `op signin`. Skipping (fail-open).")
        return 0

    # --check: presence only, no secret reads of the env file's values
    if args.check:
        print(f"creds-hydrate --check ({ENV_FILE}):")
        for e in cred_map:
            envs = e.get("env", [])
            present = all(_env_has(k) for k in envs) if envs else False
            mark = "✓" if present else "✗"
            print(f"  {mark} {e['lane']:28} {ref_display(e['ref'])} -> {','.join(envs) or '(file only)'}")
        return 0

    apply = args.apply  # default (no flag) == dry-run
    print(f"creds-hydrate {'--apply' if apply else '--dry-run (no reads, no writes — pass --apply to hydrate)'}:")
    hydrated, skipped = 0, 0
    for e in cred_map:
        ref, envs, fspec = e["ref"], e.get("env", []), e.get("file")
        targets = ", ".join(envs) + (f" + {fspec['path']}" if fspec else "")
        if not apply:
            print(f"  plan: {e['lane']:28} {ref_display(ref)} -> {targets}")
            continue
        val = op_read(ref)
        if not val:
            print(f"  SKIP {e['lane']:28} {ref_display(ref)} — unreadable (check op signin / the field name)")
            skipped += 1
            continue
        for k in envs:
            write_env(k, val)
        wrote_file = write_tool_file(fspec, val) if fspec else None
        del val  # drop the secret from memory promptly
        loc = (",".join(envs) or "") + (f" + {wrote_file}" if wrote_file else "")
        print(f"  ✓ {e['lane']:28} -> {loc}")
        hydrated += 1

    if apply:
        print(f"creds-hydrate: {hydrated} hydrated, {skipped} skipped. "
              f"Apply to the running daemon: launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat")
        if skipped:
            print("  (skipped = `op` couldn't read it: unlock with `op signin`, or fix the field in the map. "
                  "Never a vendor re-login — only the 1Password unlock.)")
    return 0


def ref_display(ref: str) -> str:
    """op://vault/item/field — safe to print (it's a path, not a secret)."""
    return ref


if __name__ == "__main__":
    raise SystemExit(main())
