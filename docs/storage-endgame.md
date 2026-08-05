# Storage Endgame — the declared roles of every storage rail (ported, redacted)

**Provenance.** Ported 2026-07-15 from three hand-authored operating docs on the archive volume
(the archive of record for the full originals):

- `/Volumes/Archive4T/_OPERATIONS/MASTER-STORAGE-BACKUP-ENDGAME-2026-06-15.md`
- `/Volumes/Archive4T/_OPERATIONS/CLOUD-INTEGRITY-AUDIT-2026-06-15.md`
- `/Volumes/Archive4T/_OPERATIONS/STORAGE-OPERATING-MANUAL-2026-06-15.md`

**Authority model.** This doc records *intent* (why the roles are what they are). The **roles**
live as declared data in [`institutio/governance/storage-roles.yaml`](../institutio/governance/storage-roles.yaml)
(HORREVM, the granary). The **live state** is derived — never hand-maintained — by
`scripts/cloud-storage-doctor.py` each scheduled beat (`logs/cloud-storage-health.json`). If this
prose and the registry disagree, the registry wins; if the registry and reality disagree, the
doctor says so (that is its whole job — the roles were prose-only for a month and rotted silently,
the PREC-2026-07-10 "declared-but-unwired is a defect" pattern).

## Why this exists (the 2026-06-15 findings)

- A 4TB external SSD had become an unstable exFAT archive/workspace/trash mix (kernel panics).
- The internal Mac was in emergency free-space territory.
- iCloud had been accidentally damaged in the past; its low-level File Provider history carried
  stale errors (`missingLastKnownVersion`, `excludedFromSync`, `itemChangedDuringPropagation`,
  `serverUnreachable`) even while high-level sync reported caught-up.
- Google Drive was signed in on the iPhone but unreachable from Apple Files (provider integration
  breakage, not data loss).
- **Root cause of all of it: every provider was present WITHOUT an enforced role** — no clean
  distinction between archive, scratch, sync, backup, and active workspace.

## The roles (mirror of the registry; the registry is authoritative)

| Rail | Role | Never |
|---|---|---|
| **iCloud Drive** | Apple-ecosystem docs + Mac↔iPhone bridge (DailyEngine); cache is system-owned (library-preserve evict-never-delete) | sole/bulk backup; terminal deletion under `~/Library/Mobile Documents` or `~/Library/CloudStorage`; full local mirrors |
| **Google Drive** | Headless ciphertext custody (HORREVM/rclone, `drive.file` scope) + browser-first collab | desktop File Provider app; archive warehouse; sole backup; plaintext private egress |
| **Dropbox** | Headless break-glass grab bag (recovery card + sealed continuity kernel) | desktop File Provider app; archive warehouse; only-backup of anything |
| **OneDrive** | Nothing — dormant by design | any backup role; silent adoption |
| **Backblaze** | Primary offsite/versioned backup for `/` and Archive4T | backing up TM-Mac/Ingress/Scratch; any doctor-initiated bz action |
| **Archive4T** | PRIMARY local archive — SSOT for curated recovered data | TM-only safety; scratch; consumer-sync-folder residence |
| **T7Recovery** | Second local recovery copy until offsite restore proof | scratch; active workspace; premature deletion |
| **Time Machine → TM-Mac** | Local Mac rollback only (optional convenience) | substitute for offsite; backup of Archive4T |
| **Ingress** | Intake zone — nothing archived until promoted | long-term storage; Backblaze selection |
| **Scratch** | Disposable workspace | only home of anything important |

## Cloud rules (the operating manual, unchanged in spirit)

1. Important data is NOT safe unless in **≥2 independent places with ≥1 version history**.
2. iCloud, Dropbox, Google Drive are **sync/collaboration tools by default, NOT backups**.
3. Known problem history in this environment → each provider **must pass trust gates before being
   trusted in any workflow** (declared per rail in the registry; automatable gates run headlessly,
   device-side gates are levers).
4. Never delete originals before restore proof. Never mirror huge archives locally through a sync
   client. Never let a sync client impersonate the durability layer.

## The past failure vector, encoded as drift

The desktop File Provider layer (Dropbox.app / Google Drive.app / OneDrive.app) is what churned,
bloated, and silently broke. It stays **required-absent** — for Drive and Dropbox even after
headless adoption. The doctor red-flags: a desktop app reappearing, a File Provider registration,
a NEW dated `iCloudDrive-iCloudDrive (…)` provider domain beyond the 3 baselined forensic ones,
any unrecognized `~/Library/CloudStorage` entry, or the Archive4T SSOT unmounted.

## Do not do (binding, from the originals + estate law)

- **Never `rm` inside `~/Library/Mobile Documents`** — it deletes iCloud originals. Eviction is
  `brctl evict` / Finder Remove Download only (library-preserve.py owns this).
- Never terminal-delete the baselined CloudStorage remnants (forensic leftovers; removal covenant).
- Never initiate Backblaze actions from automation — `bztransmit`/`bzserv` observation is
  read-only; nudges are the operator's hand.
- No paid tiers; no desktop sync app installs; no plaintext private egress (ciphertext + the one
  non-secret recovery card only — see `L-CLOUD-EGRESS-CONSENT` in `his-hand-levers.json`, PR2).

## Redaction note

The originals embed the operator's Google account string in path listings; it is ported here and
in the registry as the glob `GoogleDrive-*` / `GoogleDrive-<account>`. The doctor masks account
tokens in everything it emits, and its unit tests fail on any `@` in serialized output.
