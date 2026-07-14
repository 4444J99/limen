# Workstream Kickstart

Use this when a prompt has several real lanes and the right move is to split the work into a bounded,
resumable surface instead of holding everything in the chat.

For a closeout successor or a new autonomous initiative, use autonomous capsule mode:

```bash
workstream --autonomous --prompt-file /path/to/next-session.md limen next-epoch
```

Autonomous mode refuses a missing prompt. Its README is passed to Codex as the initial prompt and
includes a live derive-not-force contract: re-probe remote/CI, task owners, handoff, provider
headroom, mounts, host pressure, active sessions, and lifecycle custody; then derive `continue`,
`switch`, `wait_relay`, `settled`, or `invalid`. It does not pin a future model, task count, duration,
or desired ending.

```bash
/Users/4jp/Workspace/limen/scripts/start-worktree-session.sh --shell --prompt "short objective and constraints" limen my-workstream
```

After `install.sh`, the shortcut is:

```bash
workstream --prompt "short objective and constraints" limen my-workstream
```

The command works from Terminal, Kitty, Ghostty, Warp, or any normal shell. It creates or reuses
`<repo>/.worktrees/<slug>` on `work/<slug>`, then writes a private kickoff README at:

```text
<repo>/.worktrees/<slug>/.limen-workstream/README.md
```

It also writes:

```text
<repo>/.worktrees/<slug>/.limen-workstream/kickstart.sh
```

Run it from any terminal with:

```bash
bash <repo>/.worktrees/<slug>/.limen-workstream/kickstart.sh
```

The README contains the repo path, branch, base ref, origin URL, status at kickoff, prompt packet,
first-five-minute checklist, dynamic environment contract (in autonomous mode), and closeout rules.
The `.limen-workstream/` directory is locally
excluded so creating the workstream does not itself make the repo dirty.

## Current Leads

- Triptych video canon: keep the source commit pushed, use media atom manifests to classify the 2 GB
  payload, then offload or regenerate/delete generated lanes only after acceptance.
- Domus: continue from the clean `work/universal-entry-20260629` branch; do not blindly push or reset
  the polluted original branch without an explicit retire plan.
- Maddie texts: keep raw transcript outputs private; use the weekend assessment to set a bounded
  payment/scope boundary before taking more implementation work.
- Limen lifecycle: keep worktree pressure, remote receipts, and cleanup at session boundaries rather
  than relying on memory or manual reminders.

## Active Packets Created 2026-06-29

Triptych media offload:

```bash
bash /Users/4jp/Workspace/4444J99/portvs/.worktrees/triptych-media-offload-20260629/.limen-workstream/kickstart.sh
```

Domus quarantine retire:

```bash
bash /Users/4jp/Workspace/domus-genoma/.worktrees/domus-quarantine-retire-20260629/.limen-workstream/kickstart.sh
```

Maddie boundary:

```bash
bash /Users/4jp/Workspace/4444J99/relationship-pipeline/.worktrees/maddie-boundary-20260629/.limen-workstream/kickstart.sh
```

Current implementation lane:

```bash
bash /Users/4jp/Workspace/limen/.worktrees/workstream-kickstart-20260629/.limen-workstream/kickstart.sh
```

## Pattern

1. Create a worktree per logical lane.
2. Put the prompt/context in `.limen-workstream/README.md`.
3. Do the source work in the worktree.
4. Verify.
5. Commit and push.
6. For the first push from a new branch, use `git push -u origin HEAD`.
7. Report local/remote state and classify anything large or generated.
