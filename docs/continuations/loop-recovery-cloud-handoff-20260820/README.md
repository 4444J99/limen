# Loop recovery cloud handoff

This continuation capsule preserves the broker-safe Jules handoff for the
Limen loop-recovery repair. It does not contain credentials, corpus bodies,
private paths, or task-board state.

Exact bases:

- initial `organvm/limen` `main`: `b302ba97e6092e62b40aab9eff923e1a91c90c30`
- Limen continuation `main`: `5ea7a6a52efe11b3a8c83a7bfa67c71a86ea7f3c`
- `organvm/domus-genoma` `master`: `a8e0c7d434968d289b5da2e79c01e0692a3ec2b5`

The additive principal registry bootstrap and exact-SHA Worker deployment
succeeded. Root run `run-3e1ae37905ba1c5ee6dad0a9bd38409a` reserved and
launched both original leaves. Domus session `15303174208601107748` completed
with a pullable receipt. Limen session `1893712404416464604` stopped at
`awaiting_user_feedback`; Jules CLI v0.1.42 can pull that partial result but
cannot answer feedback, so it is not a closeable implementation receipt.

The bounded CLI-native recovery is the single-leaf continuation manifest. Its
prompt explicitly pre-approves the plan and directs Jules not to pause for
feedback. Plan it, then launch it exactly once through the broker:

```bash
PYTHONPATH=cli/src python3 -m limen.cli fanout plan --manifest docs/continuations/loop-recovery-cloud-handoff-20260820/fanout-manifest-limen-continuation.json
PYTHONPATH=cli/src python3 -m limen.cli fanout start --manifest docs/continuations/loop-recovery-cloud-handoff-20260820/fanout-manifest-limen-continuation.json --remote-first --local-max 0
```

Then use the returned root run ID with `limen fanout status ROOT_RUN --json`
and `limen conduct graph ROOT_RUN`. The laptop is safe to close only after both
leaf runs have keeper-bound Jules session URLs and pullable continuation
receipts naming `python3 scripts/jules-land.py --apply --recover` as the next
action.
