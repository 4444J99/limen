# container/ — the one-container migration

**Decided path:** git-deploy / **zero-move** (chosen from 5 adversarially-judged designs,
workflow `wf_6fd8a8f7-9fb`).

## The idea
`~/Workspace/limen` **already is** the container — it's the git repo the live `com.limen.heartbeat`
launchd agent points at, and every hardcoded path (the `$LIMEN_ROOT`-relative lock, the
`dispatch.py` `~/Workspace/.home-cartridge/Code` cart-root, the worktrees root) resolves from it.
So we don't *move* anything — we **fold the scattered slots into it**:

| OS slot (fixed by the OS) | becomes | why |
|---|---|---|
| `~/.limen.env` | absolute **symlink → `limen/env/limen.env`** | bash `.` follows symlinks transparently |
| `~/.claude/settings.json` | absolute **symlink → `limen/container/claude/settings.json`** | Claude reads through symlinks |
| `~/Library/LaunchAgents/com.limen.heartbeat.plist` | **real file, rewritten in place** (byte-identical) | launchd is hostile to symlinked plists (0/10 here are symlinks) |
| `~/.zshrc .zshenv .zprofile .bashrc` | **scrubbed** of the leaked `GEMINI_API_KEY` line | the leak; conductor never read them anyway |

Left real & untouched: `~/Workspace/.home-cartridge` (live co-tenant, hardcoded), `~/.limen-worktrees`, `~/.gemini`.

## Run it
```bash
bash ~/Workspace/limen/container/migrate.sh     # one trigger; pauses before the one near-irreversible touch
bash ~/Workspace/limen/container/rollback.sh    # exact inverse, anytime
```
`migrate.sh` self-preflights, stages additively, performs the gated cutover, proves the wiring with
one heartbeat tick, then backs up to Archive4T + T7Recovery (mountpoint-guarded). It is **idempotent**
(re-runnable), **copy→verify→rename / never delete-first**, and writes `state/deploy.json` *before*
the irreversible step so rollback is total.

## Safety invariants (from the adversarial judges)
- plist stays a **real file** (never a symlink) — content-rewritten byte-identical, reloaded via bootout/bootstrap.
- `~/.limen.env` symlink uses an **absolute** target (a relative one dangles and silently drops the gemini lane).
- secret value is **never printed**; the 4 rc `*.premigrate` backups live in `backup/` at `chmod 700`.
- backups are **mountpoint-guarded** — an unplugged volume is SKIPPED, never created on the internal disk (which would leak the secret).
- `state COMPLETE` is set only after ≥1 frozen backup verifies (preserves the 2-copy invariant).
- `finalize.sh` (separate, later, after N clean heartbeats) is the only point that shreds the `*.premigrate` originals — until then, full rollback is available.

## Backups, frozen
`/Volumes/Archive4T/limen-backups/<UTC>/` and `/Volumes/T7Recovery/limen-backups/<UTC>/` — copy→verify
(git bundle + rsync + sha256 manifest). **Never run from them.**
