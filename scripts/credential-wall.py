#!/usr/bin/env python3
"""credential-wall.py — generate the canonical secret/credential Wall (pinned issue #320).

Anthony's standing rule (2026-06-25): "anything involving tokens, secrets, APIs, logins, env
variables — that's not our burden — register it appropriately and pin it on the GitHub wall,
not in a chat." The pinned issue #320 already states it is "regenerated from `DEFAULT_MAP` in
code — never hand-maintained." That generator did not exist; its table was hand-written and had
drifted (the CI / runtime secrets were never indexed). THIS is the missing generator.

Every token / secret / API key / login / env-var atom in the system is indexed here from its
*source of truth*, never recited at a human:

  * Hydration lanes  — derived LIVE from `scripts/creds-hydrate.py` `DEFAULT_MAP` (the loader),
                       so the structural columns (env var, provenance, probe, parked-state) can
                       never disagree with the code that actually hydrates them.
  * CI / runtime     — GitHub Actions secrets, GCP Secret Manager, and the headless 1Password
    secrets            service-account token. Declared below (names + homes only).

VALUES NEVER TOUCH THE REPO. This script prints only env-var NAMES, `op://` item paths, and the
homes — exactly what `creds-hydrate.py` already exposes behind its `_scrub()` firewall. There is
no path here that reads a secret value.

  python3 scripts/credential-wall.py            # print the generated Wall body (default)
  python3 scripts/credential-wall.py --check    # PREDICATE: exit 1 if any secret atom lacks a home
  python3 scripts/credential-wall.py --sync      # write the body into the pinned Wall issue (#320)

Exit 0 from --check  ⟺  every credential/secret in use has a registered home (nothing hangs in a
chat or a head).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


WALL_ISSUE = _positive_int_env("LIMEN_CRED_WALL_ISSUE", 320)
WALL_MARKER = "<!-- wall:credentials -->"


def _load_default_map() -> list[dict]:
    """Import DEFAULT_MAP from the hyphenated loader script (the single source of truth)."""
    p = ROOT / "scripts" / "creds-hydrate.py"
    spec = importlib.util.spec_from_file_location("creds_hydrate", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return list(getattr(m, "DEFAULT_MAP", []))


# Editorial layer — per-lane issue pointer + whose-hand. The STRUCTURAL columns (env var, derive,
# enabled, probe) come live from DEFAULT_MAP; only this low-churn editorial note lives here, so the
# table stays honest about who must act without re-deriving it from prose each session.
LANE_META: dict[str, dict] = {
    "gemini": {"issue": "#265", "hand": "his — account-gated re-mint (downstream of #182)"},
    "gh/copilot/jules": {"issue": "—", "hand": "none — keyring-derived, self-heals every beat (#251)"},
    "cloudflare (wrangler deploy)": {"issue": "—", "hand": "none — token valid + headless via cf-wrangler.sh (#518); phantom re-mint lever retired 2026-07-01"},
    "cloudflare (a-i-chat--exporter CI secret)": {"issue": "—", "hand": "none — organ-owned gh_secret sink; lands once op can read (gated on the non-blocking SA vault-grant on #320)"},
    "gmail (C_MAIL app-password)": {"issue": "#261", "hand": "reroutable — `op read … | gh secret set`"},
    "ianva (cloud connector bearer)": {"issue": "#263", "hand": "his — claude.ai account edit"},
    "claude": {"issue": "—", "hand": "none — owned by the Rung-0 credential-race self-heal"},
    "codex/opencode (openai)": {"issue": "—", "hand": "none — codex authenticates via ChatGPT OAuth"},
    "opencode (openrouter)": {"issue": "—", "hand": "none — free model / own auth"},
    "vox (elevenlabs voice clone)": {"issue": "#898", "hand": "his — vendor MINT (create ElevenLabs API key); parked enabled=False until minted (vox mock is default)"},
}

# CI / runtime secrets — NOT hydration lanes; their home is GitHub Actions / GCP Secret Manager /
# a local file, never DEFAULT_MAP. Declared here (names + homes only, NEVER values). `home` must be
# non-empty for every entry — that is what --check enforces. These were in active use but were
# absent from the Wall before this generator existed.
CI_SECRETS: list[dict] = [
    {
        "name": "LIMEN_API_TOKEN",
        "home": "GitHub Actions secret (set) + GCP Secret Manager `limen-api-token:latest`",
        "used": "`web/api/main.py` owner bearer; dashboard deploy runtime verification",
        "hand": "none — set",
        "issue": "—",
    },
    {
        "name": "LIMEN_CLIENT_TOKEN",
        "home": "GitHub Actions secret (set) + GCP Secret Manager `limen-client-token:latest`",
        "used": "`web/api/main.py` client bearer; dashboard deploy runtime verification",
        "hand": "none — set",
        "issue": "—",
    },
    {
        "name": "GCP_SA_KEY",
        "home": "GitHub Actions secret (gated, optional)",
        "used": "`google-github-actions/auth` → Firebase Hosting + Cloud Run deploy",
        "hand": "optional — unset ⇒ Firebase deploys manually, Cloud Run skipped (live runtime = Cloudflare Worker)",
        "issue": "—",
    },
    {
        "name": "WARP_API_KEY",
        "home": "GitHub Actions secret + local `~/.limen.env` (optional)",
        "used": "`cli/src/limen/capacity.py` + heartbeat warp/oz lane",
        "hand": "optional — unset ⇒ warp/oz lane off",
        "issue": "—",
    },
    {
        "name": "OP_SERVICE_ACCOUNT_TOKEN",
        "home": "file `~/.config/op/service-account-token` (1Password service account) + `~/.zshenv` export",
        "used": "`creds-hydrate.py` headless `op read` + `--sweep-all` (fleet); `~/.zshenv` exports it so every shell's `op` is promptless too (no Touch-ID anywhere)",
        "hand": "INSTALLED ✓ — op is promptless forever (fleet + every shell), verified via `op whoami`. Scope residual: the saved SA token carries zero vault grants, so op *re-reads* return nothing — the fleet runs off the already-valid `~/.limen.env` (see `creds-hydrate.py --verify`). For op itself to re-read/rotate secrets (true full sweep), grant the SA read access to the vault(s) holding them in the 1Password console (service accounts read shared vaults; personal-vault items may need moving into one). Non-blocking.",
        "issue": "#288",
    },
]

_HEADER = """\
**This is the canonical index for everything involving a token, secret, API key, login, or env var.** \
None of it lives in a chat or in anyone's head. Two homes, both on GitHub:

- **The information** — what each credential is, its `op://` provenance, its env-var name, its validity \
probe — lives in code: [`scripts/creds-hydrate.py`](https://github.com/organvm/limen/blob/main/scripts/creds-hydrate.py) \
→ `DEFAULT_MAP`. Adding a vendor = adding **one entry**, never a login step. **Values never touch the \
repo** — only `op://` item paths + env-var names, behind the `_scrub()` PII firewall. Actual secrets \
live in 1Password; account/health PII lives off-repo at `700`.
- **The actions** — each remaining human or reroutable atom — live as the `credential`-labelled issues. \
Filter the live set anytime: <https://github.com/organvm/limen/labels/credential>.

**Verify the whole estate:** `python3 scripts/creds-hydrate.py --verify` (exit `0` = every lane \
authenticates). **Hydration flow:** 1Password → `~/.limen.env` (chmod `600`, never committed) → every \
`metabolize.sh` beat + a 30-min launchd agent (`com.limen.creds-hydrate.plist`)."""

_FOOTER = """\
---

_**Machine-generated** — `python3 scripts/credential-wall.py --sync` regenerates this body from \
`DEFAULT_MAP` (hydration lanes) + the declared CI/runtime catalog. The structural columns are derived \
live from the loader; **if this table and the code ever disagree, the code wins.** The `Probe` column \
is structural (has a `--verify` probe / parked / self-healing) — run `creds-hydrate.py --verify` for \
live pass/fail. Pinned. Discussions are disabled on this repo, so this pinned issue (plus the \
`credential` label filter) is the Wall surface._"""


def wall_body() -> str:
    dm = _load_default_map()
    lines = [_HEADER, "", "## Hydration lanes — live from `creds-hydrate.py` `DEFAULT_MAP`", ""]
    lines += ["| Lane | Home | Env var(s) | Probe | Whose hand | Issue |",
              "|---|---|---|---|---|---|"]
    for e in dm:
        lane = str(e.get("lane", "?"))
        if not e.get("enabled"):
            probe = "◻️ parked"
        elif e.get("derive"):
            probe = "✅ derived (self-heals)"
        elif e.get("verify"):
            probe = "🔎 `--verify` probe"
        else:
            probe = "— no probe"
        home = "`DEFAULT_MAP`"
        if e.get("derive"):
            home += f" (derive: `{' '.join(e['derive'])}`)"
        if e.get("file"):
            home += " + tool file"
        env = ", ".join(f"`{x}`" for x in e.get("env", [])) or "—"
        meta = LANE_META.get(lane, {})
        lines.append(f"| {lane} | {home} | {env} | {probe} | {meta.get('hand', '—')} | {meta.get('issue', '—')} |")

    lines += ["", "## CI / runtime secrets — GitHub Actions · GCP Secret Manager · 1Password SA", ""]
    lines += ["| Secret | Home | Used by | Whose hand | Issue |",
              "|---|---|---|---|---|"]
    for s in CI_SECRETS:
        lines.append(f"| `{s['name']}` | {s['home']} | {s['used']} | {s['hand']} | {s['issue']} |")

    lines += ["", _FOOTER, "", WALL_MARKER]
    return "\n".join(lines)


def check() -> int:
    """Predicate: every credential/secret in use has a registered home. Exit 0 ⟺ clean."""
    homeless: list[str] = []
    for e in _load_default_map():
        if not (e.get("ref") or e.get("derive")):
            homeless.append(f"DEFAULT_MAP lane '{e.get('lane')}' has neither `ref` nor `derive` — cannot hydrate")
    for s in CI_SECRETS:
        if not str(s.get("home", "")).strip():
            homeless.append(f"CI secret '{s.get('name')}' has no `home`")
    if homeless:
        print("✗ credential-wall: secret atoms with no registered home:")
        for h in homeless:
            print(f"   - {h}")
        return 1
    n = len(_load_default_map()) + len(CI_SECRETS)
    print(f"✓ credential-wall: all {n} secret atoms registered (every token/secret/login/env has a home)")
    return 0


def census() -> dict:
    """Counts-only public census; no env names, homes, secret names, or issue prose."""
    default_map = _load_default_map()
    return {
        "wall_issue": WALL_ISSUE,
        "hydration_lanes": len(default_map),
        "enabled_lanes": sum(1 for entry in default_map if entry.get("enabled")),
        "derived_lanes": sum(1 for entry in default_map if entry.get("derive")),
        "probed_lanes": sum(1 for entry in default_map if entry.get("verify")),
        "parked_lanes": sum(1 for entry in default_map if not entry.get("enabled")),
        "ci_runtime_secrets": len(CI_SECRETS),
        "homeless_secret_atoms": sum(1 for entry in default_map if not (entry.get("ref") or entry.get("derive")))
        + sum(1 for secret in CI_SECRETS if not str(secret.get("home", "")).strip()),
    }


def sync() -> int:
    body = wall_body()
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body)
        path = f.name
    subprocess.run(["gh", "issue", "edit", str(WALL_ISSUE), "--body-file", path], check=True)
    # Ensure it stays pinned; pinning an already-pinned issue is a no-op error → tolerate it.
    subprocess.run(["gh", "issue", "pin", str(WALL_ISSUE)], capture_output=True, text=True)
    print(f"✓ synced + pinned the credential Wall → issue #{WALL_ISSUE}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit 1 if any secret atom lacks a home")
    g.add_argument("--sync", action="store_true", help="write the generated body into issue #320 + pin it")
    g.add_argument("--census", action="store_true", help="print counts-only public census JSON")
    args = ap.parse_args()
    if args.check:
        return check()
    if args.sync:
        return sync()
    if args.census:
        print(json.dumps(census(), indent=2, sort_keys=True))
        return 0
    print(wall_body())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
