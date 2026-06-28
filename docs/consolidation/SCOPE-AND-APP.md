# Consolidation Scope Unblock + limen[bot] GitHub App Path

## 2026-06-28 live status

- `gh auth status` now shows `admin:org` and `workflow`; the personal-token scope blocker in this document is resolved for the current `4444J99` `gh` login.
- The durable App identity is still not wired. `bash scripts/gh-app-token.sh --which` reports `pat (GITHUB_TOKEN fallback)`.
- `gh api /orgs/organvm/installations` lists `claude`, `google-labs-jules`, `oz-by-warp`, and `chatgpt-codex-connector`; no `limen-bot`/`limen[bot]` App installation is present.
- Current consolidation dry-run: 34 source repos remain outside `organvm`, with 13 collision groups. Use `docs/consolidation/RUNBOOK.md` and `docs/consolidation/COLLISION-RENAMES.md` for the current gate packet.

> Subject: the consolidation `--apply` (org→org repo transfers into `organvm`) and the
> live fleet's CI both fail for the **same root cause** — the active token is a
> *personal* token (`4444J99`) that (a) lacks `admin:org` so transfers are forbidden and
> (b) is coupled to the personal account whose billing lock killed CI in June.
> This doc gives BOTH fixes: (1) the one immediate command, (2) the durable App.
> Date written: 2026-06-20. gh authed as `4444J99`, scopes `gist, read:org, repo`.
> **Nothing here is executed by writing this file.** Every command is gated on the user.

---

## 0. Verified current state (read-only)

```
gh auth status      → Logged in to github.com account 4444J99 (keyring), active
token scopes        → gist, read:org, repo        # NO admin:org, NO workflow
target org          → organvm   (exists, empty, free plan, 4444J99 = active admin)
source owners (10)  → 4444J99, a-organvm, meta-organvm,
                      organvm-i-theoria … organvm-vii-kerygma   (287 repos)
```

Two distinct missing scopes, two distinct symptoms:

| Missing scope | Blocks | Symptom |
|---|---|---|
| `admin:org` | `POST /repos/{owner}/{repo}/transfer` where source and/or target is an **org** | `consolidate-github.py --apply` errors / partial-fails — "Must have admin rights" |
| `workflow` | pushing/editing files under `.github/workflows/**` via git or the Contents API | After transfer, the `deploy-api.yml` literal fix (`LIMEN_GITHUB_REPO=4444J99/limen`) and any workflow rewrite is rejected unless the pusher's token carries `workflow` |

Both are needed for the consolidation cutover, so grant them together.

---

## 1. IMMEDIATE UNBLOCK — the exact single command (user runs this)

This re-authorizes the **existing** `gh` login in place, adding the two scopes the
transfer + workflow rewrite need. It opens a browser device-code prompt; approve it on
the `4444J99` account. No new token to store, no config changes — `gh`/git keep using
the keyring entry, now with the wider scopes.

```bash
gh auth refresh -h github.com -s admin:org -s workflow
```

Verify immediately after (should now list `admin:org` and `workflow`):

```bash
gh auth status
```

Then prove the grant with **one** low-stakes manual transfer before any bulk run
(reversible — transfer it back; old URLs auto-redirect):

```bash
# pick the lowest-value archived/source repo as the canary, transfer to organvm:
gh api -X POST repos/<source-owner>/<canary-repo>/transfer -f new_owner=organvm
# revert if you want to confirm reversibility:
gh api -X POST repos/organvm/<canary-repo>/transfer -f new_owner=<source-owner>
```

Only after that single transfer succeeds should the gated bulk `--apply` from
`docs/CONSOLIDATE-DRYRUN.md §6` be considered (and only after the 15 collisions are
resolved and the config-rewrite cutover is planned — see that dossier §5).

> Note — org *third-party access policy*: if any source org restricts OAuth apps,
> `admin:org` on the token still won't transfer until the GitHub CLI OAuth app is
> approved for that org. Approve at:
> `https://github.com/organizations/<org>/settings/oauth_application_policy`
> (Owner → Settings → Third-party access). This is the most common reason a
> correctly-scoped token still returns 403 on org→org transfer.

---

## 2. DURABLE FIX — limen[bot] GitHub App on the `organvm` org

The refresh in §1 is a *personal-token* unblock: it ties the fleet's authority to the
`4444J99` human account, the exact coupling that let a personal-billing lock take CI
down (per memory: "GitHub structure: App not orgs" + "Fleet shipping unblocks"). The
durable fix is a **GitHub App** owned by the `organvm` org. The fleet then authenticates
with a short-lived **installation token** minted from the App's private key — decoupled
from any one human's account, billing, or OAuth approval. A personal billing lock can no
longer kill CI, because CI no longer runs as a person.

### 2a. Create the App (one-time, owned by the org so it survives the human)

Browser path (App owned by the ORG, not the user):

1. Go to `https://github.com/organizations/organvm/settings/apps/new`
   (Org → Settings → Developer settings → GitHub Apps → **New GitHub App**).
2. **GitHub App name:** `limen[bot]`  (display name; the actor will appear as
   `limen[bot]`). If taken, use `limen-conductor` and set the *display* name to Limen.
3. **Homepage URL:** `https://github.com/organvm`  (any valid URL is fine).
4. **Webhook:** **uncheck "Active"** (the fleet polls; no inbound webhook needed yet).
5. **Repository permissions** (least-privilege for the conductor + CI + consolidation):
   - **Administration: Read and write**  ← required to **transfer repos**
   - **Contents: Read and write**         ← clone, push branches, commit
   - **Pull requests: Read and write**    ← `gh pr create`, merge
   - **Workflows: Read and write**        ← edit `.github/workflows/**` (the `workflow` analog)
   - **Actions: Read and write**          ← rerun/observe CI checks
   - **Metadata: Read-only** (mandatory, auto-selected)
   - **Issues: Read and write** (optional — mine-backlog reads/labels issues)
6. **Organization permissions:**
   - **Administration: Read and write**   ← org-level admin for **org→org transfer**
   - **Members: Read-only** (optional)
7. **Where can this App be installed?** → **Only on this account** (lock to `organvm`).
8. Create. On the App's page note the **App ID**. Then **Generate a private key** →
   downloads a `*.pem`. Store it as a secret (see 2c); never commit it.

CLI alternative (manifest flow, avoids hand-toggling 8 permissions). Write a manifest
and POST it; GitHub returns a creation URL the user opens once to confirm:

```bash
# from a scratch dir — creates the App under the organvm org via the manifest flow:
cat > /tmp/limen-app-manifest.json <<'JSON'
{
  "name": "limen-bot",
  "url": "https://github.com/organvm",
  "hook_attributes": { "active": false },
  "public": false,
  "default_permissions": {
    "administration": "write",
    "contents": "write",
    "pull_requests": "write",
    "workflows": "write",
    "actions": "write",
    "issues": "write",
    "metadata": "read",
    "organization_administration": "write"
  }
}
JSON
# open this URL in a browser, signed in as an organvm owner, to finalize:
open "https://github.com/organizations/organvm/settings/apps/new?state=limen"
# (paste the manifest JSON into the form's "manifest" field, or use the web path in 2a)
```

### 2b. Install the App onto the org (grant it the repos)

1. App page → **Install App** → choose **organvm** →
   **All repositories** (so newly-transferred repos are auto-covered) → Install.
2. After install, capture the **Installation ID** (needed to mint tokens):

```bash
# requires a temporary JWT or, simplest, list installations after install:
gh api /orgs/organvm/installations --jq '.installations[] | {id, app_slug}'
# → note the id whose app_slug is limen-bot
```

### 2c. Store the credentials as secrets (never in the repo)

Local (for the body/daemon) and the `limen` repo Actions secrets:

```bash
# Actions secrets on the conductor repo (after limen is transferred, retarget to organvm/limen):
gh secret set LIMEN_APP_ID        --repo 4444J99/limen --body "<APP_ID>"
gh secret set LIMEN_APP_INSTALL_ID --repo 4444J99/limen --body "<INSTALLATION_ID>"
gh secret set LIMEN_APP_PRIVATE_KEY --repo 4444J99/limen < /path/to/limen-bot.private-key.pem

# local (body): keep the pem outside any git tree, e.g. ~/.config/limen/limen-bot.pem (chmod 600)
mkdir -p ~/.config/limen && mv /path/to/limen-bot.private-key.pem ~/.config/limen/limen-bot.pem
chmod 600 ~/.config/limen/limen-bot.pem
```

### 2d. Mint an installation token (this replaces the personal gho_ token)

Installation tokens are short-lived (1h) and minted on demand from the App ID +
private key. In CI, the maintained action does this in one step; locally, a small
helper does the JWT→token exchange.

CI (recommended — `actions/create-github-app-token` is GitHub-maintained):

```yaml
# .github/workflows/<any>.yml — drop-in step that yields an installation token
- name: Mint limen[bot] token
  id: app
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.LIMEN_APP_ID }}
    private-key: ${{ secrets.LIMEN_APP_PRIVATE_KEY }}
    owner: organvm            # installation-wide token across the org's repos
# then use it:
- run: gh repo list organvm
  env:
    GH_TOKEN: ${{ steps.app.outputs.token }}
```

Local (body / consolidation script) — exchange via `gh`'s JWT support, no extra deps:

```bash
# build the App JWT from the pem, then exchange for an installation token:
APP_ID="<APP_ID>"; INSTALL_ID="<INSTALLATION_ID>"; PEM="$HOME/.config/limen/limen-bot.pem"
# gh can sign the JWT and call the API directly:
TOKEN=$(GH_APP_ID="$APP_ID" gh api --method POST \
  /app/installations/$INSTALL_ID/access_tokens \
  --jwt "$(python3 - "$APP_ID" "$PEM" <<'PY'
import sys,time,jwt   # pip install pyjwt cryptography
app_id, pem = sys.argv[1], open(sys.argv[2]).read()
now=int(time.time())
print(jwt.encode({"iat":now-60,"exp":now+540,"iss":app_id}, pem, algorithm="RS256"))
PY
)" --jq .token)
# now use it like any token — decoupled from 4444J99's account/billing:
GH_TOKEN="$TOKEN" gh api repos/a-organvm/<canary>/transfer -f new_owner=organvm
```

(If `--jwt` isn't supported by the installed `gh`, the same `/access_tokens` POST works
with `curl -H "Authorization: Bearer $JWT"`; the JWT line is identical.)

### 2e. Wire the fleet to prefer the App token (decouple CI from the person)

- `deploy-api.yml` / any workflow: replace personal-token usage with the
  `actions/create-github-app-token@v1` step above; set `GH_TOKEN` from its output.
- Local daemon (`metabolize.sh` / dispatch): add a `LIMEN_GH_TOKEN` resolution that
  prefers the minted installation token, falling back to the personal `gh` token only
  if the App isn't configured (cascade-fallback principle — never hard-fail while a
  path remains).
- After `limen` itself is transferred to `organvm` (move it **LAST**, per the dossier),
  retarget the secrets to `organvm/limen` and drop the `4444J99/limen` literal in
  `deploy-api.yml:53` (`LIMEN_GITHUB_REPO`).

> Why this is the durable fix: the installation token's authority comes from the **org's
> App**, not a human's OAuth session or billing standing. The June failure mode — a
> personal card hold cascading into "GitHub billing lock → Actions disabled → CI dead" —
> cannot recur, because the App's CI minutes bill to the org and its identity is
> `limen[bot]`, not `4444J99`. The App also natively carries org-admin + workflow
> permissions, so the §1 personal-scope refresh becomes a temporary bridge, not the
> standing posture.

---

## 3. Sequencing (how §1 and §2 fit the consolidation)

1. **Now (bridge):** run §1 `gh auth refresh -s admin:org -s workflow`; canary-transfer
   one repo to prove the grant + org OAuth policy.
2. **Durable:** create + install `limen[bot]` (§2a–2c); store secrets.
3. **Cutover prep (still gated):** resolve the 15 collisions (`docs/CONSOLIDATE-DRYRUN.md
   §3/§5), re-run the dry-run (expect 287 move / 0 skip).
4. **Apply in waves** using the **App installation token** (not the personal token):
   archived + low-value first, `limen` LAST.
5. **Config rewrite:** tasks.yaml `repo:` owners → `organvm/...`, fix
   `deploy-api.yml:LIMEN_GITHUB_REPO`, update `~/Workspace` git remotes; retarget App
   secrets to `organvm/limen`.
6. **Verify fleet green** under the App identity; confirm reversibility on the canary.

The bulk `--apply` remains one of the human-gated triggers. This doc unblocks the
*authority*; it does not run the transfer.
