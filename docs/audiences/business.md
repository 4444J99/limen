# Limen for operational and business readers

> A governance layer for organizations using several AI coding agents across active software work.

[Project home](../../README.md) · [Technical edition](technical.md) ·
[Evidence and limitations](../positioning/evidence/limen.md)

## The operational problem

Adding more AI coding tools does not automatically create more reliable delivery. The operating
cost moves into coordination:

- the same issue is assigned twice;
- concurrent sessions edit overlapping branches or paths;
- provider usage is spent without a shared allocation model;
- a failed or abandoned session leaves no durable owner;
- status is distributed across chats, pull requests, vendor dashboards, and local machines;
- “done” means something different to each executor;
- public or client visibility risks exposing private task detail.

Limen addresses that coordination layer. It binds assignment, authority, resource reservation,
budget, verification, failure state, and receipts into one lifecycle.

## Who experiences the problem?

The strongest current fit is an engineering or platform operator coordinating multiple AI-agent
lanes across several repositories. The owner needs to preserve native provider identity while
preventing any one agent or vendor from becoming the canonical record keeper.

Other organizational applications are **proposed**, not deployed evidence:

- an internal AI engineering platform managing several agent vendors;
- a software consultancy separating operator, client, and public delivery views;
- a product team governing autonomous maintenance and repository work;
- a research engineering group that needs reproducible execution receipts.

No industry-specific customer deployment is claimed in this edition.

## Current workaround versus Limen

| Common workaround | Limen's implemented approach |
|---|---|
| A shared spreadsheet or issue list | Keeper-owned lifecycle with a read-only local projection |
| Each vendor reports its own status | Native identity preserved inside one packet/lease/receipt protocol |
| “First agent to push wins” | Exclusive resource claims and exact-head fencing |
| Informal token limits | Packet-level spend, retry, deadline, depth, and fanout bounds |
| Manual review of chat claims | Executable predicate evidence and typed terminal receipts |
| One dashboard for every audience | Owner, QA, client, and public personas with sanctioned disclosures |
| Restart everything after a conductor disappears | Children persist; adoption requires proved absence and authorization |

## How the workflow changes

1. The operator registers the actual agent sessions and capabilities available now.
2. Work enters as a bounded packet with a repository/path scope, authority envelope, resource
   claims, expected predicate, receipt target, and cost constraints.
3. The deterministic keeper selects an eligible executor and leases the relevant resource.
4. The native agent performs the work without losing its provider identity.
5. The result returns with exact-head, path, check, review, spend, and outcome evidence.
6. The keeper advances, blocks, retries, or closes the lifecycle according to declared rules.
7. Different readers receive owner, client, QA, or public projections rather than the same raw
   board.

Limen does not replace the team's repositories, tests, CI provider, coding agents, or human product
judgment. It connects their authority and evidence boundaries.

## Inputs and outputs

| Inputs | Outputs |
|---|---|
| Work intent and acceptance predicate | Versioned work packet and graph identity |
| Repositories and allowed path prefixes | Normalized resource claims |
| Available agent capabilities and quota | Selected native executor and lease |
| Spend, retry, deadline, and delegation limits | Enforced execution envelope |
| Repository heads and generation state | Fencing and conflict decisions |
| Test, review, and change evidence | Typed terminal receipt |
| Private operational state | Redacted client/public status contracts |

## Integration requirements

A real installation needs:

- an authenticated conduct endpoint and principal registry;
- native agent sessions or executor services that can claim and report work;
- repository access appropriate to each packet's authority;
- a credential wall outside committed source;
- project-specific executable predicates;
- a clear policy for external effects and human approval;
- an operator responsible for incident response, upgrades, and evidence review;
- a deployment decision for the API/dashboard adapters appropriate to the organization.

The public repository includes CLI, MCP, FastAPI, Next.js, Cloudflare Worker, and workflow adapters.
The shortest production path depends on the environment. Their presence does not mean a prospective
user can adopt the system without integration work.

## Deployment status

| Layer | Status | What the evidence supports |
|---|---|---|
| Core conduct contracts and Python broker | Implemented and tested | Versioned models, broker logic, resource rules, and focused protocol tests |
| Cloudflare Worker keeper | Implemented; a runtime health endpoint is deployed | Current reachability and declared private Durable Object storage at the observation time |
| Public dashboard/status | Deployed | Public aggregate surface; not a view of protected operational details |
| Owner/QA/client personas | Implemented and tested | Local/runtime contract behavior; protected live views require credentials |
| Owner-environment operation | Verified within the project's public evidence policy | Internal use, not customer adoption |
| External customer deployment | Not established | No public customer, revenue, retention, or outcome receipt |
| Industry-specific solution | Proposed | Requires domain mapping, buyer evidence, security review, and a bounded pilot |

## Risks and constraints

- **Integration risk:** agent vendors expose different execution and authentication surfaces.
- **Operational risk:** the keeper becomes critical coordination infrastructure and needs monitoring,
  backup, and recovery procedures.
- **Predicate risk:** a technically green check can still encode the wrong definition of done.
- **Security risk:** repository, provider, and deployment credentials remain sensitive even when
  public status is redacted.
- **Change-management risk:** teams must accept keeper-owned state rather than ad hoc direct edits.
- **Evidence risk:** a public dashboard can be mistaken for customer or reliability proof unless
  claims remain bounded.
- **Licensing risk:** the public tree currently lacks a license file, so reuse rights are unresolved.

## What a responsible pilot would test

A proposed organizational pilot should remain bounded to a small repository cohort and answer:

1. Can the existing work taxonomy be expressed as Limen packets without losing essential context?
2. Do resource claims prevent a measured class of duplicate or conflicting work?
3. Can each participating provider preserve native identity and return the required receipt?
4. Are spend and retry limits enforced under failure?
5. Can the team reproduce completion predicates independently of the agent's prose report?
6. Do owner, client, and public views disclose exactly what policy permits?
7. What operator labor remains after integration?

Until such a pilot produces receipts, savings, throughput, reliability, and adoption are hypotheses.

## Evaluation and next action

Start with the [technical architecture](technical.md), then inspect the
[evidence record](../positioning/evidence/limen.md). A deployment discussion should name the exact
repository cohort, agent lanes, credential boundary, predicate set, disclosure personas, and
success measures before estimating value.

The canonical status and limitations are in [`project-record.yml`](../../project-record.yml).
