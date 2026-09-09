# Limen — Evidence Appendix

**Observation date:** 2026-09-08.
**Source review date:** 2026-09-09. The review checks what each source supports; it does not rerun historical executions.
**Source baseline:** [26b82ebc65bc](https://github.com/4444J99/limen/commit/26b82ebc65bc2057b39dcef1499edc78308c0489).
Repository identity: 1255213941. Historical owner coordinates are evidence, not distinct repositories.

| ID | Material assertion supported | Source | Evidence boundary |
|---|---|---|---|
| E01 | The documented protocol separates direct human work from broker-leased autonomous work | [Agent protocol](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/AGENTS.md) | A protocol is not proof of universal compliance |
| E02 | The source has a configured broker client and fails when the required connection is unavailable | [Conduct client](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/cli/src/limen/conduct/client.py) | Does not prove any live broker is healthy or reachable |
| E03 | Scoped verification selects source-related checks and separates execution tiers | [Verification runner](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/scripts/verify.py) | Selection correctness and actual exit evidence must still be checked |
| E04 | Heavy-work admission can deny a run | [Host admission](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/cli/src/limen/host_admission.py) | A denial is not a passing test, and the guard does not prove software quality |
| E05 | Limen declares a single-owner exact-head PR integration policy | [Integration doctrine](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/docs/architecture/concurrent-integration.md), [estate registry](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/institutio/github/estate.yaml) | Current policy must not be projected backward as historical compliance |
| E06 | The September program audit distinguished structural, issue-state and stored-receipt coverage | [Snapshot observed at 2026-09-08T15:43:16Z](https://github.com/4444J99/limen/blob/1b8b5f44096d69f562df7e7c893992cad8bf6507/docs/positioning/program/recalibration/2026-09-08-snapshot.json), [recalibration PR](https://github.com/4444J99/limen/pull/2565) | 35/111 is the recorded stored-receipt coverage, not a fresh rerun, live product or commercial completion |
| E07 | Invalid completion evidence required quarantine | [Recovery PR](https://github.com/4444J99/limen/pull/2481), [P03 invalidation](https://github.com/4444J99/limen/issues/2181#issuecomment-5303837398), [P04 invalidation](https://github.com/4444J99/limen/issues/2189#issuecomment-5303837581) | Preserved invalid comments never become valid through repetition |
| E08 | R00's September 8 reports distinguish missing broker configuration, initial admission denial, later admitted execution, failed tests and a partial environment repair | [Broker/admission resumption at source 20ef4a8313d9](https://github.com/4444J99/limen/pull/2566#issuecomment-5590279757), [later execution checkpoint for correction 81d57e6f71bd](https://github.com/4444J99/limen/pull/2566#issuecomment-5591987771) | The dated executor checkpoint reports 6,720 CLI passes / 126 failures / 16 skips, 48 API passes, then 114 passes resolving 33 failures; 93 earlier failures remain unverified there. This is reported execution evidence, not an independent rerun or a claim about later runtime health |
| E09 | The existing contract supplies the authorship disclosure and proposes an Agentic Delivery Audit with bounded read access and explicit exclusions | [Commercial contract](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/docs/positioning/commercial-contract.md), [owning YAML](https://github.com/4444J99/limen/blob/26b82ebc65bc2057b39dcef1499edc78308c0489/institutio/positioning/commercial-contract.yaml) | Policy wording is not a forensic authorship audit. An offer definition is not evidence of a sale, consent to publish, a signed mandate or a promised business result |

## Claim coverage and publication boundary

E01–E05 support the mechanism descriptions and the intended tradeoffs in the report and summary.
They establish source behavior and documented policy, not universal enforcement or measured
benefits. E06 supports the historical task/receipt counts. E07 supports the explicit receipt-failure
history. E08 supports the dated runtime and verification chronology. E09 supports the unchanged
authorship wording and proposed service scope. The builder-scope discussion is an interpretation
of those mechanisms, not evidence of an employment title, executive mandate or customer result.

The controlled demonstration is a proposed procedure and has no claimed execution result. The
limitations deliberately withhold reliability, adoption, cost, revenue, independent replication
and outcome guarantees. These withheld claims do not become positive claims through this review.

The independent factual/publication verdict belongs to
[P05-W01](https://github.com/4444J99/limen/issues/2198). A publishable source package still requires
its canonical acceptance evidence; external distribution requires its own authority and target.

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
