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

1Password is OPT-IN, never automatic. By default this organ touches `op` on NO codepath — not the
launchd login agent, not a metabolize beat, not an interactive session — so it can never raise a
Touch-ID/GUI dialog unattended (the app's BiometricsOnly/never-cache policy turns every `op read`
into a fresh biometric prompt, and service accounts — the only promptless `op` — are Business-only,
unavailable on a personal account). The promptless `derive` lanes (gh keyring via `gh auth token`)
hydrate every time. To (re)hydrate the static op:// creds you run `--apply --op` at a terminal once
and accept a single touch — a deliberate act, never a surprise storm.

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
#   gh_secret: optional CI-SECRET sink {"repo": "owner/repo", "name": "SECRET_NAME"} — the same op://
#          value landed as a GitHub Actions secret on the consuming repo. This closes the LAST credential
#          sink the organ didn't reach: a "paste this gh secret" task (the GMAIL_APP_PASSWORD class) is
#          pure plumbing, never a human's hand. A gh_secret-ONLY entry presence-guards via `gh secret
#          list` and only reads+sets when ABSENT (so a beat never touches 1Password for an already-landed
#          secret). Value streams op→gh via stdin, never printed. [[gmail-mutation-cascade-avenues]]
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
        # CI-SECRET sink — the credential the organ didn't used to reach, so it kept landing on a human as
        # a "paste this gh secret" lever (L-GMAIL-CRED). The Gmail app-password ALREADY EXISTS in 1Password;
        # the autonomous mail lane just needs it as a GitHub Actions secret on the consuming repo. That is
        # pure plumbing the organ owns — NOT a his-hand task. gh_secret-only (no env/file): presence-guarded,
        # so a beat does not touch 1Password when the secret is already set. [[gmail-mutation-cascade-avenues]]
        "lane": "gmail (domus CI secret)",
        "ref": "op://Private/gmail-app-pw-2026-06-06/password",
        "gh_secret": {"repo": "organvm/domus", "name": "GMAIL_APP_PASSWORD"},
        "enabled": True,
    },
    {
        # Parked: the Claude token is owned by the credential-race fix + Rung-0 self-heal
        # ([[claude-login-flap-credential-race]] / L-CLAUDE-AUTH). Enable only if that handler is retired.
        # SECOND CONSUMER (2026-07-01): this same LIMEN_CLAUDE_AUTH_TOKEN is the sanctioned env token the
        # budget gauge's `poll` avenue reads (scripts/claude-usage.py av_poll, gated by LIMEN_CLAUDE_POLL=1)
        # to fetch Claude's EXACT server-side weekly usage from rate-limit headers — the trust=measured tier
        # that auto-supersedes the calibrated on-disk bridge. So retiring the login-flap handler and enabling
        # this entry ALSO upgrades the gauge calibrated→measured; NO separate credential to mint (the
        # "one human atom" is this same op:// item, already homed here — never re-recite it in chat).
        # See memory: fleet-budget-gauge-truth.
        "lane": "claude",
        "ref": "op://Personal/Claude/password",
        "env": ["LIMEN_CLAUDE_AUTH_TOKEN"],
        "enabled": False,
    },
    {
        # The Gmail app-password for the autonomous mail lane (C_MAIL keyless drafts/sweep). The secret
        # ALREADY EXISTS in 1Password — nothing to mint. Registered here as the credential's canonical HOME
        # so it never resurfaces as a "generate a credential" chat/lever again. enabled=False because its
        # real CONSUMER is a CI secret, not a local subprocess: the deploy target is the GitHub Actions
        # secret GMAIL_APP_PASSWORD on organvm/domus, landed once via `op read <ref> | gh secret set
        # GMAIL_APP_PASSWORD -R organvm/domus` (value streams op→gh, never on screen). Flip to True only if
        # a local lane is ever switched to read GMAIL_APP_PASSWORD from ~/.limen.env directly.
        # See L-GMAIL-CRED / issue #261, the Wall index #320, memory: gmail-mutation-cascade-avenues.
        "lane": "gmail (C_MAIL app-password)",
        "ref": "op://Private/gmail-app-pw-2026-06-06/password",
        "env": ["GMAIL_APP_PASSWORD"],
        "enabled": False,
    },
    {
        # The ianva cloud-connector bearer token (the one re-auth a local gateway physically cannot fix —
        # claude.ai runs that OAuth from Anthropic's cloud). LOCALLY MINTED, not a 1Password secret: created
        # once via `python3 -m ianva.cli bearer --new` and landed in ~/.limen.env via
        # `scripts/set-credential.sh IANVA_BEARER_TOKEN` (silent prompt). NOT derived/refreshed here because
        # `bearer --new` ROTATES it (non-idempotent) — hydrating would break the live connector. Registered
        # so the credential INFORMATION has a canonical home (env-var name + provenance); the activation is
        # L-IANVA-CLOUD / issue #263 (Wall index #320). The `ref` is a placeholder home should a stable
        # op:// item ever be minted; enable only then. See memory: ianva-mcp-doorway.
        "lane": "ianva (cloud connector bearer)",
        "ref": "op://Personal/IANVA Bearer Token/credential",
        "env": ["IANVA_BEARER_TOKEN"],
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


# Where a 1Password service-account token lives if the user mints one. Kept OUTSIDE the repo
# (chmod 600, never committed) so the secret never lands in git. Override with LIMEN_OP_SA_TOKEN_FILE.
SA_TOKEN_FILE = Path(os.environ.get(
    "LIMEN_OP_SA_TOKEN_FILE", str(Path.home() / ".config" / "op" / "service-account-token")))


def load_service_account_token() -> None:
    """If OP_SERVICE_ACCOUNT_TOKEN isn't already in the env, hydrate it from SA_TOKEN_FILE.
    A service-account token is the ONLY way `op read` authenticates with ZERO interactive prompt —
    the desktop-app integration always raises a Touch-ID/GUI dialog when locked, which is exactly
    the prompt storm this organ must not trigger from the daemon (launchd + every metabolize beat)."""
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return
    try:
        tok = SA_TOKEN_FILE.read_text().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return
    if tok:
        os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = tok


def op_can_read_silently() -> bool:
    """True only when `op read` can succeed WITHOUT raising an interactive prompt — i.e. a
    service-account token (or a Connect server) is configured. Under the desktop-app integration
    this is False: a locked vault pops Touch-ID, which is the dialog we refuse to trigger unattended."""
    return bool(
        os.environ.get("OP_SERVICE_ACCOUNT_TOKEN")
        or (os.environ.get("OP_CONNECT_HOST") and os.environ.get("OP_CONNECT_TOKEN"))
    )


def running_interactively() -> bool:
    """A human is at a terminal — an `op` Touch-ID prompt is then expected and wanted."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (ValueError, OSError):
        return False


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


def have_gh() -> bool:
    return shutil.which("gh") is not None


def gh_secret_present(repo: str, name: str, timeout: int = 15) -> bool | None:
    """Is a GitHub Actions secret already SET on the repo? `gh secret list` returns NAMES only (never a
    value). Returns True/False, or None when gh is unavailable / the call fails (fail-open: 'unknown')."""
    if not have_gh():
        return None
    try:
        r = subprocess.run(
            ["gh", "secret", "list", "-R", repo],
            capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    names = {ln.split()[0] for ln in (r.stdout or "").splitlines() if ln.split()}
    return name in names


def gh_secret_set(repo: str, name: str, value: str, timeout: int = 30) -> bool:
    """Set a GitHub Actions secret. The value is piped via STDIN (never in argv, never on screen) and
    never logged. Returns True on success, False on any failure (fail-open — logged by NAME only)."""
    if not have_gh():
        return False
    try:
        r = subprocess.run(
            ["gh", "secret", "set", name, "-R", repo],
            input=value, capture_output=True, text=True, timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0


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
    ap.add_argument("--op", action="store_true",
                    help="ALSO read op:// lanes — may raise a 1Password Touch-ID/GUI prompt. OFF by default: "
                         "without it, only promptless lanes (derive, e.g. the gh keyring) hydrate, so NO dialog "
                         "ever fires from a daemon beat or an interactive session. Pass it deliberately, at a "
                         "terminal, when you want to (re)hydrate the op:// creds and accept one biometric touch.")
    args = ap.parse_args()

    load_service_account_token()  # hydrate OP_SERVICE_ACCOUNT_TOKEN from its file if present → silent `op read`

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
            gspec = e.get("gh_secret")
            if not envs and gspec:
                # A CI-secret sink isn't probeable here — the value isn't materialized on this floor and
                # GitHub never returns a secret's value. Presence/landing is reported by --apply. Neutral,
                # network-free, never fails the beat.
                print(f"  · {e['lane']:28} CI-secret gh:{gspec['repo']}:{gspec['name']} — managed on --apply (value not readable back)")
                continue
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
            gspec = e.get("gh_secret")
            if not envs and gspec:
                print(f"  · {e['lane']:28} {ref_display(e['ref'])} -> gh:{gspec['repo']}:{gspec['name']} (CI secret — checked on --apply)")
                continue
            present = all(_env_has(k) for k in envs) if envs else False
            mark = "✓" if present else "✗"
            print(f"  {mark} {e['lane']:28} {ref_display(e['ref'])} -> {','.join(envs) or '(file only)'}")
        print("  (presence only — ✓ means the env var is SET, not that it still authenticates. "
              "Run `--verify` to probe validity against each service.)")
        return 0

    apply = args.apply  # default (no flag) == dry-run

    # ── OP IS OPT-IN — the root-to-leaf fix for the recurring 1Password Touch-ID/GUI dialogs ──────
    # ROOT CAUSE (confirmed from 1Password's own daemon logs): the app's unlock policy is
    # `BiometricsOnly` with "Ask Again After: -1" (never cache) — so EVERY `op read` re-locks
    # immediately and demands a fresh Touch-ID. Nothing is cached, so each access is its own prompt.
    # On personal accounts a service-account token (the only promptless `op`) is NOT available
    # (Business-only), so there is no token path to make `op read` silent here.
    # The earlier gate still let `op read` fire whenever stdin/stdout was a TTY — but the daemon's
    # metabolize beat and ~10 concurrent interactive sessions ALL present as TTYs, so that clause WAS
    # the storm (20+ biometric prompts in rapid succession). The cure: `op` is now strictly OPT-IN.
    # It runs ONLY with an explicit `--op` flag (a human deliberately accepting one touch) or a real
    # service-account/Connect token. Default: never touch 1Password — so no daemon beat and no
    # interactive session can pop a dialog. The promptless `derive` lanes (gh keyring via `gh auth
    # token`) hydrate every time regardless; only the op:// fallback is gated. PER-ENTRY, not a blanket
    # skip. [[macos-tcc-gatekeeper-dialogs-solved]]
    op_ok = op_can_read_silently() or args.op
    if apply and not op_ok:
        hint = ("re-run with `--op` at a terminal to hydrate them (accepts one Touch-ID)."
                if running_interactively()
                else "they hydrate only with `--op` or a service-account token.")
        print("creds-hydrate: op:// lanes SKIPPED (opt-in) — not touching 1Password, so no Touch-ID/GUI "
              f"prompt fires. Promptless `derive` lanes still hydrate. To (re)hydrate the op:// creds, {hint}")

    print(f"creds-hydrate {'--apply' if apply else '--dry-run (no reads, no writes — pass --apply to hydrate)'}:")
    hydrated, skipped = 0, 0
    for e in cred_map:
        ref, envs, fspec = e["ref"], e.get("env", []), e.get("file")
        dcmd = e.get("derive")
        gspec = e.get("gh_secret")
        targets = ", ".join(envs) + (f" + {fspec['path']}" if fspec else "")
        if gspec:
            targets += (" + " if targets else "") + f"gh:{gspec['repo']}:{gspec['name']}"
        source = f"`{' '.join(dcmd)}` (op:// fallback)" if dcmd else ref_display(ref)
        if not apply:
            print(f"  plan: {e['lane']:28} {source} -> {targets}")
            continue
        # gh_secret-ONLY entry (no env/file): if the CI secret is already set, skip — no value read, no
        # re-push, and crucially NO 1Password touch. The organ keeps it landed without a per-beat biometric
        # prompt; it only reads+sets when the secret is ABSENT (and op is permitted / the value derivable).
        if gspec and not envs and not fspec and gh_secret_present(gspec["repo"], gspec["name"]) is True:
            print(f"  ✓ {e['lane']:28} -> gh:{gspec['repo']}:{gspec['name']} (already set)")
            hydrated += 1
            continue
        # Prefer a live-minted value (e.g. the gh keyring) over the static op:// secret; fall back to
        # op ONLY when op can read without a prompt (op_ok) — else the op:// fallback is skipped, no GUI.
        val = derive_value(dcmd) if dcmd else None
        if not val and op_ok:
            val = op_read(ref)
        if not val:
            why = ("unreadable (check op signin / the field name)" if op_ok
                   else "op:// read skipped — no promptless 1Password auth (fail-open, no Touch-ID)")
            print(f"  SKIP {e['lane']:28} {source} — {why}")
            skipped += 1
            continue
        for k in envs:
            write_env(k, val)
        wrote_file = write_tool_file(fspec, val) if fspec else None
        gh_set = gh_secret_set(gspec["repo"], gspec["name"], val) if gspec else None
        del val  # drop the secret from memory promptly
        parts = []
        if envs:
            parts.append(",".join(envs))
        if wrote_file:
            parts.append(wrote_file)
        if gspec:
            parts.append(f"gh:{gspec['repo']}:{gspec['name']}" + ("" if gh_set else " (set FAILED)"))
        print(f"  ✓ {e['lane']:28} -> {' + '.join(parts)}")
        hydrated += 1

    if apply:
        print(f"creds-hydrate: {hydrated} hydrated, {skipped} skipped. "
              f"Apply to the running daemon: launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat")
        if skipped:
            print("  (skipped = `op` couldn't read it: unlock with `op signin`, then re-run with `--op`, "
                  "or fix the field in the map. Never a vendor re-login — only the 1Password unlock.)"
                  if op_ok else
                  "  (skipped = op:// lanes are opt-in and `--op` was not passed — this is the NO-PROMPT "
                  "default. Promptless `derive` lanes hydrated. Pass `--op` at a terminal to hydrate op://.)")
    return 0


def ref_display(ref: str) -> str:
    """op://vault/item/field — safe to print (it's a path, not a secret)."""
    return ref


if __name__ == "__main__":
    raise SystemExit(main())
