# Limen for a general reader

> Limen is a traffic controller and record keeper for teams of AI coding agents.

[Project home](../../README.md) · [See the public status](https://limen-dashboard.pages.dev/public) ·
[Inspect the evidence](../positioning/evidence/limen.md)

## What is this?

Limen is a software system for coordinating other software agents. Those agents may work through
different products, on different repositories, and at different times. Limen gives their work a
shared set of rules:

- every task has an identified owner;
- permissions and spending are bounded before execution;
- two agents cannot silently claim the same exclusive resource;
- a task is not complete merely because an agent says it is;
- the result returns with a receipt that can be inspected;
- public status can be separated from private operational detail.

A **repository** is the organized collection of source code, tests, documentation, and revision
history used to build a software project. This repository contains Limen itself: the coordinator,
its command-line interface, its web surfaces, its protocols, and the tests used to check them.

## Why does it exist?

AI agents can produce work quickly, but speed creates a coordination problem. Several agents can
edit the same branch, repeat the same task, spend from an unstated budget, or report success against
different definitions of “done.” A chat transcript may describe activity without proving that a
change reached the intended repository or passed the relevant test.

Limen treats those failures as a governance problem rather than a prompting problem. It asks:

1. Who is allowed to do this work?
2. What exactly may they change?
3. Which resource is reserved while they work?
4. How much time or provider capacity may they consume?
5. What executable check defines completion?
6. What record survives after the session ends?

## What happens when someone uses it?

A person or authorized agent describes a bounded unit of work. Limen records that unit as a work
packet, checks that an eligible agent is available, and grants a time-limited lease. The executor
does the work under the packet's permission and spending limits. It then returns a receipt that
names the result, affected paths, checks, and outcome. The keeper accepts or rejects the lifecycle
transition according to the shared protocol.

The checked-in `tasks.yaml` file is a projection—a readable view—not a free-for-all document that
every agent rewrites. The deterministic keeper, called **TABVLARIVS** inside the project, owns
canonical task, lease, and budget transitions.

## A concrete example

Imagine that two AI coding sessions are ready to change the same branch.

Without coordination, both can begin, produce incompatible histories, and each report success.
With Limen, each proposed job declares its branch or path as a resource claim. The keeper grants
the exclusive writer lease to one eligible executor. The overlapping writer must wait or be routed
elsewhere. If the branch moves while the first executor is working, the old lease is fenced: its
late receipt remains evidence of an attempt but cannot silently update current state.

This behavior is implemented in the conduct broker and resource model and exercised by protocol
tests. The example demonstrates conflict control; it does not establish that every possible tool
or network failure has been eliminated.

## Why might this matter?

Limen makes delegated machine work more legible. A person evaluating the system can distinguish:

| Question | Limen's record |
|---|---|
| What was requested? | A bounded work packet |
| Who received authority? | A registered native agent identity and lease |
| What was reserved? | A task, branch, path, review, or external-effect resource claim |
| What was the limit? | Authority, spend, retry, deadline, depth, and fanout bounds |
| What happened? | A terminal receipt and lifecycle event |
| What counted as done? | The declared executable predicate and its evidence |

The system does not remove human responsibility. It makes the boundary between human direction,
machine execution, deterministic record keeping, and public disclosure easier to inspect.

## What currently exists?

The repository contains:

- a Python command-line package;
- a conductor protocol with versioned packet, lease, session, and receipt schemas;
- local development/test state adapters;
- an authenticated Cloudflare Worker keeper and private Durable Object implementation;
- FastAPI and web-dashboard adapters;
- owner, client, QA, and public persona surfaces;
- resource, budget, authorization, retry, and exact-head controls;
- focused tests and repository-level verification gates;
- a deployed public dashboard and runtime health endpoint.

The project status is **operational-internal**. The public evidence supports operation in the
owner's environment and a deployed public/runtime surface. It does not support claims of paying
customers, broad external adoption, comparative reliability, return on investment, or
zero-maintenance autonomy.

The source can be read publicly, but the verified repository tree has no license file. Public
availability must not be confused with an open-source permission grant until a license is
explicitly committed.

## Where should I go next?

- To understand the mechanisms, read the [technical edition](technical.md).
- To examine questions of authority, memory, and authorship, read the
  [humanities edition](humanities.md).
- To consider use in an engineering organization, read the [business edition](business.md).
- To assess Anthony's contribution and inspectable proof, read the
  [evaluator edition](evaluator.md).
- To check exact claims and limitations, use the [evidence packet](../positioning/evidence/limen.md)
  and canonical [`project-record.yml`](../../project-record.yml).
