# Limen — Evidence Appendix

**Observation date:** 2026-09-08.
**Source baseline:** [26b82ebc65bc](https://github.com/4444J99/limen/commit/26b82ebc65bc2057b39dcef1499edc78308c0489).
Repository identity: 1255213941. Historical owner coordinates are evidence, not distinct repositories.

| ID | Material assertion supported | Source | Evidence boundary |
|---|---|---|---|
| E01 | The documented protocol separates direct human work from broker-leased autonomous work | [Agent protocol](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/AGENTS.md) | A protocol is not proof of universal compliance |
| E02 | The source has a configured broker client and fails when the required connection is unavailable | [Conduct client](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/cli/src/limen/conduct/client.py) | Does not prove any live broker is healthy or reachable |
| E03 | Scoped verification selects source-related checks and separates execution tiers | [Verification runner](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/scripts/verify.py) | Selection correctness and actual exit evidence must still be checked |
| E04 | Heavy-work admission can deny a run | [Host admission](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/cli/src/limen/host_admission.py) | A denial is not a passing test, and the guard does not prove software quality |
| E05 | Limen declares a single-owner exact-head PR integration policy | [Integration doctrine](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/docs/architecture/concurrent-integration.md), [estate registry](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/institutio/github/estate.yaml) | Current policy must not be projected backward as historical compliance |
| E06 | The September program audit distinguished structural, issue-state and stored-receipt coverage | [Dated snapshot](../program/recalibration/2026-09-08-snapshot.json), [recalibration PR](https://github.com/4444J99/limen/pull/2565) | 35/111 is stored-receipt coverage, not live product or commercial completion |
| E07 | Invalid completion evidence required quarantine | [Recovery PR](https://github.com/4444J99/limen/pull/2481), [P03 invalidation](https://github.com/4444J99/limen/issues/2181#issuecomment-5303837398), [P04 invalidation](https://github.com/4444J99/limen/issues/2189#issuecomment-5303837581) | Preserved invalid comments never become valid through repetition |
| E08 | The R00 repair produced bounded positive evidence and a separately reported host-admission failure | [Exact repair and verification report](https://github.com/4444J99/limen/pull/2566) | 57 focused tests and 14 cheap gates do not substitute for its unexecuted heavy tail; session connection failure is not estate-wide outage proof |

## Reproduction and interpretation

Inspect the exact source version before repeating a command. The structural program check is
`python3 scripts/positioning-program.py --check`. The ready-work query is
`python3 scripts/positioning-program.py --ready --json`; its output depends on current remote issues,
receipts and the version of the admission code. A later output is a new observation, not evidence
that the dated September snapshot was wrong.

Run the relevant source-owned tests or scoped gate only in an isolated, appropriately admitted
environment. Record the command's own exit code and distinguish selected, executed, skipped,
denied and passed checks. The exact reproduction result belongs to its tested tree.

No private customer content, production credentials, cost estimates or third-party endorsement is
needed to inspect these public sources. None is supplied by this appendix.
