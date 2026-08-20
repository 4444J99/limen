# Omega substrate convergence successor

This is the durable public index for the private continuation capsule emitted
by the Omega literal-substrate implementation closeout. Read these tracked
modules in order:

1. [`intent.md`](intent.md) — objective, authorities, and prohibitions.
2. [`runtime.md`](runtime.md) — live probes and routing rules.
3. [`closeout.md`](closeout.md) — executable ending and switch conditions.
4. [`RELAY.md`](RELAY.md) — producer receipts and exact handoff state.
5. [`workstream.json`](workstream.json) — redacted finite-runway contract.

The private `.limen-workstream/` directory contains the validated prompt
modules and identity hashes. Its contents stay local; `workstream.json` is the
remote custody receipt.

## Launch

```bash
workspace_root="${WORKSPACE_ROOT:-$HOME/Workspace}"
canonical_limen_root="${LIMEN_ROOT:-$workspace_root/library/engine/organvm/limen}"
canonical_capsule="$canonical_limen_root/.worktrees/omega-substrate-convergence-next"
legacy_capsule="$workspace_root/limen/.worktrees/omega-substrate-convergence-next"
if [[ -x "$canonical_capsule/.limen-workstream/kickstart.sh" ]]; then
  capsule_root="$canonical_capsule"
elif [[ -x "$legacy_capsule/.limen-workstream/kickstart.sh" ]]; then
  capsule_root="$legacy_capsule"
else
  printf 'Omega successor capsule is unavailable at canonical and migration paths\n' >&2
  exit 1
fi
cd "$capsule_root" && bash .limen-workstream/kickstart.sh
```

Before launching, run `bash
docs/continuations/omega-substrate-convergence-next/switch-predicate.sh`.
Missing, expired, or contradictory capsule state fails closed.
