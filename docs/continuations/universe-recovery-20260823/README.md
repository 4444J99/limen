# Universe Recovery Continuation Capsule

This capsule owns the protective control-plane tranche of the 2026-08-23 universe recovery
program. It is deliberately nonterminal: no remote/local reaping, bulk PR closure, deployment,
activation, merge, or cleanup is authorized by this branch.

## Exact lane

- Branch: `recovery/universe-20260823`
- Base: `origin/main@f034e3e659c8c8c3b9469b7b66e32c2bc03fdb64`
- Human-protected Codex session: `01a02f60-498f-7732-a532-853019d6a146`
- TABVLARIVS root: `run-758d8e6df21df2184a68bf9757128219`
- Root lease generation: `1009`
- Writer scope: this isolated Limen worktree only

`conduct-root-packet.json` is the redacted tracked projection of the broker-owned packet; the
canonical packet remains in TABVLARIVS. Child read-only packets contain no private coordinates.

## Freeze

The legacy remote reaper is dark even when invoked with `--apply`. Its dry-run remains available
for observation only. New deletion requires, in order, a stdout-only plan, independent live
verification, a short-lived signed repository-qualified capability, exact-tip server CAS through
the sole effector, and post-effect absence verification. Archive4T and T7Recovery were not mounted
at launch, so source deletion and original-source cleanup remain prohibited.

## One launch command

```bash
python3 scripts/universe-recovery.py --check --manifest docs/continuations/universe-recovery-20260823/manifest.json
```

The expected launch result is nonzero until the listed source, review, and census debt has durable
terminal receipts. Even a clean manifest remains nonterminal until a separately persisted
`stable-observation.json` from an earlier exhaustive census has the same stable digest and predates
the current manifest. The checker is read-only and writes no repairs, observations, or effects.

## Next bounded wave

1. Land this protective PR through the repository merge rail; do not administer or force it.
2. Re-run the exact GitHub census and replace the launch-only denominator with exhaustive current
   repository, ref, PR, review, check, local-ref, worktree, stash, and source-instance receipts.
3. Mount and identity-verify both custody volumes before any source cleanup.
4. Process the first repository dependency chain from the program, at most four repositories and
   eight PRs per packet, with one writer and one merge effect per repository.

The source projection is [source-projection.json](source-projection.json). Read-only audit findings
are under [explorations](explorations/). The aggregate manifest is [manifest.json](manifest.json).
