# Credential Token Tombstone Audit

Receipt for: `organvm/limen#686` / `AW-CREDENTIAL-WALL-TOKEN-HYGIENE`

Prepared: `2026-07-08T02:04:41Z`

## Scope

This receipt records ownership and revocation custody for token, secret, API-key,
login, and env-var pain points that have appeared in the credential wall work.
It does not record secret values, partial values, raw bearer strings, private
account identifiers, or prompt text.

The current credential wall remains the source of truth for live credential
atoms:

- `scripts/creds-hydrate.py` -> `DEFAULT_MAP` owns hydration lanes and derived
  or parked credentials.
- `scripts/credential-wall.py` -> `CI_SECRETS` owns CI/runtime secret names and
  homes.
- `https://github.com/organvm/limen/issues/320` is the pinned wall surface.
- `https://github.com/organvm/limen/labels/credential` is the action filter.
- This file owns historical tombstones and rotation custody.

## Harvest Before Edit

Checked before creating this receipt:

- Local packet: `docs/always-working.md` section
  `CREDENTIAL-WALL-TOKEN-HYGIENE`.
- Local task projection: `tasks.yaml` task `GH-organvm-limen-686`.
- Remote owner issue: `organvm/limen#686`.
- Remote wall issue: `organvm/limen#320`.
- Existing implementation receipts: `organvm/limen#523`, `#527`, `#541`,
  `#551`, `#557`, and `#652`.
- Local source: `scripts/credential-wall.py` and `scripts/creds-hydrate.py`.

No existing tombstone-audit PR or receipt file was found in this worktree.

## Current Home Gate

The current-home predicate is:

```bash
python3 scripts/credential-wall.py --check
```

That predicate proves every currently declared credential, token, login, API-key,
or env-var atom has a registered home. It does not prove live vendor validity;
for credential validity use:

```bash
python3 scripts/creds-hydrate.py --verify
```

Validity probes may require network/vendor availability. Tombstone custody does
not require reading or printing secret values.

## Tombstone And Custody Register

| Class | State | Owner surface | Rotation or revocation custody | Verification without values |
|---|---|---|---|---|
| Former static GitHub PAT class feeding `GH_TOKEN` / `GITHUB_TOKEN` | Tombstoned as a live source; current lanes derive from the local `gh` keyring instead of trusting a static token cache. | `scripts/creds-hydrate.py` lanes `gh/copilot/jules` and `laurea`; wall issue `#320`; related credential issue context in `#265`. | If a stale static PAT exists outside this repo, revoke it in GitHub token settings and let `gh auth token` remain the derived source. Do not paste replacement values into chat, issues, PRs, or the board. | `python3 scripts/credential-wall.py --check`; `python3 scripts/creds-hydrate.py --verify` for the GitHub probe when vendor access is available. |
| Phantom OpenAI API-key lane `OPENAI_API_KEY` | Parked, not a current credential requirement for Codex because the lane authenticates through ChatGPT OAuth. No repo evidence requires an API-key value. | Disabled `codex/opencode (openai)` entry in `scripts/creds-hydrate.py`; wall issue `#320`. | If Anthony later mints a real API key for a tool that consumes it, add/update the `DEFAULT_MAP` entry and rotate the value only in its secret manager. Until then, no value exists in this repo to revoke. | `python3 scripts/credential-wall.py --check`; code-owner review of `DEFAULT_MAP` before enabling the lane. |
| Phantom OpenRouter API-key lane `OPENROUTER_API_KEY` | Parked, not a current credential requirement for OpenCode because the lane uses its own auth or a free model path. | Disabled `opencode (openrouter)` entry in `scripts/creds-hydrate.py`; wall issue `#320`. | If a future OpenRouter credential is minted, land it through the credential wall and rotate it in the vendor account only. Do not create a chat-held token. | `python3 scripts/credential-wall.py --check`; code-owner review of `DEFAULT_MAP` before enabling the lane. |
| Cloudflare deploy token class | Current active credential class, not tombstoned. Earlier false-negative and re-mint framing is retired; the token class is owned by the credential organ. | `scripts/creds-hydrate.py` Cloudflare lanes; `scripts/credential-wall.py`; wall issue `#320`; PR receipts `#541` and `#551`. | Rotation belongs to the Cloudflare account plus the credential organ sinks that set GitHub Actions secrets. Old values, if rotated, must be revoked in Cloudflare and replaced only through the secret store or `gh secret set` plumbing. | `python3 scripts/credential-wall.py --check`; `python3 scripts/creds-hydrate.py --verify` for the Cloudflare probe when vendor access is available. |
| 1Password service-account token class `OP_SERVICE_ACCOUNT_TOKEN` | Current active control point with a recorded scope residual: promptless auth can exist while vault grants may still be limited. | `scripts/credential-wall.py` CI/runtime catalog; `scripts/op-service-account.sh`; wall issue `#320`; PR receipts `#523`, `#527`, and `#541`. | Replacement requires human/vendor action in 1Password. Local removal is owned by `scripts/op-service-account.sh remove`; new install is through `scripts/op-service-account.sh install`. Old service-account tokens must be revoked in 1Password, never archived in repo. | `scripts/op-service-account.sh status` and `op whoami` when available; `python3 scripts/credential-wall.py --check` for structural home. |
| GCP deploy service-account key class `GCP_SA_KEY` | Parked/superseded for current Limen runtime; retained as an optional CI secret shape, not a live required token. | `scripts/credential-wall.py` CI/runtime catalog; disabled GCP lane in `scripts/creds-hydrate.py`; PR receipts `#526` and `#528`. | If a key is ever minted, it must live in the selected secret manager and GitHub Actions secret only. If superseded, disable or destroy old Secret Manager versions and delete stale Actions secrets. No current repo evidence requires a key value. | `python3 scripts/credential-wall.py --check`; deployment preflight only when the GCP path is explicitly reactivated. |
| Gmail app-password class `GMAIL_APP_PASSWORD` | Current credential class for mail automation sinks; no value belongs in the repo. | `scripts/creds-hydrate.py` Gmail lanes; wall issue `#320`; credential issue `#261`. | Rotate in the mail/account provider, update the secret store, then land CI sink through `op read` to `gh secret set` without printing the value. Revoke old app passwords in the provider UI. | `python3 scripts/credential-wall.py --check`; sink presence checks in `creds-hydrate.py --verify` when available. |
| IANVA bearer token class `IANVA_BEARER_TOKEN` | Current parked/local credential class; rotation is non-idempotent and must not be run by a background hydration beat. | Disabled IANVA entry in `scripts/creds-hydrate.py`; wall issue `#320`; credential issue `#263`. | Rotation belongs to the IANVA bearer mint command and the owning cloud connector. A new bearer supersedes the old one; do not run rotation unless the scoped task explicitly requires it. | `python3 scripts/credential-wall.py --check`; connector-specific activation check when the cloud side is ready. |
| Claude auth token class `LIMEN_CLAUDE_AUTH_TOKEN` | Parked under the Rung-0 credential-race self-heal; not hydrated by the generic credential organ. | Disabled Claude entry in `scripts/creds-hydrate.py`; wall issue `#320`. | Rotate only through the owning Claude/auth flow. If that handler is retired, update `DEFAULT_MAP` and the wall before enabling generic hydration. | `python3 scripts/credential-wall.py --check`; Claude-specific probe only from the owning lane. |
| Limen runtime bearer classes `LIMEN_API_TOKEN` and `LIMEN_CLIENT_TOKEN` | Current active runtime secret classes. | `scripts/credential-wall.py` CI/runtime catalog; GitHub Actions secret homes; GCP Secret Manager homes. | Rotate by adding a new secret-manager version and updating GitHub Actions secrets, then disable or destroy old versions according to the deployment owner policy. Never put bearer values in logs, PR text, tasks, or chat. | `python3 scripts/credential-wall.py --check`; runtime deploy verification when that path is in scope. |
| Optional Warp/Oz paid-service key class `WARP_API_KEY` | Optional current credential class; lanes stay off when absent. | `scripts/credential-wall.py` CI/runtime catalog; capacity docs; local env cache if installed. | If installed, rotate through the vendor account and update both local env cache and GitHub Actions secret. If absent, no token exists here to revoke. | `python3 scripts/credential-wall.py --check`; capacity/route probes when paid lanes are in scope. |

## Closure Rule

A credential/token pain point is closed only when one of these is true:

- It is present in the generated wall and `credential-wall.py --check` passes.
- It is parked or superseded in `DEFAULT_MAP` with an owner comment and no current
  consumer.
- It has an owner issue under the `credential` label.
- It has a tombstone row in this file naming rotation or revocation custody.

Any future receipt, PR, issue, or task that needs a value must point to the owner
surface above. It must not ask Anthony to paste the value into chat or a public
artifact.
