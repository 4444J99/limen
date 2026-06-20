# Offsite Durability Proposal — the third copy of the irreplaceable data

Date: 2026-06-19
Status: PROPOSAL (propose-only). This document recommends and lays out exact human
steps. It performs no backup, no billing, no auth, and no write to `/Volumes/Archive4T`.
All sizes below were measured by read-only inspection of the Lifeboat on 2026-06-19.

---

## 1. The risk (one paragraph)

The irreplaceable single-source-of-truth data currently exists in exactly **two local
copies in one physical location**: `/Volumes/Archive4T` and its byte-mirror
`/Volumes/T7Recovery`. There is **zero offsite copy and zero versioned copy.** The
Core Rule (`/Volumes/Archive4T/CLAUDE.md`, from `STORAGE-OPERATING-MANUAL`) is explicit:
*"Important data is not safe unless it exists in at least two independent places and at
least one has version history or retention."* Two disks on the same desk are not two
independent places — they share one flood, one fire, one theft, one power surge, one
ransomware blast radius. The moment either of those events happens, the **only surviving
source** of the LOST keystones (Limen / session-meta / Portal), the agent-memory corpus
the archive labels "consciousness-adjacent," the private local Mail/Messages/keychain
stores that were never cloud-synced, and the dirty/unpushed fork commits and reflogs in
`30_CODE` all go to zero at once. This is the one genuine durability gap, and it is the
single highest-leverage safety action available.

---

## 2. Scope tiers (measured 2026-06-19, read-only)

Source root: `/Volumes/Archive4T/RecoveryCopies/CleanUnique-Lifeboat-2026-06-13/`

### Tier 1 — the irreplaceable sliver (SMALLEST, MUST-DO) — ≈ 5–6 GB

This is the data that exists **nowhere else** and is small enough to be offsite-safe
*today*, on any plan, in under an hour. **Start here.**

| Component | Path (under the Lifeboat root) | Size | Files |
|---|---|---|---|
| "Consciousness-adjacent" agent-memory corpus | `20_TEXT/claude-home-agent-records` | 2.6 G | 19,919 |
| Private notes / authored markdown / docs | `20_TEXT/visible-docs` | 1.2 G | 9,533 |
| Local Mail + Messages (not cloud-synced) | `10_PROFILE/private/local-communications-records` | 775 M | — |
| Obsidian/Apple-Notes/ChatGPT-adjacent non-repo text | `20_TEXT/workspaceapfs-nonrepo-records` | 189 M | — |
| Local identity / keychain records | `10_PROFILE/private/local-identity-keychain-records` | 71 M | — |
| Personalization / knowledge records | `10_PROFILE/private/local-personalization-knowledge-records` | 59 M | — |
| Dirty/unpushed forks + reflogs in `30_CODE` (e.g. `are-is-clone-cloud` ≈ 263 M, plus `docs-et-cet-alia`, `gemini-cli`, `train-neural-network`, `auto-ontological-schema`, `semantic-pedantic-grep`) | `30_CODE/repos/path-mirror/.../organization*` | ≈ 0.5–1 G | — |

**Tier-1 total: ≈ 5–6 GB.** (Note: the named code forks live deep under
`30_CODE/repos/path-mirror/Volumes/.../Development-Archive/...`; the single most
load-bearing one, `are-is-clone-cloud`, is a fork of `rclone/rclone` with dirty
working-tree changes and an intact `.git` — verified `git fsck` clean at archive time.)

At ≈ 5–6 GB, Tier 1 costs **well under $0.10/month** to store offsite-versioned on B2.
There is no cost reason to delay it.

### Tier 2 — the full Lifeboat — ≈ 146 GB

`RecoveryCopies/CleanUnique-Lifeboat-2026-06-13/` in its entirety
(`00_SUBSTRATE 10_PROFILE 20_TEXT 30_CODE 40_MEDIA 50_PUBLIC 90_INBOX _MANIFESTS`).
Domain breakdown measured today: `30_CODE` 93 G, `20_TEXT` 30 G, `10_PROFILE` 21 G,
plus media/substrate. This is the curated frozen snapshot. At B2 pricing ≈ **$0.88/mo**.

### Tier 3 — the sparsebundle disk image — ≈ 311 GB

`CleanUnique.apfs.sparsebundle` (39,876 bands, restore-verified). This is the raw
private-by-default archive image. Largest, slowest, most expensive (≈ **$1.87/mo** on
B2). Lowest priority for an *offsite* copy because its authored content is already
represented (de-duplicated and human-organized) inside Tier 2.

### Recommendation on tiers

**Do Tier 1 now** (today, tiny, irreversible-loss exposure removed in <1 hour). Then
backfill **Tier 2** once the encrypted pipeline is proven on Tier 1. Treat **Tier 3**
as optional/last — its unique value over Tier 2 is the byte-exact disk image, which
matters for the SSD-rebuild gate (§6) but not for content survival.

---

## 3. Options compared

**Hard constraint:** this payload contains private comms, keychains, and personal
identity records. **Client-side (end-to-end) encryption is mandatory** — the cloud
provider must never hold plaintext or the encryption key. That rules out any "convenient"
provider-side-only encryption.

| Option | Versioned? | Client-side E2E encryption | Effort | Cost (≈) | Verdict |
|---|---|---|---|---|---|
| **Backblaze B2 + `rclone crypt`** | Yes (B2 lifecycle / object versions) | Yes — rclone encrypts before upload; B2 sees only ciphertext | Medium (CLI, one config) | **~$6/TB/mo** (Tier 1 ≈ $0.04/mo) | **RECOMMENDED** |
| Backblaze B2 + `restic` | Yes (restic snapshots = native versioning + dedup) | Yes — restic encrypts client-side | Medium (one binary, `restic init`) | Same ~$6/TB/mo | **Strong alternative** — better dedup/snapshot UX; needs `brew install restic` |
| Arq (Mac-native GUI) → B2/S3/Wasabi | Yes (Arq keeps versions) | Yes — Arq encrypts client-side | **Low** (GUI, scheduled) | App ~$60 once + storage | Good if a GUI + scheduler is wanted; least CLI |
| Backblaze **Personal** (already installed: `/Library/Backblaze.bzpkg`) | Limited (30-day default version history) | Encryption yes, but **key escrow risk** unless a private key is set; **path-limited** (backs up internal drive, awkward for external archive volumes) | Low | $99/yr flat unlimited | **Not recommended for this** — external-volume + path limits + 30-day-only versioning make it wrong for a frozen archive tier |
| tarsnap | Yes (snapshots) | Yes — strong, audited | Medium (CLI) | **~$250/TB/mo** | Paranoid-grade but ~40x B2 cost; only justify for Tier-1-only if extreme |

### RECOMMENDATION

**Backblaze B2 as the destination, with `rclone crypt` as the client-side encryption
layer.** Rationale:
- `rclone` is **already installed** (`/opt/homebrew/bin/rclone`) and `~/.config/rclone`
  already exists (empty) — zero new tooling for the recommended path.
- B2 is the cheapest credible versioned object store (~$6/TB/mo); Tier 1 is effectively
  free.
- `rclone crypt` encrypts filenames and contents locally before upload — B2 holds only
  ciphertext, satisfying the mandatory-E2E constraint for comms/keychains.
- It scales cleanly from Tier 1 → Tier 2 → Tier 3 with the same one config.

**Secondary recommendation:** if snapshot/version semantics and dedup matter more than
minimal tooling, use **`restic` to B2** instead (`brew install restic`). restic gives
first-class versioned snapshots and pruning; same storage cost. Either is correct. Pick
rclone-crypt to ship today with what's installed; pick restic if you want richer
version history out of the box.

**Avoid** Backblaze Personal for this specific job (path/external-volume limits +
30-day-only history), even though it is already installed — it is the wrong shape for a
frozen archive's third copy.

---

## 4. Exact human steps (the propose-only atoms)

These are the steps **only Anthony can do** (account, payment, keys). Numbered so each
is a single approval atom. Nothing here is executed by the assistant.

1. **Create a Backblaze account** (or sign into an existing one) at
   `https://www.backblaze.com/sign-up/cloud-storage` (B2 Cloud Storage, *not* the
   Personal/Computer-Backup product).

2. **Add a payment method.**
   ⚠️ **KEYSTONE BLOCKER FLAG:** per the fleet memory, the **card-0186 fraud-hold** is
   the root cause that already locked GitHub and Anthropic billing. If card 0186 is the
   only card on file, this step will likely fail the same way. **Use a different,
   non-frozen card or payment method for Backblaze**, or clear the 0186 hold first.
   Flag this before attempting payment so the failure is anticipated, not a surprise.
   (B2's first 10 GB are free — **Tier 1 fits inside the free tier**, so a working card
   is needed only when you graduate to Tier 2/3.)

3. **Create a B2 bucket**, e.g. `archive4t-offsite`, with the bucket set to **Private**.
   Enable **Object Lock / lifecycle to keep prior versions** if offered (this is the
   "versioned/retention" half of the Core Rule).

4. **Generate an Application Key** (Account → Application Keys → *Add a New Application
   Key*). Scope it to the one bucket; capture the `keyID` and `applicationKey`. Store the
   `applicationKey` in the macOS Keychain or a password manager — it is shown only once.

5. **Generate a strong `rclone crypt` passphrase** (this is *your* encryption key; B2
   never sees it). Store it in the password manager. **If this passphrase is lost, the
   offsite copy is unrecoverable** — this is the price of mandatory E2E encryption.
   Write it down in two places you control.

6. **Configure rclone** (one interactive setup, run by Anthony or approved for the
   assistant to run with the keys pasted in):
   ```sh
   rclone config        # create remote "b2" (type: b2; paste keyID + applicationKey)
   rclone config        # create remote "b2crypt" (type: crypt; remote: b2:archive4t-offsite; paste passphrase)
   ```

7. **Kick the first encrypted Tier-1 backup** (the single first command — Tier 1 only,
   read-only on the source, encrypts before upload):
   ```sh
   rclone copy --transfers 8 --fast-list \
     "/Volumes/Archive4T/RecoveryCopies/CleanUnique-Lifeboat-2026-06-13/20_TEXT/claude-home-agent-records" \
     "b2crypt:tier1/claude-home-agent-records" \
     --log-file ~/Workspace/limen/docs/offsite-tier1-run-2026-06-19.log -P
   ```
   Then repeat `rclone copy` for the remaining Tier-1 paths in §2 (`visible-docs`,
   `local-communications-records`, `workspaceapfs-nonrepo-records`,
   `local-identity-keychain-records`, `local-personalization-knowledge-records`, and the
   named `30_CODE` forks). `rclone` reads the source read-only — it never writes to
   `/Volumes/Archive4T`.

**The single first human step is Step 1** (create the B2 account), because everything
else gates on having an account + key. The single first *command* once configured is the
`rclone copy` in Step 7.

---

## 5. Dry-run / verification plan and cadence

### Dry-run (do before the real Step 7)
```sh
rclone copy --dry-run "<source>" "b2crypt:tier1/..." -P    # lists what WOULD upload, transfers nothing
```

### Post-backup verification (prove it restores — the copy is worthless until restore is proven)
1. `rclone check "<source>" "b2crypt:tier1/<name>" --one-way` — confirms every source
   file is present and hash-matched in the encrypted remote.
2. **Restore-to-scratch test:** `rclone copy "b2crypt:tier1/claude-home-agent-records"
   /tmp/offsite-restore-test` then `diff -r` (or compare `du -sh` + file counts) against
   the source. This proves the *decryption path and passphrase actually work* — the most
   common silent failure is an unrecoverable passphrase.
3. Record results into `~/Workspace/limen/docs/offsite-tier1-verify-2026-06-19.md`
   (NOT into `/Volumes/Archive4T`).

### Cadence
- **Tier 1 (frozen):** the Lifeboat is frozen, so a **single verified upload** satisfies
  durability; re-verify quarterly with `rclone check`.
- **If you later point this at live `~/Workspace` data**, run a **daily** scheduled
  `rclone copy` (launchd/cron) and a **weekly** `rclone check`. restic users: daily
  `restic backup` + weekly `restic check --read-data-subset`.
- Keep both local copies (Archive4T + T7Recovery) untouched. This adds a third,
  independent, offsite, versioned copy — it does not replace either local copy.

---

## 6. This offsite copy is a precondition that unlocks reclamation (leverage beyond safety)

The Lifeboat manifests already define a hard gate that this proposal directly satisfies.
From `_MANIFESTS/off-ssd-backup-execution-packet-2026-06-13.md` and the preflight result
(`off-ssd-backup-preflight-readonly-result-2026-06-13.md`): the current blocker is
literally `BLOCKED_FOR_COPY: fewer than two physical external disks are mounted`, and the
gate flags **"off-SSD backup verified," "exact-path cleanup approved," "APFS rebuild
approved," and "final polluted ExFAT wipe approved" all remain `false`.** The APFS-rebuild
gate states that **no SSD reformat is approved until a verified off-SSD copy exists.**

Important distinction this proposal closes: the existing packet only contemplated a
**second *local* physically-separate disk** as the off-SSD destination. That still would
not satisfy the Core Rule's *offsite + versioned* requirement. An **offsite versioned B2
copy is strictly stronger** — it satisfies both the manifest's off-SSD gate *and* the
Core Rule simultaneously. Therefore, completing even **Tier 1 + Tier 2** to B2 is the
precondition that flips "off-SSD backup verified" toward true and unblocks the downstream
reclamation chain (cleanup → APFS rebuild → SSD wipe) that is currently frozen for lack
of a safe third copy. The offsite copy has leverage well beyond safety: **it is the key
that unlocks ~300 GB of SSD reclamation that is otherwise permanently gated.**

(Reclamation itself remains separately gated and is NOT proposed here — copy → verify →
then, and only then, a future explicit cleanup decision. Never delete first.)
