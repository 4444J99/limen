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

PRESENCE is not VALIDITY. `--check` (and route.py's capacity census) only ask "is the env var set?" —
a stale/revoked/suspended token sits in ~/.limen.env looking ✓ while every lane it feeds is dead. The
durable predicate is `--verify`: it authenticates each materialized credential against its own service
(gh /user, cloudflare /tokens/verify, gemini /models) and exits non-zero on a dead token. Run it after
--apply and on a cadence — a green --check over dead creds is the precise way "done" silently rots.

Usage:
  python3 scripts/creds-hydrate.py --dry-run     # print the plan (no reads, no writes) — default
  python3 scripts/creds-hydrate.py --check       # PRESENCE of env targets (NAMES only; offline) — not validity
  python3 scripts/creds-hydrate.py --verify      # VALIDITY — authenticate each cred against its service; exit 1 if any dead
  python3 scripts/creds-hydrate.py --apply        # op read → materialize into ~/.limen.env + tool files
  LIMEN_CREDS_MAP=/path/map.json python3 scripts/creds-hydrate.py --apply   # override the named map

The MAP is a NAMED, tweakable parameter (one entry per credential). Edit DEFAULT_MAP below or point
LIMEN_CREDS_MAP at a JSON file with the same shape.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
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
#   derive: optional ["cmd", "arg", ...] that MINTS the value from a live local source (e.g. the gh
#          keyring via `gh auth token`) instead of a static op:// secret. Tried BEFORE `ref`; runs with
#          GH_TOKEN/GITHUB_TOKEN unset so a dead floor token can't shadow the keyring. Fail-open → ref.
#   enabled: set False to park an entry (e.g. claude — its token is owned by the credential-race
#          fix / Rung-0 self-heal; hydrating it here could fight that handler).
DEFAULT_MAP: list[dict] = [
    {
        "lane": "gemini",
        "ref": "op://Personal/Gemini API Key/credential",
        "env": ["GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"],
        "enabled": True,
        # validity probe: a 200 from the model list means the key authenticates. A suspended
        # Google project answers 403 PERMISSION_DENIED / CONSUMER_SUSPENDED — caught by --verify.
        "verify": {"url": "https://generativelanguage.googleapis.com/v1beta/models",
                   "auth": "query", "param": "key"},
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
        # The static op:// PAT (master-org-token-011726) is REVOKED — --verify reports 401 Bad
        # credentials — and once materialized it SHADOWS the still-valid `gh` keyring (account 4444J99)
        # in every process that sources ~/.limen.env. So mint GH_TOKEN from the live keyring instead:
        # `derive` runs `gh auth token` (with GH_TOKEN/GITHUB_TOKEN unset so gh reads the keyring, not
        # the dead env token), preferred over `ref`; op:// stays the last-resort fallback. Self-heals
        # each beat from a source that already works — closing the gh credential with ZERO human atoms
        # (no PAT re-mint, no un-wired GitHub App). [[credential-durability-organ]] / L-FLEET-CAPACITY.
        "derive": ["gh", "auth", "token"],
        # validity probe: GET /user with the token. A revoked/expired PAT answers 401 Bad credentials.
        "verify": {"url": "https://api.github.com/user", "auth": "bearer"},
    },
    {
        "lane": "cloudflare (wrangler deploy)",
        "ref": "op://Personal/Cloudflare API Token/credential",
        "env": ["CLOUDFLARE_API_TOKEN"],
        "enabled": True,
        # validity probe: the canonical token self-verify endpoint. Invalid → 401 code 1000.
        "verify": {"url": "https://api.cloudflare.com/client/v4/user/tokens/verify", "auth": "bearer"},
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


def derive_value(cmd: list[str], timeout: int = 15) -> str | None:
    """Mint a credential from a LIVE local source (e.g. `gh auth token` → the gh keyring) rather than a
    static op:// secret. Runs with GH_TOKEN/GITHUB_TOKEN scrubbed from the child env so a dead floor
    token can't shadow the keyring gh would otherwise read. Returns the value (never printed) or None on
    any failure — fail-open, so the caller falls back to the op:// ref."""
    child_env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, env=child_env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
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


# --- VALIDITY PROBE ---------------------------------------------------------------------------------
# --check answers "is the env var present?" (cheap, offline). It does NOT answer "does the credential
# still authenticate?" — a stale/revoked/suspended token sits in ~/.limen.env looking ✓ while every
# lane it feeds is dead (the exact failure that masked a suspended Google project + revoked CF/GH
# tokens behind a green --check). --verify closes that gap: it authenticates each materialized cred
# against its own service. Values are used only for the request and never logged.
_SECRET_RX = (
    re.compile(r"AIza[\w\-]{4}[\w\-]+"),          # Google API keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{4}[A-Za-z0-9]+"),  # GitHub tokens
    re.compile(r"api_key:\S+"),                   # Google's error echoes the key inline
)


def _scrub(s: str) -> str:
    """Redact anything key-shaped from a provider message before we print it."""
    for rx in _SECRET_RX:
        s = rx.sub("<redacted>", s)
    return s


def _env_value(key: str) -> str | None:
    """Read the MATERIALIZED value of a key from ENV_FILE — used only to probe validity, never printed.
    Mirrors _env_has (matches both `KEY=` and `export KEY=`) but returns the value."""
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text().splitlines():
        s = line.strip()
        for pre in (f"{key}=", f"export {key}="):
            if s.startswith(pre):
                return s[len(pre):].strip().strip('"').strip("'") or None
    return None


def _probe_reason(body: bytes) -> str:
    """Pull a short, key-free reason out of a provider error body."""
    try:
        d = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return ""
    out = ""
    if isinstance(d, dict):
        err = d.get("error")
        if isinstance(err, dict):  # google style — prefer the machine reason over the prose message
            det = err.get("details")
            reason = det[0].get("reason", "") if isinstance(det, list) and det and isinstance(det[0], dict) else ""
            out = reason or err.get("status", "") or str(err.get("message", ""))
        elif "message" in d:  # github style
            out = str(d.get("message", ""))
        else:  # cloudflare style
            errs = d.get("errors")
            if isinstance(errs, list) and errs and isinstance(errs[0], dict):
                out = f"{errs[0].get('code', '')} {errs[0].get('message', '')}".strip()
    return _scrub(out)[:80]


def probe_cred(entry: dict, value: str, timeout: int = 6) -> tuple[str, str]:
    """Authenticate a credential against its service. Returns (state, detail):
      'valid'        — accepted (HTTP 200)
      'invalid'      — rejected (400/401/403) — a DEAD credential
      'unverifiable' — no probe defined, or no network / service error (fail-open)
    The value is used only to build the request and is never logged."""
    spec = entry.get("verify")
    if not spec:
        return "unverifiable", "no probe defined"
    url, headers = spec["url"], {"User-Agent": "limen-creds-hydrate"}
    if spec.get("auth") == "bearer":
        headers["Authorization"] = f"Bearer {value}"
    elif spec.get("auth") == "query":
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{spec.get('param', 'key')}={value}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return ("valid", "HTTP 200") if r.status == 200 else ("invalid", f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        try:
            reason = _probe_reason(e.read())
        except Exception:
            reason = ""
        if e.code in (400, 401, 403):
            return "invalid", (f"HTTP {e.code}: {reason}".rstrip(": ") if reason else f"HTTP {e.code}")
        return "unverifiable", f"HTTP {e.code} (service error)"
    except Exception as e:  # URLError (no network), timeout, DNS — fail open, do not cry wolf offline
        return "unverifiable", f"unreachable ({type(e).__name__})"


def main() -> int:
    ap = argparse.ArgumentParser(description="Hydrate fleet credentials from 1Password — once minted, never re-logged-in.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="op read → materialize into ~/.limen.env + tool files")
    g.add_argument("--check", action="store_true", help="report PRESENCE of env targets (names only; offline) — not validity")
    g.add_argument("--verify", action="store_true", help="authenticate each materialized cred against its service (VALIDITY) — exit 1 if any is dead")
    g.add_argument("--dry-run", action="store_true", help="print the op://→target plan; NO reads, NO writes (default)")
    args = ap.parse_args()

    cred_map = [e for e in load_map() if e.get("enabled", True)]
    if not cred_map:
        print("creds-hydrate: map is empty (all entries disabled) — nothing to do")
        return 0

    # --verify: authenticate each MATERIALIZED cred against its service. Reads the floor, not op —
    # so it runs without a 1Password session and tests exactly what the lanes inherit. Exit 1 if any
    # enabled cred is definitively rejected (a dead token); offline/service errors stay fail-open.
    if args.verify:
        print(f"creds-hydrate --verify ({ENV_FILE}) — authenticating each materialized credential:")
        any_invalid = False
        for e in cred_map:
            envs = e.get("env", [])
            val = _env_value(envs[0]) if envs else None
            if not val:
                print(f"  ? {e['lane']:28} {','.join(envs) or '(file only)'} — not materialized (run --apply)")
                continue
            state, detail = probe_cred(e, val)
            del val
            mark = {"valid": "✓", "invalid": "✗", "unverifiable": "?"}[state]
            print(f"  {mark} {e['lane']:28} {state.upper()}" + (f" — {detail}" if detail else ""))
            any_invalid = any_invalid or state == "invalid"
        if any_invalid:
            print("creds-hydrate: ✗ = a DEAD credential (presence ✓ is not validity). Re-mint it into its "
                  "op:// item, then `--apply`. Re-run `--verify` to confirm green.")
        return 1 if any_invalid else 0

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
        print("  (presence only — ✓ means the env var is SET, not that it still authenticates. "
              "Run `--verify` to probe validity against each service.)")
        return 0

    apply = args.apply  # default (no flag) == dry-run
    print(f"creds-hydrate {'--apply' if apply else '--dry-run (no reads, no writes — pass --apply to hydrate)'}:")
    hydrated, skipped = 0, 0
    for e in cred_map:
        ref, envs, fspec = e["ref"], e.get("env", []), e.get("file")
        dcmd = e.get("derive")
        targets = ", ".join(envs) + (f" + {fspec['path']}" if fspec else "")
        source = f"`{' '.join(dcmd)}` (op:// fallback)" if dcmd else ref_display(ref)
        if not apply:
            print(f"  plan: {e['lane']:28} {source} -> {targets}")
            continue
        # Prefer a live-minted value (e.g. the gh keyring) over the static op:// secret; fall back to op.
        val = derive_value(dcmd) if dcmd else None
        if not val:
            val = op_read(ref)
        if not val:
            print(f"  SKIP {e['lane']:28} {source} — unreadable (check op signin / the field name)")
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
