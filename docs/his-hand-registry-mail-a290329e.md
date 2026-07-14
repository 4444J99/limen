# His-Hand Registry — mail organism (session a290329e, 2026-06-22)

Everything from the "tend both mail lanes" build that is **yours to pull or decide** — surfaced
here (a new, non-contended file) rather than hand-driven, since other interactive sessions + the
daemon are live. Nothing below blocks the keyless value already shipped; these only raise the
ceiling. Nothing here ever sends or deletes — reversible only.

## DEPLOY (one merge activates the autonomic mail lane)
- **Merge this branch → `main`:** `worktree-glimmering-mapping-whistle` (limen). On merge,
  `sync-release.sh` ff's it into the live checkout and the **`C_MAIL` voice** goes live: every 6
  beats it sweeps the inbox (flag fires + archive folder-store noise, reversible), rebuilds the
  obligations ledger, and refreshes the face. A PR is open for the merge organ / your one-tap merge.
  Until merged, the live daemon runs the old `main` (no mail voice yet); all the work is staged + verified.
- **What goes live:** `scripts/heartbeat-loop.sh` (+`C_MAIL` cadence), `scripts/mail-beat.sh`,
  `scripts/obligations-view.py` → face at **http://127.0.0.1:8787/obligations.html**.

## macOS Automation permission (operational, one-time)
- The launchd daemon needs **Automation → Mail** permission to drive Mail.app via osascript. Without
  it the sweep **fails open** (the ledger/face still rebuild from existing receipts; no crash). Grant
  it once if you want the daemon to flag/archive new arrivals autonomically.

## Cross-repo: universal-mail--automation (organvm/universal-mail--automation)
- New mail-organ source is **already on disk** at `~/Workspace/universal-mail--automation` (the daemon
  reads it directly, so it is effectively deployed): `core/protocols.py`, `core/unsubscribe.py`,
  `obligations_build.py`, `draft_writer.py`, plus edits to `providers/mailapp.py` (keyless `create_draft`)
  and `inbox_sweep.py` (`--flag-only-gmail`). The **capture organ** (C_BACKUP) commits + pushes every
  workspace repo additively, so these durably reach `main` without me hand-merging that repo's contended main.

## Levers — raise the ceiling (never forced; also rendered in the obligations face)
- **L-MCP** — expand the Gmail MCP connector to write scope (`gmail.modify`) in claude.ai. Re-tested
  2026-06-22: still read-only. Unlocks reliable keyless Gmail **archive + drafts** in any live session.
- **L-IMAP-APP-PW** — generate a Google app-password (account.google.com → Security → App passwords).
  Cleanest durable path for the **headless daemon**: reliable Gmail archive/draft over IMAP, no weekly
  token death, no browser-driving. ~60s once.
- **L-OAUTH** — revive the Gmail OAuth app: fresh consent + flip to **Production** publishing (stops the
  7-day testing-mode token expiry). I can browser-drive the consent when you want it.
- **`LIMEN_NTFY_TOPIC`** — set it to push high-priority obligations to your phone (opt-in).
- **`LIMEN_MAIL_DRAFTS=1`** — turn ON persisting reply drafts to your Mail **Drafts** folder (keyless,
  idempotent, capped, **never sent**). Default OFF; reply drafts are already visible in the ledger/face.

## Housekeeping
- A self-addressed test draft is in your Gmail **Drafts**: subject *"[Limen] draft-persistence
  self-test — safe to delete"*. It proved the keyless draft path works; **safe to delete**.

## Verification (before this was staged)
- 5 adversarial safety verifiers, all green: never-sends ✅ · never-deletes ✅ · daemon-safe ✅
  (bounded ≤240s/account; the 40-min Gmail-archive loop is skipped) · no-secrets ✅ · idempotent ✅.

---

## UPDATE 2026-07-14 — ROOT CAUSE of "why is Gmail still messy" (supersedes the stale framing above)

The lever **L-IMAP-APP-PW** above ("generate a Google app-password") is **stale**: the app-password
**already exists** at `op://Private/gmail-app-pw-2026-06-06` (organ-homed; creds-hydrate lanes
`gmail (C_MAIL app-password)` → `GMAIL_APP_PASSWORD`, `.../username` → `GMAIL_USER`, both `enabled`).
Nothing needs to be *generated*.

**The actual failure (diagnosed, code+log-grounded):** the 1Password **service account cannot read
that op:// item**, so headless hydration `SKIP`s it fail-open and `GMAIL_APP_PASSWORD`/`GMAIL_USER`
never reach `~/.limen.env`. Downstream, the mail organ can't authenticate to Gmail over IMAP, so the
Gmail inbox never auto-cleans. This was filed on the credential Wall (#320 / tombstone audit) as a
**"non-blocking" SA vault-grant residual** — that classification was wrong; it **blocks the mail organ.**

### The one irreducible atom (a 1Password-console action — owned by the credential estate, NOT recited at the operator)
Make `op read op://Private/gmail-app-pw-2026-06-06/{password,username}` succeed **under the service
account** (`~/.config/op/service-account-token`). Three candidate causes, resolve at the owner:
1. **SA lacks a read grant** on the vault holding the item (most likely). **Secure form:** do NOT grant
   a headless service account access to the `Private` (crown-jewel) vault — instead **re-home the item
   into an SA-readable automation/service vault** and update the two `ref`s in `creds-hydrate.py`.
2. **Field-name mismatch** — the item's field isn't literally `password`/`username` (a code-only fix to
   the `ref`, no 1Password change).
3. **Item moved** to a different vault path.
Homed on Wall **#320** / credential issue **#261**. Disambiguating requires reading the op item, which
is a credential-estate/admin action — not an ad-hoc vault probe from a session.

### Secondary (ad-hoc shells only): `~/.zshenv` lost the `OP_SERVICE_ACCOUNT_TOKEN` export
The SA token **file** is installed but `~/.zshenv` no longer exports it, so interactively-run tools see
`op` "not signed in". Owned by `scripts/op-service-account.sh install` (re-wire) + the **domus-genoma
cartridge**, which must **re-assert** the export on checkout so a session bounce can't silently unwire
it again. `his-hand-levers.json` line ~252 still *claims* this is "ALREADY CURED … exported via
~/.zshenv" — that claim is false today and `dialogs-silenced.sh` should be the predicate that catches
the drift.

### What is now wired on the limen side so this flows automatically the instant the atom resolves
- **`creds-hydrate.py`:** the two Gmail lanes are marked `required: True`; `--verify` now prints a loud
  `✗ REQUIRED, NOT materialized` and **exits 1** (was a silent `?`), so the beat log surfaces the exact
  failing ref every beat instead of rotting green. Verified 2026-07-14: `--verify` exit=1, names both refs.
- **`mail-beat.sh` step 1b:** runs `gmail_imap_sweep.py --apply` (true `\Inbox`-label archive, reversible,
  starred/protected gated, receipt = undo manifest) **gated on `GMAIL_APP_PASSWORD` + `GMAIL_USER`** — a
  no-op today (logs the skip loudly), auto-archives Gmail the moment the credential hydrates. Opt out:
  `LIMEN_MAIL_GMAIL_ARCHIVE=0`.
