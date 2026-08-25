# Personal Control Plane Transfer Capsule

This capsule governs the durable move of repository ID `1255213941` from `organvm/limen` to
`4444J99/limen`. Anthony explicitly delegated the technical transfer, merge, activation,
deployment, installation, and restart effects to the system lane on 2026-08-25. It does not
authorize a mirror, duplicate registry, budget change, paid runner, overage, or predicate bypass.

The content-hashed pre-transfer preflight snapshot is summarized in
[public-capture-receipt.json](public-capture-receipt.json). It proves the capture machinery and its
private counterpart includes the
complete Git bundle and restore proof, every ref and open-PR head, review threads, releases, issue
denominator and assignments, labels, rulesets, branch protection, workflow and Actions settings,
environment/secret/variable names, hooks, keys, App census result, and protected-lane snapshots.
Private source, credentials, process commands, custody metadata, and protected-lane digests are not
published.

Because landing this tracked receipt changes an open-PR head, it is deliberately not the final
transfer manifest. After every branch, PR, or review mutation has stopped, the active system lane
creates one new private bundle and manifest and performs no further ref or review change before the
transfer. The final private sidecar digest and bundle restore proof—not this preflight
snapshot—bind the transfer.

## One launch command

Set `LIMEN_PRIVATE_TRANSFER_MANIFEST` to the privately held frozen manifest, then run:

```bash
python3 scripts/repository-transfer-workflows.py --manifest "${LIMEN_PRIVATE_TRANSFER_MANIFEST:?set the private manifest path}" --repo organvm/limen --check
```

It must report all 16 transfer-sensitive workflows frozen immediately before the system transfers
the repository. If GitHub refuses `4444J99/limen` before mutation, use only
`4444J99/limen-control`; do not create a mirror. That fallback remains noncanonical until a
follow-up identity/defaults commit records the same numeric repository at the fallback coordinate.

## Delegated execution rail

1. After all branch, PR, and review mutations stop, create a fresh private bundle and manifest.
   Validate its content digest and restore proof; confirm the live repository is still public, ID
   `1255213941`, at the captured default SHA, and the freeze command above passes. Perform no
   further ref or review mutation before transfer.

   ```bash
   python3 scripts/repository-transfer-manifest.py --repo organvm/limen --output "${LIMEN_FINAL_TRANSFER_MANIFEST:?set final private manifest}" --bundle "${LIMEN_FINAL_TRANSFER_BUNDLE:?set final private bundle}" --protected-checkout "agy=${LIMEN_AGY_CHECKOUT:?set Agy checkout}" --protected-path "opencode=${LIMEN_OPENCODE_PATH:?set OpenCode path}"
   ```
2. Perform the one GitHub repository-transfer effect through the authenticated technical lane.
3. Immediately capture the new coordinate with `scripts/repository-transfer-manifest.py`, verify it
   against the frozen manifest, re-query App access, and verify both authenticated coordinates plus
   the anonymous redirect. Do not stop or modify OpenCode to manufacture an equal snapshot.
4. Re-enable only `.github/workflows/ci.yml` with one private, content-hashed evidence receipt
   covering the seven recovery-CI predicates required by `scripts/repository-transfer-workflows.py`.
   Restore exactly that one workflow in the invocation, then dispatch it manually on
   the transferred default SHA. A zero-step or missing-runner result is terminal evidence, not a
   retry signal.
5. Continue through [runtime.md](runtime.md) and [closeout.md](closeout.md). The system lane merges via
   `scripts/await-pr.sh`, activates the heartbeat plan, installs merged artifacts, deploys, and
   re-enables effectful workflows only as their exact predicates pass.
