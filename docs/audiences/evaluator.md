# Limen for evaluators

> A bounded guide to what the project is, what Anthony James Padavano contributed, what can be
> inspected, and what the public record does not establish.

[Project home](../../README.md) · [Technical edition](technical.md) ·
[Evidence record](../positioning/evidence/limen.md)

## Evaluation summary

Limen is a substantial governance and orchestration system for coordinating AI-agent work across
repositories. It combines versioned conduct contracts, a deterministic lease keeper, native-agent
interfaces, budget and authority envelopes, resource-conflict rules, exact-head verification,
runtime adapters, persona-separated dashboards, and a large verification estate.

Its documented status is **operational-internal**. Public evidence supports implementation,
owner-environment operation, and deployed public/runtime surfaces. It does not establish customer
adoption, revenue, enterprise scale, comparative reliability, or zero-maintenance autonomy.

## Initial condition and design problem

The project addresses a recurring failure in multi-agent software delivery: task assignment,
provider capacity, repository authority, concurrent mutation, verification, and failure state are
distributed across separate tools. Under that condition, activity is easy to generate and difficult
to reconcile. A branch, chat transcript, or provider completion message can be mistaken for a
landed and verified result.

Limen's design response is a single governed lifecycle in which work is packetized, leased,
executed under bounded authority, checked against a predicate, and returned with a durable receipt.

## Anthony's role

The project's public authorship class is **agent-directed**.

Anthony James Padavano's recorded role is project architect and director of a governed multi-agent
implementation. The evidence-bounded contribution statement is:

- defined the system's ideal form and cross-provider operating problem;
- established the keeper/conductor/executor architecture;
- defined authority, evidence, human-gate, and completion doctrine;
- directed implementation and revision across multiple AI-agent lanes;
- set acceptance pressure and required executable verification;
- integrated the project into the wider ORGANVM repository-governance system;
- authored and curated conceptual, operational, and public-facing documentation.

This should not be paraphrased as “Anthony manually wrote every line.” Machine assistance is
central and disclosed through commit, review, protocol, and receipt surfaces. The repository also
uses external frameworks, services, and dependencies. A complete line-by-line authorship audit has
not been performed.

## What changed because of the work

The repository contains an implemented system in place of an informal multi-agent queue:

| Capability | Inspectable result |
|---|---|
| Shared work contract | Versioned session, packet, lease, attempt, receipt, and fanout schemas |
| Deterministic authority | Keeper role separate from model/conductor identity |
| Concurrent work control | Normalized exclusive/shared resource claims and exact-head fencing |
| Bounded delegation | Child authority, scope, spend, retry, deadline, depth, and fanout attenuation |
| Provider plurality | Native lane identities and adapter surfaces rather than one canonical model vendor |
| Evidence-bearing completion | Predicate/check data and changed-head/path information in receipts |
| Audience separation | Owner, QA, client, and public status contracts with persona sanctions |
| Repository governance | Scoped and whole-repository predicates driven by a gate registry |

This table describes implemented mechanisms, not outcome superiority.

## Where to inspect the work

### Architecture and protocol

- [`docs/architecture/peer-conductor-protocol.md`](../architecture/peer-conductor-protocol.md)
- [`cli/src/limen/conduct/models.py`](../../cli/src/limen/conduct/models.py)
- [`cli/src/limen/conduct/broker.py`](../../cli/src/limen/conduct/broker.py)
- [`cli/src/limen/conduct/resources.py`](../../cli/src/limen/conduct/resources.py)
- [`spec/contracts/conduct/`](../../spec/contracts/conduct/)

### Interfaces and deployment adapters

- [`cli/src/limen/conduct/cli.py`](../../cli/src/limen/conduct/cli.py)
- [`mcp/src/limen_mcp/server.py`](../../mcp/src/limen_mcp/server.py)
- [`web/worker/src/conduct/`](../../web/worker/src/conduct/)
- [`web/api/main.py`](../../web/api/main.py)
- [`web/app/app/`](../../web/app/app/)

### Tests and gates

- [`cli/tests/test_conduct_protocol.py`](../../cli/tests/test_conduct_protocol.py)
- [`cli/tests/test_conduct_roles.py`](../../cli/tests/test_conduct_roles.py)
- [`cli/tests/test_conduct_auth.py`](../../cli/tests/test_conduct_auth.py)
- [`web/api/tests/test_main.py`](../../web/api/tests/test_main.py)
- [`web/worker/test/`](../../web/worker/test/)
- [`institutio/governance/gates.yaml`](../../institutio/governance/gates.yaml)
- [`scripts/verify-scoped.sh`](../../scripts/verify-scoped.sh)

### Operating and public evidence

- [Public status](https://limen-dashboard.pages.dev/public-status.json)
- [Runtime health](https://limen-runtime.ivixivi.workers.dev/health)
- [Project evidence packet](../positioning/evidence/limen.md)
- [`project-record.yml`](../../project-record.yml)

## How strong is each evidence class?

| Evidence | What it can establish | What it cannot establish alone |
|---|---|---|
| Source and schemas | The mechanism exists in the inspected tree | The mechanism is correctly deployed or adopted |
| Focused tests | Declared behaviors reproduce in the test environment | Long-window production reliability |
| Repository gates/workflows | A named revision passed declared checks | Business value or absence of undiscovered defects |
| Public runtime endpoint | A deployed surface responded with a declared contract at an observation time | Private task truth, SLA, or customer usage |
| Git history | Revision scale, sequence, and recorded identities | Complete human/machine authorship attribution |
| Owner evidence packet | The project's bounded public claim and withdrawal rules | Independent third-party validation |

## Decisions that demonstrate judgment

- **Keeper separated from conductor.** A temporary agent role does not become the canonical state
  authority.
- **Projection separated from state.** `tasks.yaml` remains readable without permitting every
  session to rewrite truth.
- **Fail-closed canonical claims.** Broker unavailability blocks new authoritative work rather than
  inventing a local success path.
- **Native identity preserved.** Provider plurality is treated as a design requirement, not routed
  through a single model identity.
- **Late evidence retained but fenced.** Historical work is not erased, yet stale authority cannot
  update present state.
- **Human sessions protected.** Autonomous continuity has an explicit limit around direct human
  work.
- **Public disclosure redacted.** Operational proof is separated from protected task and client
  detail.

## Known incompleteness and claim boundaries

- Customer adoption, revenue, retention, and externally measured outcomes are not publicly
  established.
- Public status is a dated, redacted projection and may not reflect private operation in real time.
- A deployed runtime health response is not a reliability window or security certification.
- Provider integrations and lane declarations do not prove every provider is continuously available.
- No independent comparative benchmark establishes cost, throughput, or quality advantage.
- The repository has no license file at the verified tree, so open-source reuse rights are
  unresolved despite public source visibility.
- The repository contains broad operational scope and accumulated technical debt; evaluation should
  use scoped predicates rather than assuming every subsystem shares the same maturity.

## Suggested reproduction path

For a bounded technical evaluation:

1. inspect the packet, lease, receipt, and authority models;
2. run the focused conduct protocol and role suites listed in the
   [technical edition](technical.md#verification-map);
3. inspect the Worker keeper and persona tests;
4. compare the README claim to the evidence packet and canonical project record;
5. treat live endpoints as fresh observations only when rechecked;
6. separate implementation evidence from adoption or outcome inference.

That sequence evaluates what Limen actually demonstrates without requiring the evaluator to accept
its internal terminology or commercial positioning first.
