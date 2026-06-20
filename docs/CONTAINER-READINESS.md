# One-Container Cutover — Readiness Report

Generated 2026-06-19 by a read-only readiness pass. No files were moved; `migrate.sh`
was NOT run. This report supersedes the ledger-TODO assumptions where they conflict with
the verified live state below.

## TL;DR

**NOT ready for the full cutover.** Two hard blockers and one scope conflict:

1. **HARD-RULE VIOLATION — internal free disk = 69 GiB, below the 80 GiB stop-work
   floor.** `migrate.sh:58` (`free > 80`) will ABORT on preflight. This is the gating
   blocker even before scope.
2. **No external backups exist yet.** Both `Archive4T` and `T7Recovery` are mounted, but
   neither has a `limen-backups/` dir — the cutover never reached Step 12. The 2-copy
   invariant is not yet satisfied for the conductor.
3. **Scope conflict (the "ONE folder" ask).** Folding the bulky state dirs into the repo
   would push ~11G onto an internal disk that is already under the floor, and `~/.gemini`
   (8.7G, mostly `antigravity-cli`) is explicitly marked "leave REAL" in the base
   manifest. The extended plan resolves this with symlink-with-verify + reference-only
   bins (see `container/manifest-extended.tsv`).

The staged half already ran cleanly (S1-S3) and is reversible. The single human action
that unblocks the most is not "mount a volume" — both are already mounted — it is
**free internal disk above 80 GiB** (and decide the `.gemini` scope).

## Preconditions — checked (read-only)

| Precondition | Required by | Status | Evidence |
|---|---|---|---|
| git toplevel == `~/Workspace/limen` | migrate.sh:55 | PASS | `git rev-parse --show-toplevel` |
| branch == `heal/conductor-restart-2026-06-16` | migrate.sh:56 (warn only) | PASS | current branch matches |
| launchd agent `com.limen.heartbeat` LOADED | migrate.sh:57 (die) | PASS | `launchctl print` → loaded |
| internal free > 80 GiB | migrate.sh:58 (die) + CLAUDE.md HARD RULE | **FAIL** | `df -g /` → **69 GiB** |
| `~/.limen.env` present | migrate.sh:59 (die) | PASS | real file, 69 bytes |
| `~/.limen.env` perms 0600 | migrate.sh:61 (warn) | PASS | `stat` → 600 |
| exactly 1 `GEMINI_API_KEY=` line | migrate.sh:62 (die) | PASS | grep -c → 1 |
| no stale `logs/.saturate.lock.d` | migrate.sh:64 (die) | PASS | dir absent |
| `container-pre-deploy` tag exists (rollback anchor) | rollback.sh:49 | PASS | tag → 9721722 |
| external backup volume mounted | migrate.sh:200-206 | PASS (both) | Archive4T + T7Recovery mounted |
| backups already exist | 2-copy invariant | **FAIL** | no `limen-backups/` on either volume |
| rollback tested | safety | **NOT TESTED** | no cutover has occurred to roll back; dry-read of rollback.sh shows it is a clean inverse and the anchor tag + premigrate machinery exist |

## Correction to the ledger TODO

- The TODO said `state/deploy.json` does not exist. **It exists**
  (`container/state/deploy.json`, 102 bytes) with `completed_steps: [S1, S2, S3]` and no
  slots. So the kit DID run — but only the additive STAGED half (`STAGE_ONLY` path,
  migrate.sh:120-124). It is NOT marked COMPLETE, and no OS slot was touched
  (`~/.limen.env` is still a real file, no `*.premigrate` in `$HOME`). The secret is
  already staged at `container/env/limen.env` (S3) and settings merged at
  `container/claude/settings.json` (S2).
- The TODO estimated `~/.codex` at 328M and `~/.gemini` unspecified. **Live sizes:**
  `~/.claude` 2.1G, `~/.codex` 468M, `~/.gemini` **8.7G** (almost entirely
  `.gemini/antigravity-cli`, i.e. the agy install state). The cost of "one folder" is
  ~11G, not ~2.4G.

## The "ONE folder" gap and the extended plan

The base `manifest.tsv` only folds four config slots (secret, claude settings, plist,
rc scrub). The literal ask — one folder including state dirs and bins — needs two new
KINDs, both designed to honor "names are outputs, not inputs" and the disk floor. Full
plan in **`container/manifest-extended.tsv`** (a PLAN file; nothing moved). Summary:

- **State dirs → `symlink-state-absolute`** (copy → verify with rsync+du → `mv -n`
  original to `.premigrate` → `ln -s` absolute → re-read a known file to prove the link
  resolves). Caches (`*.sqlite-wal/-shm`, codex `logs_*.sqlite` ~93M, `.gemini` tmp) are
  gitignored. This keeps state inside the container WITHOUT copying multi-GB blobs into
  git.
- **`~/.gemini` is the exception.** Base manifest says leave it REAL; it is 8.7G and on a
  disk already under the floor. RECOMMEND: keep `~/.gemini` real, or sub-slot only
  `.gemini/config` + `.gemini/history` and leave `antigravity-cli` in place. Do NOT fold
  the whole 8.7G.
- **Bins → `reference-only`.** codex/agy/gemini/jules/opencode are brew-managed; claude is
  self-updated under `~/.local/share/claude/versions/<v>` (three versions present —
  a symlink would dangle to a stale version after the next update). Moving any of them
  breaks its manager and gets re-clobbered on upgrade. So: inventory them to
  `container/state/bins.json` (path + realpath + version + manager) and let dispatch
  derive the path at use-time / pin via the existing `LIMEN_<AGENT>_BIN` knobs. Never move
  a bin.
- **Secret-bearing files flagged for guard:** `~/.codex/auth.json`, `~/.codex/config.toml`,
  `~/.claude.json` (separate from the dir). Must stay out of git and only ever be backed
  up to a mountpoint-guarded external volume — same discipline migrate.sh already applies
  to `~/.limen.env`.

## The single blocking human action

**Free internal disk to ≥ 80 GiB (ideally ≥ 90–100 GiB for headroom), then decide the
`.gemini` scope.** Both external volumes are already mounted, so the originally-suspected
"mount + name a backup volume" is already done. The real gate is the disk floor — it
blocks even the config-only cutover, and the extended state-dir fold makes it worse.
Concretely:

1. Reclaim internal disk above 80 GiB (e.g. prune old `~/.local/share/claude/versions/`
   2.1.179/2.1.181, clear codex/gemini caches, empty Trash — all OUTSIDE this readonly
   pass and OUTSIDE Archive4T).
2. Confirm the `.gemini` decision (recommend: keep 8.7G real; do not fold).

Everything downstream (the gated config cutover steps 4-13, then the optional extended
state-dir symlinks) is mechanical and reversible once the floor is cleared.

## Recommended sequence (after the floor is cleared)

1. **Dry-confirm** by re-running the staged half: `STAGE_ONLY=1 bash
   container/migrate.sh` — should report S1-S3 already done, touch no OS slot.
2. **Config cutover:** `bash container/migrate.sh` (gated; pauses before the one plist
   rewrite). This satisfies the base manifest and writes deploy.json slots before the
   irreversible touch.
3. **Prove rollback once, deliberately:** after the config cutover and one clean
   heartbeat, run `bash container/rollback.sh` in a window where downtime is OK, confirm
   it restores real files + reloads the agent, then re-migrate. This is the only way to
   move "rollback tested" from NOT-TESTED to PASS.
4. **State dirs (optional, extended):** implement `manifest-extended.tsv` as a separate
   gated step — symlink `~/.claude` and `~/.codex` with verify; leave `~/.gemini` real;
   write `bins.json` (reference-only). Re-confirm disk floor BEFORE this step.
5. **Backups:** ensure Step 12 runs with both volumes mounted so `limen-backups/<UTC>/`
   appears on each, restoring the 2-copy invariant. Only then is `state COMPLETE` legit.

## Do-not list (carried from CLAUDE.md / kit)

- Do not fold `~/.gemini` (8.7G) into the repo / internal disk.
- Do not move or symlink the bins — they are package-manager-owned; pin via
  `LIMEN_<AGENT>_BIN` instead.
- Do not let any secret (`~/.limen.env`, `auth.json`, `config.toml`, `~/.claude.json`)
  enter git or land on the internal disk as a backup — mountpoint-guard, external only.
- Do not run any of this while internal free is < 80 GiB.
- Do not touch Archive4T / T7Recovery except as mountpoint-guarded backup targets.
