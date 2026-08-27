# GitHub App exact-repository identity architecture

Current control-plane correction, verified 2026-08-25:

- `4444J99/limen` is the canonical supra-organization controller, with stable repository ID
  `1255213941`; `organvm/limen` is a historical alias that redirects to the same repository.
- Organizations remain governed owners of their domain products, policies, and deployments. They
  are not the owner of the governor.
- App access is resolved and minted for one exact `OWNER/REPO` at a time. An organization-wide
  installation is not authority to select an arbitrary repository.

Historical topology snapshot, verified 2026-07-06 and retained as evidence:

- `organvm` now holds 301 repos.
- GitHub consolidation gates report `0` source repos and `0` collision groups outside `organvm`.
- `limen[bot]` is still blocked on App creation/install plus secret hydration. The installed `organvm` Apps are `claude`, `google-labs-jules`, `oz-by-warp`, and `chatgpt-codex-connector`.
- `scripts/gh-app-token.sh --repo OWNER/REPO --which` reports the credential path without printing a token.

Status as of 2026-06-20. This is the **settled** conclusion — not new research. It answers, once,
"we don't need enterprise, do we? we don't even need all these orgs? we need the user profile…
and something beyond it."

## Runner admission diagnosis

Provider errors are observations, not proof that an account is billing locked. A failed Actions
job with no runner and no executed steps is durably classified as `provider_runner_admission` /
`CI_ZERO_STEP_ADMISSION`; the account cause and remedy remain unverified unless authoritative
account, budget, usage, and repository evidence proves them.

Keep standard-runner CI repositories public so their runner surface remains zero-cost. Moving the
controller changes which repository admits the runner; it does not by itself prove recovery.

## Identity (architecture — the remaining durable fix, staged here)

| Question | Answer |
|---|---|
| Need GitHub **Enterprise**? | **No.** SAML/SCIM/audit/EMU/pooled-billing — none used. Let the `organvm-i..vii` + `meta-organvm` Enterprise **trial** (seats:0, created 2025-10-22) **lapse**. |
| Need all those **orgs**? | **Yes, as governed domain namespaces—not as the supra-organization controller.** `dispatch.py` / `route.py` / `resolve-identities.py` derive current coordinates from repository identity while preserving historical aliases. Organizations continue owning domain products, policies, and deployments; `4444J99/limen` governs across them. Do **not** delete `organvm`. |
| "Something beyond the user profile"? | **A GitHub App: `limen[bot]`, using installation tokens.** |

### Why a GitHub App, not a PAT

A **PAT acts as the human** and shares that account's authorization and rate-limit surface. A
**GitHub App** is a first-class machine identity:

- its own actor (`limen[bot]`), independent of any human account,
- per-repo **least-privilege, auto-expiring** installation tokens,
- 15k/hr rate limit,
- selects the installation for one exact target repository before minting.

(A bot *user* account is the inferior alternative; a fine-grained PAT is only a bootstrap.)

## How it's wired (code on `main`)

`scripts/gh-app-token.sh` is the executable identity. Any GitHub caller gets its token via:

```sh
GITHUB_TOKEN=$(bash scripts/gh-app-token.sh --repo OWNER/REPO)
```

Credential selection is fail-closed at the App boundary:

1. **App** — if `GITHUB_APP_ID` + `GITHUB_APP_PRIVATE_KEY` are set → mint a short-lived
   token only after `GET /repos/OWNER/REPO/installation` resolves one installation and the
   repository's numeric ID/full name match. A configured installation ID is an assertion and must
   equal the resolved ID. Because an App JWT cannot call the general repository endpoint, the
   helper first mints a one-repository-name bootstrap token, verifies the stable numeric identity
   with that token, discards it, and returns a fresh token containing exactly that one numeric
   repository ID.
2. **PAT** — only when App credentials are absent, emit `GITHUB_TOKEN` unchanged.
3. **gh** — else `gh auth token`.

When App credentials are present, missing/invalid targeting or mint failure exits nonzero without
falling back to PAT or `gh`. `bash scripts/gh-app-token.sh --repo OWNER/REPO --which` reports which
path would be used, printing no secret.

## The one human atom (to flip identity from PAT → App)

Everything below is the irreducible manual step a script cannot do (it generates a private key):

1. **Register the App**: GitHub → Settings → Developer settings → GitHub Apps → New.
   - Name `limen[bot]`; permissions least-privilege (Contents: RW, Pull requests: RW,
     Actions: R, Metadata: R); no webhook needed for token minting.
   - Generate a **private key** (downloads a `.pem`). Note the numeric **App ID**.
2. **Install** the App only where required, beginning with the exact controller repository
   `4444J99/limen`, then each exact organization target that a trusted finalizer must mutate.
   Derive targets from live repository identity at execution time; do not grant blanket estate
   access or select an arbitrary repository from an owner-wide installation.
3. **Hand the conductor the creds** (silent, never echoed):
   ```sh
   scripts/bootstrap-github-app.py
   # or, if the App was created manually:
   bash scripts/set-credential.sh GITHUB_APP_ID
   bash scripts/set-credential.sh GITHUB_APP_PRIVATE_KEY   # paste full PEM, or store the .pem and give its path
   bash scripts/set-credential.sh --check                  # names only; confirms the App keys are present
   # GITHUB_APP_INSTALLATION_ID is optional — when set it must match the exact repository
   ```
4. Verify: `bash scripts/gh-app-token.sh --repo 4444J99/limen --verify-app`.
5. **Let the Enterprise trial lapse.** No migration, no payment. (Do NOT delete `organvm` — it
   now holds 301 repos; the earlier "delete the empty organvm" note is stale.)

Until step 1–3 are done, the fleet keeps running on the PAT fallback — zero behavior change.
