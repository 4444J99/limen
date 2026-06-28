# Rob Game Lane

Generated: `2026-06-28`

Status: `active`

## Identity

- Lane handle: `rob-game`.
- Canonical project: `MICRO TATO`.
- Source repo: `4444J99/micro-tato`.
- Local checkout: `/Users/4jp/Workspace/micro-tato`.
- Public build repo/surface: `4444J99/micro-tato-play`,
  `https://4444j99.github.io/micro-tato-play/`.
- Relationship to Rob: this is the newer personal/fun game built to play with
  Rob and John F. It is not the Hokage Chess business/workstream lane.

This is a workstream lane, not a new Limen `target_agent`. Route tasks to the
existing agent fleet and add `rob-game` as a label.

## Current Ground Truth

- Game engine: Godot 4.7 / GDScript.
- Local state checked on 2026-06-28: `main...origin/main`, clean.
- Current local head checked on 2026-06-28: `c1976ce seed(B63): build contract for #6 (#20)`.
- The game repo already has its own branch-lane tooling:
  - `./lane.sh new <topic>`
  - `./lane.sh validate`
  - `./lane.sh preview <topic>`
  - `./lane.sh ship <topic>`
  - `./tend.sh [--dry-run|--force|<slug>]`
- The local launch gate is `./lane.sh validate`: Godot headless import plus a
  four-hero soak (`fighter`, `knight`, `cowboy`, `magician`) with zero script
  errors, NaN failures, or normalize warnings.

## Purpose

Use this lane for Micro Tato work that would otherwise be lost in generic game,
Rob, or prompt-history buckets:

- gameplay design packets and build contracts;
- branch/PR batch tending and preview publication;
- Godot implementation tasks;
- playtest/feel-test receipts;
- adaptive audio and reactive visual evolution;
- web/PWA/Android distribution maintenance;
- iOS/TestFlight planning, gated on human spend/Apple account action.

## Allowed Files

For lane packetization in Limen:

- `docs/lanes/rob-game.md`
- `docs/lanes/README.md`
- future Rob-game receipts under `docs/lanes/rob-game/**`
- `tasks.yaml` only when a direct request explicitly asks to create or update
  task-board state

For implementation in the game repo:

- `/Users/4jp/Workspace/micro-tato/README.md`
- `/Users/4jp/Workspace/micro-tato/RUNBOOK.md`
- `/Users/4jp/Workspace/micro-tato/BRANCHING.md`
- `/Users/4jp/Workspace/micro-tato/SESSION_LOG.md`
- `/Users/4jp/Workspace/micro-tato/SESSION_REPORT.md`
- `/Users/4jp/Workspace/micro-tato/COMBAT_DESIGN.md`
- `/Users/4jp/Workspace/micro-tato/batches/**`
- `/Users/4jp/Workspace/micro-tato/scripts/**`
- `/Users/4jp/Workspace/micro-tato/scenes/**`
- `/Users/4jp/Workspace/micro-tato/assets/**`
- `/Users/4jp/Workspace/micro-tato/project.godot`
- `/Users/4jp/Workspace/micro-tato/export_presets.cfg`
- `/Users/4jp/Workspace/micro-tato/build_web.sh`
- `/Users/4jp/Workspace/micro-tato/build_apk.sh`
- `/Users/4jp/Workspace/micro-tato/lane.sh`
- `/Users/4jp/Workspace/micro-tato/tend.sh`

## Forbidden / Stop Gates

- Do not touch `/Users/4jp/Workspace/4444J99/portvs`.
- Do not route this lane to `4444J99/hokage-chess`; that is a separate Rob lane.
- Do not create a new Limen `target_agent` called `rob-game`.
- Do not mutate `tasks.yaml` unless the user explicitly asks for task-board
  state changes.
- Stop before live promotion to the root public build unless the operator asks
  for it. Prefer preview builds for agent work.
- Stop before paid distribution actions: Apple Developer enrollment, Google Play
  console work, signing identities, store submissions, or credential changes.
- Stop before deleting game worktrees, dropping branches, force-pushing branches
  outside the existing `tend.sh` rebase/lease flow, or publishing secrets.
- Stop before creative placement or marketing-channel work unless the task is
  explicitly scoped to that surface.
- For gameplay changes, stop at a green local gate plus preview/receipt when
  motion, feel, or taste needs human playtesting.

## Standard Work Packet

Use this shape for new tasks:

```yaml
labels: [rob-game, micro-tato]
repo: 4444J99/micro-tato
target_agent: <canonical Limen agent>
context: >
  Work only in /Users/4jp/Workspace/micro-tato or a Micro Tato lane worktree.
  Use ./lane.sh new <topic> for implementation lanes. Verify with ./lane.sh
  validate. Publish only previews unless explicitly asked to promote live.
  Leave a receipt naming changed files, branch/PR, preview link if any, and gate
  result.
```

## Resume Commands

Read-only orientation:

```bash
git -C /Users/4jp/Workspace/micro-tato status --branch --short
git -C /Users/4jp/Workspace/micro-tato log --oneline -5
git -C /Users/4jp/Workspace/micro-tato branch -vv
git -C /Users/4jp/Workspace/micro-tato worktree list
```

Inspect active game batches:

```bash
cd /Users/4jp/Workspace/micro-tato
./lane.sh list
./tend.sh --dry-run
```

Validate a candidate lane:

```bash
cd /Users/4jp/Workspace/micro-tato
./lane.sh validate
```

Create a new implementation lane:

```bash
cd /Users/4jp/Workspace/micro-tato
./lane.sh new <topic>
cd .lanes/<topic>
```

Publish a preview only:

```bash
cd /Users/4jp/Workspace/micro-tato
./lane.sh preview <topic>
```

## Receipts Required

Every completed Rob-game packet should leave:

- repo/worktree used;
- branch and commit;
- changed paths;
- validation command and result;
- preview URL or explicit "no preview";
- human feel-test gate, if applicable;
- exact next action.
