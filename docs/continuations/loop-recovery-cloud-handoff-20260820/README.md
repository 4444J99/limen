# Loop recovery cloud handoff

This continuation capsule preserves the broker-safe, two-leaf Jules handoff for
the Limen loop-recovery repair. It does not contain credentials, corpus bodies,
private paths, or task-board state.

Exact bases:

- `organvm/limen` `main`: `b302ba97e6092e62b40aab9eff923e1a91c90c30`
- `organvm/domus-genoma` `master`: `a8e0c7d434968d289b5da2e79c01e0692a3ec2b5`

Current blocker: the live broker returns HTTP 401 for the registered Jules
principal bearer before an executor session or lease can be created. The
credential owner is the Limen credential wall, issue #320. Do not substitute
the Codex bearer, launch Jules manually, edit `tasks.yaml`, or use local test
state.

After the credential owner additively republishes the principal registry and a
read-only Jules-principal capability probe succeeds, launch exactly once:

```bash
PYTHONPATH=cli/src python3 -m limen.cli fanout start --manifest docs/continuations/loop-recovery-cloud-handoff-20260820/fanout-manifest.json --remote-first --local-max 0
```

Then use the returned root run ID with `limen fanout status ROOT_RUN --json`
and `limen conduct graph ROOT_RUN`. The laptop is safe to close only after both
leaf runs have keeper-bound Jules session URLs and pullable continuation
receipts naming `python3 scripts/jules-land.py --apply --recover` as the next
action.
