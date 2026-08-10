---
type: prompt-relay-envelope
version: 1.0
date: YYYY-MM-DD
from: agent + native session identifier
to: next healthy session in this scope
scope: /absolute/path/to/worktree
phase: FRAME | SHAPE | BUILD | PROVE | DONE
compression_level: medium
---

# Relay — PSP-WORK-ID: one-line subject

## Routing

- Program work ID:
- GitHub issue:
- Target repository:
- Branch/worktree:
- Conduct root/run/lease receipt, if any:

## Verified current state

| Item | Live state |
|---|---|
| Exact local head | |
| Exact remote branch head | |
| Exact target repository heads | single declared target, or multi-repository resolved set, with exact predicate-tested heads |
| Working tree | clean / named changes |
| Acceptance condition | unmet / partial / met with named evidence |
| Task-specific predicate | not run / failing with exact cause / passing at exact head |
| Receipt verifier | no receipt / invalid with exact cause / passing with comment URL |
| Phase exit gate | not applicable / skeleton command, underlying predicate, binding digests, verifier result, and receipt URL |
| Omega observation | not applicable / emitting `--omega-pass` command, pass file, `observed_at`, snapshot, and `state_digest` |
| External effects | none / precisely named |

## Completed work

- [ ]

## Decisions and rationale

| Decision | Evidence and rationale |
|---|---|
| | |

## Next actions

1.
2.

If the next action is receipt verification, name the already-passing underlying predicate; never
record `--verify-work` as its own evidence. If it is phase closure, name the executable phase
exit-gate receipt still required and whether
`python3 scripts/positioning-program.py --phase-receipt-template <PHASE-ID>` has generated the
current `observed_heads`, `child_receipts_sha256`, `remote_state_sha256`, and `parity_sha256`
bindings. If it is Omega, identify which distinct observation comes next and do not reuse parity,
closure, or digest facts across different remote snapshots. Passes `1` and `2` come from separate
`--omega --omega-pass 1` and `--omega --omega-pass 2` invocations, must have different RFC3339
`observed_at` values while attesting the same `state_digest`, and are consumed by
`--omega --require-two-pass`.

## Risks and prohibitions

- Human gates still unpulled:
- Sensitive/private material boundaries:
- Files or sibling work that must not be touched:
- Rollback route:

## References

- Program manifest: `institutio/positioning/program.yaml`
- GitHub map: `institutio/positioning/github-map.json`
- Pull request / receipt:

The fresh-agent injection phrase is:

```text
Continue from relay at <absolute-pointer-path>. mid-task — see Next Actions for current step.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, or permission.
