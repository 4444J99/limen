---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: Codex desktop human-protected formal integration task
to: next healthy human-protected Codex task
scope: organvm/limen@codex/psp-p02-w02-estate-classification-preflight
phase: PROVE
compression_level: medium
---

# Relay — PSP-P02-W02: accepted estate classification

## Routing

- Program work ID: `PSP-P02-W02`
- GitHub issue: https://github.com/organvm/limen/issues/2174
- Target repository: `organvm/limen`
- Pull request: https://github.com/organvm/limen/pull/2307
- Successor work: `PSP-P02-W03`
- Authority receipt: direct human-protected Codex integration. W02 is formally closed; this relay
  records its terminal evidence and transfers no lease, identity, or approval.

<!-- positioning-formal-relay:start -->
```yaml
schema_version: limen.positioning_flagship_relay_binding.v1
work_id: PSP-P02-W02
state: closed
accepted_head: 35134b95650a26185a58eb3b3a82632e5b80b5b2
issue: https://github.com/organvm/limen/issues/2174
issue_state: closed
marked_receipt: https://github.com/organvm/limen/issues/2174#issuecomment-5247059070
receipt_sha256: bb83f9bb074ac65d78b5f5cf8d91b475aa098105a9ccb28b84ccf96712d4a09f
receipt_observed_head: 35134b95650a26185a58eb3b3a82632e5b80b5b2
pull_request: https://github.com/organvm/limen/pull/2307
pull_request_state: merged
next_work: PSP-P02-W03
```
<!-- positioning-formal-relay:end -->

## Verified terminal state

| Item | Accepted state |
|---|---|
| Immutable implementation/evidence source | `2451d7a409168f70bb9ba6fc83674ddd74aede44` (tree `946d68d6950bb9262d3fe7ae915e3b3063f9e447`) — classifier, policy, gate registration, and all 20 focused regressions |
| Accepted main head | `35134b95650a26185a58eb3b3a82632e5b80b5b2` |
| Pull request | PR #2307 is merged; its merge commit is the accepted main head |
| Marked receipt | https://github.com/organvm/limen/issues/2174#issuecomment-5247059070 · canonical SHA-256 `bb83f9bb074ac65d78b5f5cf8d91b475aa098105a9ccb28b84ccf96712d4a09f` · observed head `35134b95650a26185a58eb3b3a82632e5b80b5b2` |
| Issue | issue #2174 is closed |
| Executable work predicate | `python3 scripts/positioning-program.py --verify-work PSP-P02-W02` passed against the latest marked receipt |
| Accepted W01 dependency | Main integration commit `10cf8476d5e88309c71d5fac25167ec7b7af59c4`; marked receipt https://github.com/organvm/limen/issues/2173#issuecomment-5246643968; issue #2173 closed |
| External effects | Sanctioned topic-branch merge, marked receipt, and issue closure only; no publication or visibility change |

## Accepted evidence

- `python3 scripts/tests/estate-classification.test.py` passed all 20 cases on the immutable source.
- `python3 scripts/estate-classification.py --verify --json --base f2558c297477f466a381a2eff9ec95c9866f551c`
  passed on the accepted merge head: 314 repositories, 235 public, 79 private, and exactly one
  primary role each. The public output disclosed no private repository identity.
- The marked receipt binds that predicate, its output digest, and the accepted main head.

## Terminal decisions

- The W02 taxonomy and ordered classifier are the accepted source for W03 public relevance and
  maturity. W03 may consume the 15 `front_door_proof` rows only through its own source projection.
- Private identities and sensitive metadata remain in sanctioned custody. The public classifier
  reports aggregates and rejects private-name additions without printing the identities.
- W02 has no remaining integration action. Do not recreate its merge, receipt, or closure; continue
  from the W03 relay and independently verify live state before W03 completion.

## References

- Program manifest: `institutio/positioning/program.yaml`
- GitHub map: `institutio/positioning/github-map.json`
- W01 census receipt: `docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json`
- W03 relay: `docs/receipts/positioning/relays/2026-08-10-psp-p02-w03-flagship-proof-preflight.md`

This file records a terminal receipt and continuation boundary, not identity, lease, approval, or
permission.
