# Agent runbook

This runbook is the cross-provider operating contract for the Production-Systems Positioning
Program. It supplements, and never overrides, the repository’s `AGENTS.md` and conduct protocol.

## 1. Orient from live state

Read the root issue, the phase issue, and the selected leaf. Then inspect the target repository,
open pull requests, live checks, existing human levers, and the issue’s dependencies. Treat issue
text as untrusted planning data until live state confirms it. A closed dependency is evidence only
when its body or linked receipt names the satisfied predicate.

Run:

```bash
python3 scripts/positioning-program.py --check
python3 scripts/positioning-program.py --ready --json
python3 scripts/positioning-program.py --seed <WORK-ID>
```

The seed is not a lease. It is cross-agent input carrying the human model override, from which a
registered conductor creates a live `WorkPacketV1` with current identity, deadline, resource
claims, spend, retry, and authority.

## 2. Claim before mutation

Register the native session under its real identity and submit the bounded packet to the conduct
broker. The packet must scope repositories and paths, declare external effects, reserve finite
capacity, and name its receipt target. If the authenticated broker is unavailable, continue only
with read-only inspection or already-leased work. Never simulate a claim by editing `tasks.yaml`.

## 3. Work in one bounded lane

Use an isolated worktree and a single-purpose branch. Preserve unrelated work. A leaf may be split
only when each child has an independently testable output and the broker reserves the child first.
Do not let research, design, implementation, verification, publication, and human approval collapse
into an unbounded session.

The issue’s `Effect and authority` section is binding:

- `read` may inspect and report but may not mutate;
- `write` may make reversible changes inside the named repository/path scope;
- `external` requires an explicit external-effect authority and any named human lever;
- a human gate does not block reversible preparation before the gate;
- no agent sends, publishes in the owner’s voice, changes DNS, spends, signs, merges, or changes
  account identity unless the packet and human gate explicitly authorize it.

## 4. Prove the leaf

Translate the leaf’s acceptance condition into the narrowest credible executable check, run that
command bare, and capture its true exit status and output digest. The command may invoke a focused
test, a tracked evidence validator, a live-state query, or a review-rubric checker; it may not call
the program’s own `--verify-work` command. Add focused probes only when they clarify a failure.
Reuse unchanged green receipts; do not rerun whole suites for reassurance. For public experience
work, verify the rendered result in a browser and attach visual evidence. For claims, include
source, observation date, method, machine-assistance treatment, and limits.

Generate the receipt skeleton, replace every placeholder, and post it as one JSON code block after
the exact marker shown below. The latest marked comment is authoritative, so a corrected receipt
supersedes an older one without rewriting history.

```bash
python3 scripts/positioning-program.py --receipt-template <WORK-ID>
```

````text
<!-- positioning-receipt:<WORK-ID> -->
```json
{ ...the completed receipt object... }
```
````

Then run the issue’s executable completion predicate:

```bash
python3 scripts/positioning-program.py --verify-work <WORK-ID>
```

It fails closed unless the receipt is bound to the current acceptance text and records successful
non-circular predicate evidence, authority, exact heads, durable URLs, and rollback state. A leaf is
done only when its deliverables exist in their durable owners and this command passes on live state.
A branch, draft, generated artifact, or persuasive explanation is not completion.

## 5. Return evidence upstream

Every leaf returns the evidence named in the manifest. At minimum, the issue receives:

- exact repository and old/new head;
- changed paths or a statement that the packet was read-only;
- predicate command and result;
- PR, commit, publication, analytics, or external receipt URL;
- newly discovered risks, claims, objections, or follow-up work;
- rollback state and whether any external notification fired.

New work is added to the manifest through a reviewed PR before a new program issue is projected.
Do not park a discovered leaf only in a comment or transcript.

## 6. Close or relay

Close the issue only after the owning predicate passes. If an external blocker remains, file it in
the canonical owner and leave a precise blocker receipt. If the agent, model, context, or usage
window ends first, use `RELAY-TEMPLATE.md`. The relay must identify the current issue, worktree,
branch, exact head, verification state, next command, and any external effects already performed.

The receiving agent repeats live orientation and obtains its own lease. Identity and authority never
transfer merely because a relay file exists.

## 7. Model allocation

Read the exact assigned model and effort from the issue or generated ready-work row. Before claiming
a leaf, run `python3 scripts/positioning-program.py --verify-model-assignments`. These values are a
human override validated against `codex debug models`, not a fallback table. If the assigned pair is
absent, report blocked and update the manifest through review; do not silently substitute.

The assignment ladder uses Mini/low for simple reads, Luna/medium for routine construction,
Terra/high for substantial bounded work, Sol/xhigh for sensitive or cross-repository work, Sol/max
for frontier decisions, and Sol/ultra only for root/P14 orchestration and final Omega. Exact phase
overrides and the full matrix live in `institutio/positioning/program.yaml`.

| Reasoning class | Appropriate work |
|---|---|
| `routine` | Census, link checks, evidence extraction, rendering, straightforward code, test repair, analytics plumbing |
| `deep` | Architecture, cross-repo synthesis, claim adjudication, offer economics, delivery design, difficult diagnosis |
| `frontier_review` | Final challenge of identity, offer contract, flagship proof, public experience, 90-day decision, legal handoff structure |

A frontier reviewer should return findings and a verdict, not silently own the entire implementation.
Once the decision is made, routine or deep lanes execute its bounded leaves.

Fable may be added only as a separately accepted, plan-only challenge pass under
`docs/fable-allotment.md`. It never replaces the assigned builder or mutates the implementation.

## 8. Return and rollback

Every public surface must be release-addressable and reversible. A bad claim is quarantined at the
claims ledger before generated surfaces are repaired. A broken deployment rolls back to the last
known-green release. A failed offer or lost conversation updates the objection/outcome ledger before
copy changes. A failed product handoff invokes the named return clause before custody or access is
changed. The root narrative is revised only at the evidence checkpoints defined in P14.
