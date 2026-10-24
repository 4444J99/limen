# iCloud + iPhone storage: dedupe, unify, offload

Make iCloud Drive one clean tree that the Mac and the iPhone both reach. Stop the numbered-duplicate
churn, store the iPhone's data off the device, and settle the Google Drive leg. Remediation is safe
by construction: archive, never delete, and checksum-verify everything.

Tools (all in `scripts/`):

| Tool | Role |
|---|---|
| `icloud-dedupe.py` | numbered-duplicate engine: `--census`, `--dry-run`/`--replan`, `--status`, `--apply --group G`, `--verify` |
| `icloud-mac-import.sh` | move local `~/Documents` and `~/Desktop` user content into the iCloud intake folder (same-volume rename) |
| `iphone-offload.sh` | encrypted full backup plus DCIM pull from a trusted iPhone; never deletes from the phone |
| `cloud-storage-doctor.py` | sibling sensor; checks the rails in `institutio/governance/storage-roles.yaml` |

Tests: `tests/test_icloud_dedupe.py` (hermetic, synthetic trees; `uv run --with pytest pytest tests/test_icloud_dedupe.py -q`).

## Diagnosis findings (read-only census, 2026-10-23)

- **Duplicates:** 146 numbered variants in 12 groups under iCloud `Documents/` and `Desktop/`. They
  were born in 5 server-side bulk bursts: 2025-11-24, 2026-02-18, and 3x on 2026-02-19. Client
  resets followed on 2026-03-25 and 2026-06-12.
- **Cause:** Desktop & Documents re-enables, plus client resets that merged against an existing
  iCloud tree. No automation actor was found. Checked: LaunchAgents, Domus/limen grep, Shortcuts
  (0 triggers), Services, MDM.
- **Where the content sits:** in every taxonomy group the unsuffixed folder was empty and exactly
  one numbered variant held the content. Deleting by name pattern would have destroyed data.
- **Google Drive:** the Mac has no client. The `googledrive` rail in `storage-roles.yaml` forbids a
  desktop File Provider install. The phone's Google apps are on the Gmail account, whose Drive has
  no phone uploads, so phone backup to Drive is not configured. It is not failing.
- **iPhone (iPhone17,2, iOS 27.2):**
  - 233/256 GB used.
  - `AmountDataAvailable` is 23.9 GB, while `TotalDataAvailable` is 188.6 GB. The field semantics
    are unconfirmed; the gap suggests purgeable or cache data.
  - User apps take 62 GB, mostly app data. Top: Sniffies 8.2, Instagram 4.2, ChatGPT 2.7,
    YouTube 2.6, Audible 2.1, Snapchat 2.1 (GB).

## Method

1. **Dedupe engine (single writer):**
   - Classify each variant as KEEPER, EMPTY, SUBSET or DIVERGENT, keyed on (relpath, size), with
     SUBSET re-proven by sha256 against the keeper.
   - Archive variants to `/Volumes/Archive4T/icloud-dedupe-2026-10-23/` via `ditto`, then sha256 +
     xattr verify, F_FULLFSYNC, from-disk re-hash, re-hash the source, and unlink only the
     recorded set (directories by `rmdir` only).
   - Rename the keeper to the unsuffixed name.
   - Wait for `brctl` caught-up before mutating, between steps, and after the rename.
   - `--apply` refuses if the live tree differs from the reviewed `plan.json` (exit 5), or if iCloud
     does not settle (exit 4).
2. **`99_System_Backups`:** UNION_COPY to the archive with a sha256 manifest. iCloud originals are
   retained; removal is an open decision.
3. **Unify:** `icloud-mac-import.sh` moves the user documents from local `~/Documents` and
   `~/Desktop` into `Documents/00_Inbox_Triage/Mac-import-<date>/`. This is a same-volume rename.
   App-state dirs, dotfiles and the Domus TCC sentinel stay local. The Desktop & Documents toggle
   stays **off** deliberately, because enabling it against a non-empty iCloud tree is what mints
   `Documents - <host> N` copies.
4. **iPhone:** `iphone-offload.sh` takes an encrypted full backup (pymobiledevice3 `backup2`) plus a
   DCIM AFC pull with a sha256 manifest, to `/Volumes/Archive4T/iphone-offload/`. Nothing is
   deleted from the phone; the on-device steps are human-only.

## Green definition

- **G1:** no ` N`-suffixed folders under iCloud `Documents/` or `Desktop/`, except
  `99_System_Backups NN` while its removal decision is open.
- **G2:** the engine's `--verify` prints `LOST=0`, checked by (variant, relpath, size, sha256).
- **G3:** `brctl status` is caught-up.
- **G4:** a 7-day recheck on **2026-10-31** shows no new numbered variants.
- **G5:** the `FXICloudDrive*` flags are 0, and that is the recorded, deliberate state.
- **G6:** the iPhone backup `Status.plist` reads `SnapshotState=finished`, and the DCIM manifest exists.

## Current status (2026-10-24)

Done and verified on disk:

- All 12 duplicate groups except `99_System_Backups` are applied with exit 0: Desktop,
  `Documents - <host>`, `- 1`, and 00 through 07. iCloud `Documents/` now has one folder per
  taxonomy name. 3 content-free conflict copies that came back after renames (`- 1 13`,
  `03_Legal_and_Contracts 2`) were removed. They were empty.
- Every archived variant is in `/Volumes/Archive4T/icloud-dedupe-2026-10-23/`, with
  before/after/sha256 manifests.
- Unify-by-import: 33 items (219 files) moved into `Documents/00_Inbox_Triage/Mac-import-2026-10-24/`.
  File counts matched before and after. Manifest: `manifests/mac-import-2026-10-24.tsv`.
- `brctl` is caught-up. `FXICloudDriveDesktop` and `FXICloudDriveDocuments` are both 0, deliberately.
- iPhone: an encrypted 76.7 GB backup finished (`SnapshotState=finished`), and 99 camera-roll files
  (502 MB) were pulled with sha256. Nothing was deleted from the phone.

Interrupted (operator stopped the run 2026-10-24, after about 5 h with no output):

- The `99_System_Backups` UNION_COPY is partial: 3.8 GB of about 10 GB copied. This mode never
  removes iCloud originals, so the 17 `99_System_Backups*` folders are untouched.
- The final `--verify` (LOST=0 check) **has not run**, so G2 is unproven.

Not done / human-only:

- BLOCKED: iPhone on-device steps (below).
- Owner ruling needed on the two registry items (see Registry disclosures).

## How to resume

The engine now keeps its state under `--state-dir` (default
`$LIMEN_CUSTODY_STAGING_ROOT/icloud-dedupe`, else
`~/Workspace/limen/.limen-private/custody-staging/icloud-dedupe`, created 0700) and the archive under
`--archive-root` (default `/Volumes/Archive4T/icloud-dedupe-2026-10-23`, so the existing manifests
stay valid).

The 2026-10-23 run's reviewed `plan.json`, `census.json`, `PREVIEW.md`, both apply logs and the
iPhone run log were copied (sha256-matched) into the default state dir on 2026-10-24, so the
defaults resume it directly. Check where things stand without touching anything:

```bash
python3 -I scripts/icloud-dedupe.py --status
```

`--status` prints per-group state (applied / STARTED / pending), UNION_COPY progress against the
plan, and whether the writer lock is held. Then resume and verify:

```bash
python3 -I scripts/icloud-dedupe.py --apply --group 99_System_Backups
python3 -I scripts/icloud-dedupe.py --verify
```

Both print a flushed progress line at least every 60 s (files done/total, bytes done/total, current
path; brctl elapsed and last state while waiting to settle). A run that is silent for more than a
minute is hung, not working: check `--status` from a second terminal. The union copy resumes by
hashing what is already in the archive, so interrupting it again is safe. Do not rerun the old
`run_rest.sh`: group 03 is already applied, so its plan check would refuse.

If the live tree has legitimately moved since the plan was reviewed, `--apply` exits 5 and prints the
differences; review them, then regenerate deliberately with `--dry-run --replan` (never to silence a
refusal you have not read).

Importing more local content (dry-run first, then real):

```bash
bash scripts/icloud-mac-import.sh --dry-run --date 2026-10-31
bash scripts/icloud-mac-import.sh --date 2026-10-31
```

## iPhone runbook (human-only)

The offload tool needs a person at the phone. Steps 1-5 prepare and run it; step 6 is on-device and
only starts after step 5 verifies and the archive is copied elsewhere.

1. **Plug in.** Connect the iPhone by USB (cable direct to the Mac) and mount `/Volumes/Archive4T`.
   Verify: `pymobiledevice3 usbmux list --usb` shows your UDID; `ls /Volumes/Archive4T` works.
2. **Unlock** the phone and keep it awake.
   Verify: `pymobiledevice3 lockdown info` prints JSON.
3. **Tap Trust** on the phone and enter the passcode.
   Verify: `pymobiledevice3 lockdown get com.apple.disk_usage` returns capacity numbers.
4. **Enable encrypted backup** (you type the password; never share it, keep it in your password manager):
   `pymobiledevice3 backup2 encryption on -b /Volumes/Archive4T/iphone-offload/<UDID>/<YYYYMMDD>/backup`
   Verify: `pymobiledevice3 lockdown get com.apple.mobile.backup WillEncrypt` prints `true`.
5. **Run the script.** First `bash scripts/iphone-offload.sh --dry-run` (read-only plan), then
   `bash scripts/iphone-offload.sh`. The UDID is detected (pass `--udid` if several are attached or
   the phone is also Wi-Fi-paired). Verify: `receipt.json` and `DCIM.sha256` exist under
   `/Volumes/Archive4T/iphone-offload/<UDID>/<YYYYMMDD>/`; `cd DCIM && shasum -a 256 -c ../DCIM.sha256 | grep -vc ': OK'`
   is 0; `pymobiledevice3 backup2 info <backup dir>` reads the backup.
6. **On the phone:**
   - **Settings > Apple Account > iCloud > Photos:** iCloud Photos ON and **Optimize iPhone Storage**
     selected. Confirm this; it is inferred, not observed, from the 99-file DCIM.
   - **Settings > General > iPhone Storage:** enable **Offload Unused Apps**. Then offload, not
     delete, the large data holders you rarely open, so their documents are kept.
   - In each heavy app, clear its cache from inside the app (Instagram, Snapchat, YouTube, Chrome, ChatGPT).
   - **Messages:** Settings > Messages > Keep Messages > 1 Year, and review large attachments under
     iPhone Storage > Messages.
   - **Google Photos:** if Gmail-account photo backup is wanted, open the app, tap your profile,
     choose Backup, turn it on, and sign in as the Gmail account.
   - Re-read the free space. With purgeable space reclaimed, `AmountDataAvailable` should rise well
     above 23.9 GB; re-run `--dry-run` to see the new used bytes.

## Registry disclosures

Tracked in issue #3195. `institutio/governance/storage-roles.yaml` was **not** edited.

- The three empty `iCloudDrive-iCloudDrive (...)` remnants under `~/Library/CloudStorage` were
  removed. They are the `accepted_remnants` the `icloud` rail tolerates up to 3 of.
- The dedupe's in-iCloud removals are limited to EMPTY variants and hash-proven SUBSET duplicates,
  and every removed byte has a verified archive copy. That is still terminal deletion inside
  `~/Library/Mobile Documents`, which the `icloud` rail lists under `never:`. **Pending owner
  ruling**; `icloud-dedupe.py` states this in its docstring and must not be extended to new groups
  (or to the UNION_COPY originals) before the ruling.

## 7-day recheck: 2026-10-31

1. `python3 -I scripts/icloud-dedupe.py --dry-run`: no new numbered variants (G1, G4), and the
   `drift` section lists nothing unexpected (refresh the baseline first with `--census` if needed).
2. `python3 -I scripts/icloud-dedupe.py --verify`: `LOST=0` (G2).
3. `brctl status` caught-up (G3); `defaults read com.apple.finder FXICloudDriveDesktop` and
   `FXICloudDriveDocuments` both `0` (G5).
4. `python3 scripts/cloud-storage-doctor.py --check`: no drift on the `icloud` rail.
5. If new ` N` folders appeared, the Desktop & Documents toggle or a client reset re-minted them:
   find the trigger before running `--apply` again.
