#!/usr/bin/env python3
"""creds-hydrate.py — the credential HYDRATION organ. One source of truth, auto-applied everywhere.
# Gate authority: organs/governance/PUBLICATION-POLICY.md — convergence table row 1 (_SECRET_RX).
# The `_SECRET_RX` pattern is mirrored in scripts/publication-policy.py as the canonical firewall.
# This file owns credential HYDRATION (minting + verifying); the publication policy owns
# DISPOSITION (remove/redact/publish). Changes to what constitutes a secret shape start in the
# publication policy's _SECRET_RX, not here — mirror back if the shape changes.

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
  1. read promptless sources each beat; read static op:// credentials only with explicit `--op`
     or a promptless service-account/Connect setup,
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
  - container/launchd/com.limen.creds-hydrate.plist — a launchd login agent
    (arming is your hand, like the watchdog).
  - route.py capacity census — the VERIFIER: after hydration every lane should read "up".

Fail-open by contract: any `op` error skips that one credential (logged by NAME only) and never crashes
the beat. Read-only by default (`--dry-run` prints the op://→target plan with NO secret reads); writes
only with `--apply`, and static op:// reads still require `--op` unless promptless op auth exists.

PRESENCE is not VALIDITY. `--check` (and route.py's capacity census) only ask "is the env var set?" —
a stale/revoked/suspended token sits in ~/.limen.env looking ✓ while every lane it feeds is dead. The
durable predicate is `--verify`: it authenticates each materialized credential against its own service
(gh /user, cloudflare /accounts, gemini /models) and exits non-zero on a dead token. Run it after
--apply and on a cadence — a green --check over dead creds is the precise way "done" silently rots.

Usage:
  python3 scripts/creds-hydrate.py --dry-run     # print the plan (no reads, no writes) — default
  python3 scripts/creds-hydrate.py --check       # PRESENCE of env targets (NAMES only; offline) — not validity
  python3 scripts/creds-hydrate.py --verify      # VALIDITY — authenticate each cred against its service; exit 1 if any dead
  python3 scripts/creds-hydrate.py --apply        # promptless lanes only; no Touch-ID / op prompt
  python3 scripts/creds-hydrate.py --apply --op   # deliberate op:// read → materialize static creds
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
        "verify": {"url": "https://generativelanguage.googleapis.com/v1beta/models", "auth": "query", "param": "key"},
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
        # Parked — PHANTOM env var, retired 2026-06-25 (same investigation). OpenCode discovers its
        # currently reachable capabilities from `opencode models --verbose`; an interactive
        # `opencode auth login` may change that live catalog by writing OpenCode's own auth.json.
        # Neither reachability nor pricing is inferred from a model name or a fixed free/paid ladder.
        # No fleet code reads OPENROUTER_API_KEY (grep of cli/src: zero consumers), and the attempted
        # 1Password reference never resolved. Enable only if OpenCode is deliberately configured to
        # consume this environment variable; its own interactive authentication is a separate lever.
        "lane": "opencode (openrouter)",
        "ref": "op://Personal/OpenRouter API Key/credential",
        "env": ["OPENROUTER_API_KEY"],
        "enabled": False,
    },
    {
        # Faculty-application portal login (NEOGOV / GovernmentJobs.com, e.g. tenant cfkedu =
        # College of the Florida Keys). Read by application-pipeline's neogov_submit.py --assist to
        # log in and fill the multi-page form to the brink (the operator clicks Submit — the engine
        # never auto-submits a counterparty form). A VENDOR LOGIN the organ cannot mint: it stays
        # enabled=False until the operator authenticates once and lands the account in op://; the
        # organ then hydrates NEOGOV_USERNAME/PASSWORD every beat, value never printed. Username +
        # password are distinct values -> two entries. [[credential-durability-organ]]
        "lane": "neogov/governmentjobs (faculty apply) — username",
        "ref": "op://Personal/GovernmentJobs cfkedu/username",
        "env": ["NEOGOV_USERNAME", "GOVERNMENTJOBS_USERNAME"],
        "enabled": False,
    },
    {
        "lane": "neogov/governmentjobs (faculty apply) — password",
        "ref": "op://Personal/GovernmentJobs cfkedu/password",
        "env": ["NEOGOV_PASSWORD", "GOVERNMENTJOBS_PASSWORD"],
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
        # gh_secret sink: deploy.yml's dashboard Cloudflare Pages step (the derived owned rail after
        # the Firebase/GCP road-not-taken) reads this repo secret — the organ lands it, never a paste.
        "gh_secret": {"repo": "organvm/limen", "name": "CLOUDFLARE_API_TOKEN"},
        "enabled": True,
        # validity probe: GET /accounts. This works for BOTH token kinds — the earlier
        # /user/tokens/verify endpoint is USER-token-only and returns code 1000 "Invalid API
        # Token" for an ACCOUNT-scoped token (e.g. "Edit Cloudflare Workers"), a FALSE NEGATIVE
        # that wrongly flagged our valid deploy token dead and spawned a phantom re-mint lever
        # (L-CLOUDFLARE-DEPLOY). /accounts returns 200 for any live token, 401/403 for a revoked
        # one — the correct validity semantics for the generic probe. Fixed 2026-07-01.
        "verify": {"url": "https://api.cloudflare.com/client/v4/accounts", "auth": "bearer"},
    },
    {
        # SUPERSEDED + PARKED (enabled=False) — kept ONLY as the worked example of the gh_secret multi-sink
        # form (one op:// value fanned to many repos' CI secrets), NOT as a live or pending credential.
        # media-ark's deploy host was DERIVED to Cloudflare Containers (logic-over-inherited-config): the GCP
        # path was a prior session cloning limen's OWN deploy-api.yml, which is itself a no-op (limen's live
        # API is the CF Worker limen-runtime), dragging in a dead GCP_SA_KEY for a credential that exists
        # NOWHERE. The deploy credential is instead one already OWNED — CLOUDFLARE_API_TOKEN (the cloudflare
        # lane above), proven headless this session. So this GCP lane is not "waiting to be minted"; it is the
        # road-not-taken. The remaining atom is NOT a GCP SA — it is a ~$5/mo Workers Paid toggle on the owned
        # CF account, recorded as lever L-MEDIA-ARK-HOST (#535), sequenced behind revenue. Do NOT flip this
        # entry True unless the host decision is ever explicitly REVERSED back to GCP (unlikely). Parked so no
        # beat SKIP-noises a phantom ref. [[media-suite-convergence]] [[logic-over-inherited-config]]
        # [[credential-durability-organ]] [[his-hand-tasks-hang-in-permanent-registry]]
        "lane": "gcp (cloud run deploy SA) — SUPERSEDED by cloudflare, retained as multi-sink example",
        "ref": "op://Personal/GCP Deploy SA/credential",
        "gh_secret": [
            {"repo": "organvm/media-ark", "name": "GCP_SA_KEY"},
            {"repo": "organvm/limen", "name": "GCP_SA_KEY"},
        ],
        "enabled": False,
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
        # CI-SECRET sink — LAVREA (4444J99/laurea, the computed-laurels organ) recomputes percentile
        # placements daily in Actions; the default GITHUB_TOKEN cannot see private org memberships, so
        # without a user token the snapshot collapses (5 repos, 0 orgs) and the composite claim deletes
        # itself. The workflow reads LAUREA_TOKEN. Same promptless source as the gh/copilot/jules lane:
        # mint from the live `gh` keyring (derive preferred; the static op:// PAT is the revoked
        # last-resort, retained for shape parity). gh_secret-only: presence-guarded, so the beat only
        # reads+sets when the secret is absent. [[credential-durability-organ]]
        "lane": "laurea (computed-laurels CI secret)",
        "ref": "op://GitHub-Tokens/master-org-token-011726/password",
        "derive": ["gh", "auth", "token"],
        "gh_secret": {"repo": "4444J99/laurea", "name": "LAUREA_TOKEN"},
        "enabled": True,
    },
    {
        # CI-SECRET sink (ORG-level) — the multi-agent PR-review engine: claude-review.yml (fanned out
        # across the estate via sync-marketplace-config.py) reads secrets.ANTHROPIC_API_KEY in every
        # repo. ONE org secret with visibility=all lands it estate-wide — never a 307-repo fan-out,
        # never a paste. gh_secret-only: presence-guarded, so once set the beat never touches op again.
        # ARMING: mint an API key at console.anthropic.com into the op:// item below (a vendor act
        # gated behind the card hold #182 — the Anthropic spend limit is frozen on the same card);
        # until then --apply prints an honest SKIP each beat, which is the owed-work signal.
        "lane": "anthropic (org CI review key)",
        "ref": "op://Personal/Anthropic API Key/credential",
        "gh_secret": {"org": "organvm", "name": "ANTHROPIC_API_KEY", "visibility": "all"},
        "enabled": True,
    },
    {
        # CI-SECRET sink — the a-i-chat--exporter Cloudflare Pages deploy (GitHub Actions) needs
        # CLOUDFLARE_API_TOKEN as a repo secret. The token ALREADY EXISTS (the cloudflare lane above owns
        # op://Personal/Cloudflare API Token/credential); the exporter repo correctly DEFERS — it expects
        # the CI secret rather than documenting `wrangler login`. Landing that secret is pure plumbing the
        # organ owns, NOT a his-hand "paste this gh secret" task — the exact wrangler-login disease, cured
        # at the source. gh_secret-only (no env/file): presence-guarded, so once the secret is set the beat
        # checks `gh_secret_present` and never touches 1Password again. CLOUDFLARE_ACCOUNT_ID is NOT a
        # secret (it appears in dashboard URLs / wrangler.toml) — it belongs in the repo's own config, not
        # here. Lands once op can read the value (gated only on the non-blocking SA vault-grant on #320).
        # [[wrangler-login-and-op-ping-disease]] [[gmail-mutation-cascade-avenues]]
        "lane": "cloudflare (a-i-chat--exporter CI secret)",
        "ref": "op://Personal/Cloudflare API Token/credential",
        "gh_secret": {"repo": "organvm/a-i-chat--exporter", "name": "CLOUDFLARE_API_TOKEN"},
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
        # The Gmail app-password for the autonomous mail lane (C_MAIL keyless drafts/sends). The secret
        # ALREADY EXISTS in 1Password — nothing to mint. Registered here as the credential's canonical HOME
        # so it never resurfaces as a "generate a credential" chat/lever again.
        # ENABLED 2026-07-14: the pre-written condition on line "flip to True only if a local lane reads
        # GMAIL_APP_PASSWORD from ~/.limen.env directly" is now SATISFIED — the keyed headless draft path
        # (UMA draft_writer._select_saver → IMAPProvider.create_draft, and send_drafts._smtp_creds) reads
        # GMAIL_APP_PASSWORD from the env this lane hydrates. This designs out the macOS TCC Automation grant
        # (lever L-MAIL-AUTOMATION-GRANT #960) for draft-save: a beat persists drafts to [Gmail]/Drafts over
        # IMAP with no GUI tap. The separate domus gh_secret lane above still lands the CI secret. SENDING
        # stays disarmed (LIMEN_MAIL_SEND=0) regardless — this only enables headless drafts.
        # See L-GMAIL-CRED / issue #261, the Wall index #320, memory: gmail-mutation-cascade-avenues.
        "lane": "gmail (C_MAIL app-password)",
        "ref": "op://Private/gmail-app-pw-2026-06-06/password",
        "env": ["GMAIL_APP_PASSWORD"],
        "enabled": True,
        # REQUIRED for the autonomous mail organ: without it the keyed IMAP path (draft-save
        # AND gmail_imap_sweep archive) cannot authenticate, so nothing auto-cleans Gmail. A
        # `required` lane that fails to materialize is a LOUD --verify failure (not a silent
        # skip) — the beat log surfaces it every beat. If this is red, the op:// item is not
        # readable by the service account (vault grant / field name — Wall #320, issue #261).
        "required": True,
    },
    {
        # The Gmail ACCOUNT ADDRESS for the keyed mail lane — NOT a secret (it appears in every From: header),
        # but the keyed path needs it: draft_writer._select_saver and send_drafts._smtp_creds both require a
        # user (IMAP_USER/GMAIL_USER) alongside the app-password, or they fail closed and fall back to the
        # TCC-gated AppleScript path. Routed from the SAME 1Password item's `username` field so the address
        # never lands as a hardcode in this PUBLIC file (derive-never-pin + PII-clean): only the op:// ref is
        # in code; the value materializes solely into ~/.limen.env on the daemon. Fail-open: if the item has
        # no username field, the lane simply doesn't hydrate (surfaced by --verify in the beat log, never a
        # chat task) and the keyed path stays dormant — nothing breaks. [[gmail-mutation-cascade-avenues]]
        "lane": "gmail (C_MAIL account address)",
        "ref": "op://Private/gmail-app-pw-2026-06-06/username",
        "env": ["GMAIL_USER"],
        "enabled": True,
        # REQUIRED alongside the app-password — the keyed path needs the account address too.
        "required": True,
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
    {
        # VOX program (organvm/vox) — the ElevenLabs API key vox's real clone/synth engine reads as
        # ELEVEN_API_KEY when VOX_ENGINE != mock. Registered here so the credential's INFORMATION has its
        # canonical home (env-var name + op:// provenance); VOX-4's deliverable IS this registration, not a
        # login step. enabled=False by design: vox + in-my-head ship VOX_ENGINE=mock by default, so nothing
        # in the running fleet needs the key today — parking it keeps --verify from reddening the beat over
        # an un-minted vendor key (same treatment as the openai/openrouter/claude/ianva parked lanes). The
        # one remaining atom is a genuine vendor MINT the organ cannot perform (create the ElevenLabs
        # account + API key) — homed as credential-labelled issue #898 + the Wall index #320, never recited
        # in chat. Activation: mint the key into `op://Personal/ElevenLabs API Key`, flip enabled=True, and
        # add a --verify probe against ElevenLabs (GET https://api.elevenlabs.io/v1/user, `xi-api-key`
        # header — extend the probe auth modes if needed; today's are query/bearer). See spec/vox-program.md.
        "lane": "vox (elevenlabs voice clone)",
        "ref": "op://Personal/ElevenLabs API Key/credential",
        "env": ["ELEVEN_API_KEY"],
        "enabled": False,
    },
    {
        # PENDING VENDOR MINT — Lemon Squeezy store ID for the a-i-chat--exporter Pro-tier checkout
        # rail. LEMONSQUEEZY_STORE_ID is NOT a secret (it appears in public checkout URLs), but the
        # site build reads it as an env-var so placeholders never ship to production. Declared here as
        # a pending slot so the beat surfaces its absence via --verify (required=False, so the absence
        # is a warn not a hard failure) rather than needing a human-authored env file edit.
        # Human atom: create a Lemon Squeezy store at lemonsqueezy.com, complete KYC/payout setup,
        # then mint the Store ID into `op://Personal/Lemon Squeezy Store ID/credential`. The organ
        # lands it into ~/.limen.env (LEMONSQUEEZY_STORE_ID) on the next beat. Homed on lever
        # L-REVENUE-ACCT / issue #1090. Ko-fi slug (4444j99) is a PUBLIC identifier — already live in
        # FUNDING.yml — and does NOT need a creds-hydrate lane. [[revenue-ship-order]] [[demand-before-rails]]
        "lane": "lemonsqueezy (exporter pro-tier checkout store id)",
        "ref": "op://Personal/Lemon Squeezy Store ID/credential",
        "env": ["LEMONSQUEEZY_STORE_ID", "VITE_LEMONSQUEEZY_STORE_ID"],
        "enabled": True,
        # Not required: the MONETA BTC mint is the live rail; LS is the next MoR layer.
        # --verify silently skips (warn-level) until the op:// item is created.
        "required": False,
    },
    {
        # FILE sink — HORREVM custody (scripts/horrevm-custody.py): the ENTIRE rclone.conf is one
        # op:// item (config-is-cartridge), hydrated atomically 0600 into rclone's default path.
        # Contains the gdrive: (scope drive.file) + dropbox: remotes with their OAuth refresh
        # tokens; rclone self-refreshes access tokens from it, so hydration is the only plumbing.
        # Human atom: `rclone authorize "drive"` + `rclone authorize "dropbox"` (one browser
        # consent each), paste the assembled conf into `op://Limen-Automation/rclone.conf` —
        # homed as credential-labelled issue #1108 + Wall #320, never recited in chat. Until the
        # item exists this lane warn-skips (required=False) and horrevm-custody prints PARKED on
        # L-CLOUD-EGRESS-CONSENT (#1109). [[credential-durability-organ]] [[sovereign-cash-intake]]
        "lane": "rclone (HORREVM cloud custody config)",
        "ref": "op://Limen-Automation/rclone.conf/notesPlain",
        "env": [],
        "file": {"path": "~/.config/rclone/rclone.conf", "template": "{value}"},
        "enabled": True,
        "required": False,
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


def _gh_sinks(entry: dict) -> list[dict]:
    """gh_secret may be a single sink dict OR a LIST of them — one op:// value fanned out to every
    CI-secret sink (e.g. the shared GCP deploy SA landed on each repo that deploys to that project).
    A sink is {"repo": "owner/repo", "name": N} (repo secret) or {"org": O, "name": N,
    "visibility": "all|private"} (ORG-level Actions secret — one secret every repo inherits, the
    307-repo fan-out the review engine needs). Normalize to a list; empty when the entry has no
    CI-secret sink. Backward-compatible: a lone dict becomes a one-element list."""
    g = entry.get("gh_secret")
    if not g:
        return []
    return list(g) if isinstance(g, list) else [g]


def _sink_ref(s: dict) -> str:
    """Human label for a CI-secret sink — names only, never a value."""
    if s.get("org"):
        return f"gh-org:{s['org']}:{s['name']}"
    return f"gh:{s['repo']}:{s['name']}"


def have_op() -> bool:
    return shutil.which("op") is not None


# Where a 1Password service-account token lives if the user mints one. Kept OUTSIDE the repo
# (chmod 600, never committed) so the secret never lands in git. Override with LIMEN_OP_SA_TOKEN_FILE.
SA_TOKEN_FILE = Path(
    os.environ.get("LIMEN_OP_SA_TOKEN_FILE", str(Path.home() / ".config" / "op" / "service-account-token"))
)


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
            capture_output=True,
            text=True,
            timeout=timeout,
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
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=child_env,
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
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
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
            input=value,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0


def gh_org_secret_present(org: str, name: str, timeout: int = 15) -> bool | None:
    """Is an ORG-level Actions secret already SET? Names only, never a value. None = unknown (fail-open).
    Needs admin:org on the gh keyring token."""
    if not have_gh():
        return None
    try:
        r = subprocess.run(
            ["gh", "secret", "list", "--org", org],
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    names = {ln.split()[0] for ln in (r.stdout or "").splitlines() if ln.split()}
    return name in names


def gh_org_secret_set(org: str, name: str, value: str, visibility: str = "all", timeout: int = 30) -> bool:
    """Set an ORG-level Actions secret (value via STDIN, never argv/logged). visibility 'all' means
    every repo in the org inherits it — ONE secret instead of a 307-repo fan-out."""
    if not have_gh():
        return False
    try:
        r = subprocess.run(
            ["gh", "secret", "set", name, "--org", org, "--visibility", visibility],
            input=value,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    return r.returncode == 0


def gh_sink_present(s: dict, timeout: int = 15) -> bool | None:
    """Presence for either sink shape (repo or org)."""
    if s.get("org"):
        return gh_org_secret_present(s["org"], s["name"], timeout)
    return gh_secret_present(s["repo"], s["name"], timeout)


def gh_sink_set(s: dict, value: str, timeout: int = 30) -> bool:
    """Set for either sink shape (repo or org)."""
    if s.get("org"):
        return gh_org_secret_set(s["org"], s["name"], value, str(s.get("visibility") or "all"), timeout)
    return gh_secret_set(s["repo"], s["name"], value, timeout)


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
    re.compile(r"AIza[\w\-]{4}[\w\-]+"),  # Google API keys
    re.compile(r"gh[pousr]_[A-Za-z0-9]{4}[A-Za-z0-9]+"),  # GitHub tokens
    re.compile(r"api_key:\S+"),  # Google's error echoes the key inline
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
                return s[len(pre) :].strip().strip('"').strip("'") or None
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


# --- FULL SWEEP -------------------------------------------------------------------------------------
# DEFAULT_MAP is the CURATED spine: the lanes the fleet dispatches, each with the right env-var name and
# a validity probe. --sweep-all is the CATCH-ALL that complements it: enumerate the automation vaults and
# materialize EVERY remaining credential field into ~/.limen.env, so "one spot" holds all secrets/tokens/
# api-keys — not just the hand-listed six. It runs ONLY when `op` is promptless (a service-account token),
# so it can NEVER pop a Touch-ID storm; without the token it is a no-op that points at the one install step.
# Curated items are left to their lane (correct name + probe); the sweep fills the gap so nothing is missed.

# Field labels/ids that name a credential-shaped value (case-insensitive substring match on label OR id).
_CRED_FIELD_HINTS = ("credential", "token", "api key", "api_key", "apikey", "secret", "password", "key")
# Item categories worth sweeping. LOGIN is EXCLUDED by default — those are personal web logins, not fleet
# automation creds, and a plaintext env is the wrong home for them (set LIMEN_CREDS_SWEEP_LOGINS=1 to include).
_SWEEP_CATEGORIES = {"API_CREDENTIAL", "PASSWORD", "SECURE_NOTE", "DATABASE", "SERVER", "SSH_KEY"}


def _sweep_vaults() -> list[str]:
    """Vaults to sweep: LIMEN_CREDS_SWEEP_VAULTS (comma-sep) overrides; else the distinct vaults the
    curated DEFAULT_MAP already draws from (op://<vault>/...) — the fleet's known automation vaults."""
    override = os.environ.get("LIMEN_CREDS_SWEEP_VAULTS")
    if override:
        return [v.strip() for v in override.split(",") if v.strip()]
    vaults: list[str] = []
    for e in DEFAULT_MAP:
        ref = e.get("ref", "")
        if ref.startswith("op://"):
            v = ref[len("op://") :].split("/", 1)[0]
            if v and v not in vaults:
                vaults.append(v)
    return vaults


def _mapped_titles() -> set[tuple[str, str]]:
    """(vault, item-title) pairs already curated in DEFAULT_MAP — the sweep skips these so it never
    fights the lane's correct env-var name / probe. Parsed from each op://vault/item/field ref."""
    out: set[tuple[str, str]] = set()
    for e in DEFAULT_MAP:
        ref = e.get("ref", "")
        if ref.startswith("op://"):
            parts = ref[len("op://") :].split("/")
            if len(parts) >= 2:
                out.add((parts[0], parts[1]))
    return out


def _mapped_env_names() -> set[str]:
    """Every env-var name the curated map owns — the sweep never clobbers these (curated wins)."""
    out: set[str] = set()
    for e in DEFAULT_MAP:
        out.update(e.get("env", []))
    return out


def _sanitize_env_name(s: str) -> str:
    """An item/field title -> a legal UPPER_SNAKE env var name."""
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()


def _op_json(cmd: list[str], timeout: int = 20):
    """Run an `op` subcommand that emits JSON; return the parsed object or None on any failure."""
    try:
        r = subprocess.run(
            ["op", *cmd, "--format=json"], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def _selected_fields(item: dict) -> list[tuple[str, str]]:
    """(env-suffix-label, value) for each credential-shaped field of an item. Values never printed."""
    picks: list[tuple[str, str]] = []
    for f in item.get("fields", []) or []:
        val = f.get("value")
        if not val:
            continue
        ftype = (f.get("type") or "").upper()
        if ftype not in ("CONCEALED", "STRING", "SSHKEY", ""):
            continue
        label = (f.get("label") or f.get("id") or "").lower()
        purpose = (f.get("purpose") or "").upper()
        if purpose == "PASSWORD" or any(h in label for h in _CRED_FIELD_HINTS):
            picks.append((f.get("label") or f.get("id") or "credential", val))
    return picks


def sweep_all(apply: bool) -> int:
    """Enumerate the automation vaults and materialize every credential field NOT already curated in
    DEFAULT_MAP. Promptless-only: a no-op (with the one install hint) when op can't read silently."""
    if not have_op():
        print("creds-hydrate --sweep-all: `op` not found — install the 1Password CLI first. (fail-open)")
        return 0
    if not op_can_read_silently():
        print(
            "creds-hydrate --sweep-all: op is NOT promptless — refusing to run (a sweep here would pop a "
            "Touch-ID storm). Install the service-account token ONCE, then the sweep is silent forever:"
        )
        print(f"  scripts/op-service-account.sh install   # writes {SA_TOKEN_FILE}, chmod 600, value never shown")
        return 0

    vaults = _sweep_vaults()
    include_logins = os.environ.get("LIMEN_CREDS_SWEEP_LOGINS") == "1"
    mapped_titles, mapped_envs = _mapped_titles(), _mapped_env_names()
    print(
        f"creds-hydrate --sweep-all {'--apply' if apply else '(dry-run — pass --apply to write)'} "
        f"over vault(s): {', '.join(vaults) or '(none)'}"
    )
    swept, skipped_curated, skipped_login, skipped_collide = 0, 0, 0, 0
    written_names: set[str] = set()
    for vault in vaults:
        items = _op_json(["item", "list", "--vault", vault])
        if not items:
            print(f"  · {vault:20} (no items readable / empty)")
            continue
        for meta in items:
            title, cat = meta.get("title", ""), (meta.get("category") or "").upper()
            if (vault, title) in mapped_titles:
                skipped_curated += 1
                continue
            if cat == "LOGIN" and not include_logins:
                skipped_login += 1
                continue
            if cat not in _SWEEP_CATEGORIES and cat != "LOGIN":
                continue
            full = _op_json(["item", "get", meta.get("id", title), "--vault", vault])
            if not full:
                continue
            fields = _selected_fields(full)
            if not fields:
                continue
            base = _sanitize_env_name(title)
            for label, val in fields:
                name = base if len(fields) == 1 else f"{base}_{_sanitize_env_name(label)}"
                if name in mapped_envs:  # curated map owns this name — never clobber it
                    skipped_collide += 1
                    del val
                    continue
                if apply:
                    write_env(name, val)
                del val
                written_names.add(name)
                swept += 1
                print(f"  {'✓' if apply else 'plan:'} {vault}/{title} -> {name}")
    print(
        f"creds-hydrate --sweep-all: {swept} field(s){' materialized' if apply else ' planned'}, "
        f"{skipped_curated} curated-skip, {skipped_login} login-skip, {skipped_collide} name-collision-skip."
    )
    if skipped_login:
        print(
            f"  ({skipped_login} LOGIN item(s) skipped — personal web logins; set LIMEN_CREDS_SWEEP_LOGINS=1 to include.)"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Hydrate fleet credentials from 1Password — once minted, never re-logged-in."
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument(
        "--apply", action="store_true", help="materialize promptless lanes; combine with --op for static op:// reads"
    )
    g.add_argument(
        "--check", action="store_true", help="report PRESENCE of env targets (names only; offline) — not validity"
    )
    g.add_argument(
        "--verify",
        action="store_true",
        help="authenticate each materialized cred against its service (VALIDITY) — exit 1 if any is dead",
    )
    g.add_argument("--dry-run", action="store_true", help="print the op://→target plan; NO reads, NO writes (default)")
    ap.add_argument(
        "--sweep-all",
        action="store_true",
        dest="sweep_all",
        help="CATCH-ALL: materialize EVERY credential field in the automation vaults (beyond the curated "
        "map) into ~/.limen.env. Promptless-only (needs the service-account token) — never prompts. "
        "Combine with --apply to write; alone it dry-runs the plan.",
    )
    ap.add_argument(
        "--op",
        action="store_true",
        help="ALSO read op:// lanes — may raise a 1Password Touch-ID/GUI prompt. OFF by default: "
        "without it, only promptless lanes (derive, e.g. the gh keyring) hydrate, so NO dialog "
        "ever fires from a daemon beat or an interactive session. Pass it deliberately, at a "
        "terminal, when you want to (re)hydrate the op:// creds and accept one biometric touch.",
    )
    args = ap.parse_args()

    load_service_account_token()  # hydrate OP_SERVICE_ACCOUNT_TOKEN from its file if present → silent `op read`

    # --sweep-all is the catch-all pass; it complements the curated map rather than iterating it.
    if getattr(args, "sweep_all", False):
        return sweep_all(apply=args.apply)

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
        # A `required` lane that never materialized is a DEFECT — but only when the floor is
        # OTHERWISE configured (hydration ran, materialized other creds, yet this required one
        # failed to land → the op:// read is silently failing). On a truly EMPTY floor (fresh
        # machine / CI, nothing set up yet) stay quiet: report "?" and exit 0, no false alarm.
        floor_populated = any(_env_value(x) for e in cred_map for x in e.get("env", []))
        for e in cred_map:
            envs = e.get("env", [])
            sinks = _gh_sinks(e)
            if not envs and sinks:
                # A CI-secret sink isn't probeable here — the value isn't materialized on this floor and
                # GitHub never returns a secret's value. Presence/landing is reported by --apply. Neutral,
                # network-free, never fails the beat.
                label = ", ".join(_sink_ref(s) for s in sinks)
                print(f"  · {e['lane']:28} CI-secret {label} — managed on --apply (value not readable back)")
                continue
            val = _env_value(envs[0]) if envs else None
            if not val:
                if e.get("required") and floor_populated:
                    # A REQUIRED lane missing on a configured floor is a DEFECT, not a shrug: the
                    # op:// read is failing silently (fail-open skip on --apply) and an organ
                    # downstream is starving. Surface it as loud as a dead token so the beat log
                    # flags it — never let a required credential rot green. (Root cause: the op://
                    # item is not readable — vault grant / field name / item moved. Wall #320, #261.)
                    print(f"  ✗ {e['lane']:28} {','.join(envs)} — REQUIRED, NOT materialized "
                          f"(op:// read is failing → check {e.get('ref', 'the op:// item')} is readable)")
                    any_invalid = True
                else:
                    tail = " (REQUIRED — will alarm once the floor is configured)" if e.get("required") else " (run --apply)"
                    print(f"  ? {e['lane']:28} {','.join(envs) or '(file only)'} — not materialized{tail}")
                continue
            state, detail = probe_cred(e, val)
            del val
            mark = {"valid": "✓", "invalid": "✗", "unverifiable": "?"}[state]
            print(f"  {mark} {e['lane']:28} {state.upper()}" + (f" — {detail}" if detail else ""))
            any_invalid = any_invalid or state == "invalid"
        if any_invalid:
            print(
                "creds-hydrate: ✗ = a DEAD credential (presence ✓ is not validity). Re-mint it into its "
                "op:// item, then `--apply`. Re-run `--verify` to confirm green."
            )
        return 1 if any_invalid else 0

    if not have_op():
        print("creds-hydrate: `op` (1Password CLI) not found — install it, then `op signin`. Skipping (fail-open).")
        return 0

    # --check: presence only, no secret reads of the env file's values
    if args.check:
        print(f"creds-hydrate --check ({ENV_FILE}):")
        for e in cred_map:
            envs = e.get("env", [])
            sinks = _gh_sinks(e)
            if not envs and sinks:
                label = ", ".join(_sink_ref(s) for s in sinks)
                print(f"  · {e['lane']:28} {ref_display(e['ref'])} -> {label} (CI secret — checked on --apply)")
                continue
            present = all(_env_has(k) for k in envs) if envs else False
            mark = "✓" if present else "✗"
            print(f"  {mark} {e['lane']:28} {ref_display(e['ref'])} -> {','.join(envs) or '(file only)'}")
        print(
            "  (presence only — ✓ means the env var is SET, not that it still authenticates. "
            "Run `--verify` to probe validity against each service.)"
        )
        return 0

    apply = args.apply  # default (no flag) == dry-run

    # ── OP IS OPT-IN — the root-to-leaf fix for the recurring 1Password Touch-ID/GUI dialogs ──────
    # ROOT CAUSE (confirmed from 1Password's own daemon logs): the app's unlock policy is
    # `BiometricsOnly` with "Ask Again After: -1" (never cache) — so EVERY `op read` re-locks
    # immediately and demands a fresh Touch-ID. Nothing is cached, so each access is its own prompt.
    # The PERMANENT cure is a service-account token (the only promptless `op`): install it once at
    # SA_TOKEN_FILE (scripts/op-service-account.sh) and op_can_read_silently() flips True, so this whole
    # opt-in gate falls away — the beat and --sweep-all read op with ZERO Touch-ID, forever.
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
        hint = (
            "re-run with `--op` at a terminal to hydrate them (accepts one Touch-ID)."
            if running_interactively()
            else "they hydrate only with `--op` or a service-account token."
        )
        print(
            "creds-hydrate: op:// lanes SKIPPED (opt-in) — not touching 1Password, so no Touch-ID/GUI "
            f"prompt fires. Promptless `derive` lanes still hydrate. To (re)hydrate the op:// creds, {hint}"
        )

    print(f"creds-hydrate {'--apply' if apply else '--dry-run (no reads, no writes — pass --apply to hydrate)'}:")
    hydrated, skipped = 0, 0
    for e in cred_map:
        ref, envs, fspec = e["ref"], e.get("env", []), e.get("file")
        dcmd = e.get("derive")
        sinks = _gh_sinks(e)
        targets = ", ".join(envs) + (f" + {fspec['path']}" if fspec else "")
        for s in sinks:
            targets += (" + " if targets else "") + _sink_ref(s)
        source = f"`{' '.join(dcmd)}` (op:// fallback)" if dcmd else ref_display(ref)
        if not apply:
            print(f"  plan: {e['lane']:28} {source} -> {targets}")
            continue
        # gh_secret-ONLY entry (no env/file): if the CI secret is already set, skip — no value read, no
        # re-push, and crucially NO 1Password touch. The organ keeps it landed without a per-beat biometric
        # prompt; it only reads+sets when the secret is ABSENT (and op is permitted / the value derivable).
        if sinks and not envs and not fspec and all(gh_sink_present(s) is True for s in sinks):
            label = ", ".join(_sink_ref(s) for s in sinks)
            print(f"  ✓ {e['lane']:28} -> {label} (already set)")
            hydrated += 1
            continue
        # Prefer a live-minted value (e.g. the gh keyring) over the static op:// secret; fall back to
        # op ONLY when op can read without a prompt (op_ok) — else the op:// fallback is skipped, no GUI.
        val = derive_value(dcmd) if dcmd else None
        if not val and op_ok:
            val = op_read(ref)
        if not val:
            why = (
                "unreadable (check op signin / the field name)"
                if op_ok
                else "op:// read skipped — no promptless 1Password auth (fail-open, no Touch-ID)"
            )
            print(f"  SKIP {e['lane']:28} {source} — {why}")
            skipped += 1
            continue
        for k in envs:
            write_env(k, val)
        wrote_file = write_tool_file(fspec, val) if fspec else None
        gh_results = [(s, gh_sink_set(s, val)) for s in sinks]
        del val  # drop the secret from memory promptly
        parts = []
        if envs:
            parts.append(",".join(envs))
        if wrote_file:
            parts.append(wrote_file)
        for s, ok in gh_results:
            parts.append(_sink_ref(s) + ("" if ok else " (set FAILED)"))
        print(f"  ✓ {e['lane']:28} -> {' + '.join(parts)}")
        hydrated += 1

    if apply:
        print(
            f"creds-hydrate: {hydrated} hydrated, {skipped} skipped. "
            f"Apply to the running daemon: launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat"
        )
        if skipped:
            print(
                "  (skipped = `op` couldn't read it: unlock with `op signin`, then re-run with `--op`, "
                "or fix the field in the map. Never a vendor re-login — only the 1Password unlock.)"
                if op_ok
                else "  (skipped = op:// lanes are opt-in and `--op` was not passed — this is the NO-PROMPT "
                "default. Promptless `derive` lanes hydrated. Pass `--op` at a terminal to hydrate op://.)"
            )
    return 0


def ref_display(ref: str) -> str:
    """op://vault/item/field — safe to print (it's a path, not a secret)."""
    return ref


if __name__ == "__main__":
    raise SystemExit(main())
