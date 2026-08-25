# Handoff predicate

The implementation tranche is ready for exact-head review only when its scoped verification receipt
is green and the public preflight receipt matches its private preflight manifest digest. The final
transfer manifest is privately recaptured only after every ref and review mutation stops; its
sidecar digest and restored bundle bind the transfer without creating a self-referential PR-head
change. The recovery program itself remains nonterminal until all of these externally observed
predicates hold:

1. The old and new coordinates both resolve repository ID `1255213941`, and anonymous reads of the
   old coordinate redirect to the new coordinate.
2. The post-transfer manifest matches every transfer-stable pre-transfer invariant; removed issue
   types or non-owner assignments are restored from private custody before acceptance.
3. The protected-lane postflight is attributable and proves no transfer actor changed Agy or
   OpenCode state.
4. Manual CI on the transferred default SHA has a nonzero runner ID and at least one executed step.
5. PR #2543, then PR #2542, are exact-head green and have zero unresolved current or outdated review
   threads before the system lane uses `scripts/await-pr.sh <number> --merge`.
6. Notification artifacts land, the exact merged artifacts are installed by the system lane, and
   one unique local delivery plus three successful fires at least 300 seconds apart prove zero
   descendants and no legacy watchdog residue.
7. Effectful workflows are re-enabled one at a time only after their scoped secret, App,
   environment, and predicate checks pass. The PyPI workflow also waits for the trusted-publisher
   owner update. The paid Warp/Oz workflow remains disabled under the zero-spend constraint.
8. Two unchanged exhaustive recovery censuses have the same digest and no effects, followed by two
   passes of the four final predicates named in the recovery plan.

The former human-owned transfer gate is explicitly discharged in
`L-LIMEN-PERSONAL-CONTROL-PLANE-TRANSFER` in `his-hand-levers.json`. This continuation owns the
technical transfer and exact postflight until their predicates pass.
