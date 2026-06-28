# GitHub: billing + identity architecture (the durable fix)

Update verified 2026-06-28:

- `organvm` now holds 264 repos.
- The current `gh` login has `admin:org` and `workflow`; the temporary personal-token bridge can perform gated transfers.
- `limen[bot]` is still blocked on App creation/install plus secret hydration. The installed `organvm` Apps are `claude`, `google-labs-jules`, `oz-by-warp`, and `chatgpt-codex-connector`.
- `scripts/gh-app-token.sh --which` currently resolves to `pat (GITHUB_TOKEN fallback)`, not the App path.

Status as of 2026-06-20. This is the **settled** conclusion — not new research. It answers, once,
"we don't need enterprise, do we? we don't even need all these orgs? we need the user profile…
and something beyond it."

## Billing (keystone — DONE)

The root cause of fleet CI going dark was **account-level billing**, not architecture. Account
`4444J99` was billing-locked → GitHub Actions disabled account-wide → no PR could merge anywhere.

- **Paid 2026-06-19** (card 0186). Actions re-enabled (`actions/permissions` → `enabled:true`).
- The lock is **account-level**: consolidating repos / moving orgs does **not** fix it. The one
  human atom was "settle the balance," and it's done.
- Keep CI repos **public** → free unlimited Actions, so a future billing hiccup can't re-dark them.

## Identity (architecture — the remaining durable fix, staged here)

| Question | Answer |
|---|---|
| Need GitHub **Enterprise**? | **No.** SAML/SCIM/audit/EMU/pooled-billing — none used. Let the `organvm-i..vii` + `meta-organvm` Enterprise **trial** (seats:0, created 2025-10-22) **lapse**. |
| Need all those **orgs**? | **No.** Orgs are optional namespaces, not infrastructure. `dispatch.py` / `route.py` / `resolve-identities.py` derive identity from the git remote `owner/repo`, never from org plans/secrets. Moving a repo = change one string + the remote. **Note (verified 2026-06-20):** `organvm` is NO LONGER empty — it is now the **consolidation target holding 182 repos** (the old workhorse `a-organvm` is down to 3). Do **not** delete it; it's the primary owner. |
| "Something beyond the user profile"? | **A GitHub App: `limen[bot]`, using installation tokens.** |

### Why a GitHub App, not a PAT

A **PAT acts as the human**: it shares their 5k/hr limit and **dies the instant the personal
account is billing-locked** — exactly what took CI down. A **GitHub App** is a first-class machine
identity:

- its own actor (`limen[bot]`), independent of any human account,
- per-repo **least-privilege, auto-expiring** installation tokens,
- 15k/hr rate limit,
- survives a personal-account lock — so a future lock **can't** down the fleet.

(A bot *user* account is the inferior alternative; a fine-grained PAT is only a bootstrap.)

## How it's wired (code, staged on branch `worktree-gh-app-token`)

`scripts/gh-app-token.sh` is the executable identity. Any GitHub caller gets its token via:

```sh
GITHUB_TOKEN=$(bash scripts/gh-app-token.sh)   # drop-in for gh / the mining API / git push
```

It **cascades** (cascade-fallback-principle) so nothing breaks before the App exists:

1. **App** — if `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY` are set → mint a short-lived
   installation token (RS256 JWT via `openssl` → `/app/installations/{id}/access_tokens`).
   Installation id is **derived** at run-time if not pinned ("names are outputs").
2. **PAT** — else emit `GITHUB_TOKEN` unchanged (today's bootstrap).
3. **gh** — else `gh auth token`.

`bash scripts/gh-app-token.sh --which` reports which path *would* be used, printing no secret.

## The one human atom (to flip identity from PAT → App)

Everything below is the irreducible manual step a script cannot do (it generates a private key):

1. **Register the App**: GitHub → Settings → Developer settings → GitHub Apps → New.
   - Name `limen[bot]`; permissions least-privilege (Contents: RW, Pull requests: RW,
     Actions: R, Metadata: R); no webhook needed for token minting.
   - Generate a **private key** (downloads a `.pem`). Note the numeric **App ID**.
2. **Install** the App on the load-bearing owners, **led by `organvm` (182 repos)** —
   then `organvm-i-theoria` (7), `4444J99` (3), `a-organvm` (3), `organvm-iii-ergon` (2).
   Live repo counts verified 2026-06-20; derive the install list from where repos actually
   live, not a pinned list ("names are outputs").
3. **Hand the conductor the creds** (silent, never echoed):
   ```sh
   bash scripts/set-credential.sh GITHUB_APP_ID
   bash scripts/set-credential.sh GITHUB_APP_PRIVATE_KEY   # paste full PEM, or store the .pem and give its path
   # GITHUB_APP_INSTALLATION_ID is optional — derived if omitted
   ```
4. Verify: `bash scripts/gh-app-token.sh --which` → `app (limen[bot] installation token)`.
5. **Let the Enterprise trial lapse.** No migration, no payment. (Do NOT delete `organvm` — it
   now holds 182 repos; the earlier "delete the empty organvm" note is stale as of 2026-06-20.)

Until step 1–3 are done, the fleet keeps running on the PAT fallback — zero behavior change.
