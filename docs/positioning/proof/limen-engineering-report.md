# Limen — Engineering Report

**Status:** source-backed case study draft; not a completed P05-W01 acceptance or a publication approval.
**Observation date:** 2026-09-08.
**Authorship:** Architected and directed by one person through a governed, multi-agent production system.

## The expensive problem

When several agents contribute to a delivery workflow, a sponsor needs to distinguish a plan, a
produced artifact, a passing test, an integrated change and a useful external outcome. Treating them
as interchangeable can cause repeated work, unjustified completion claims and unclear ownership.

This report examines Limen's approach to that problem in the owner's environment. It does not
assert that other frameworks lack controls, or that enterprise demand for this solution has already
been established.

## What was built

Limen contains a shared work-packet and receipt protocol, task projections, verification selection,
host-work admission and repository integration rules. Its documented broker is the authority for
autonomous leases and task transitions. Direct human sessions have separately scoped authority;
they are not evidence that an autonomous broker was available. See evidence E01 and E02.

The verification runner selects implicated checks and preserves a distinction between lightweight
checks and host-admitted heavy work. A denied heavy run is unverified, even if the preceding checks
passed. This distinction is a design and implementation fact, not a guarantee about every past
execution. See E03 and E04.

Repository integration is explicitly qualified by the registry. Limen's current single-owner
configuration uses exact-head local verification and a PR merge; other declared configurations may
use a queue. A moving default branch is not by itself a reason to restart every successful check.
These are current operating rules, not proof that every historical merge obeyed them. See E05.

## Decisions and tradeoffs

| Decision | Benefit sought | Cost or limit |
|---|---|---|
| Distinct work, receipt and aggregate completion evidence | Inspectable claims about what actually happened | Receipt validation can still be incomplete or wrong |
| Isolated writable lanes | Fewer concurrent file/ref collisions | Checkouts and custody require explicit lifecycle ownership |
| Exact-tree, scoped verification | Test evidence tied to a known implementation; less unrelated rerunning | Coverage depends on the correctness of gate selection |
| Separate leaf admission and aggregate proof | Useful independent work can progress without declaring the whole program complete | Each prerequisite still needs valid evidence; aggregate debt remains |
| Recorded external and human gates | No invented approval, participant response or commercial outcome | Some completion conditions require people and elapsed observation |
| Native provider identity and bounded work packets | Handoffs need not inherit a conversation or impersonate another provider | Availability, authentication and budget can still block autonomous execution |

The separate-admission change is an observed correction under
[R00 / PR #2566](https://github.com/4444J99/limen/pull/2566), not a claim that it was already on the
accepted baseline when the September observation was taken.

## What the observations show

1. **A complete task graph exists.** The September structural check passed for 111 work packets,
   15 phases, 13 chunks and 127 mapped objects. This proves structural coverage, not delivery. E06.
2. **Issue closure is insufficient evidence.** The same observation found 36 closed leaf issues,
   but only 35 passed stored-receipt validation. P05-W01 had no marked receipt; three phase receipts
   failed current parity. This report does not count their apparent closure as completed proof. E06.
3. **The system has required genuine correction.** The recovery PR quarantined forged receipts.
   Historical P03/P04 closure documents were subsequently labelled invalid evidence. The invalid
   records are retained for custody, not rehabilitated by a new narrative. E07.
4. **Runtime access is a separate fact.** The current execution session's CLI and connected broker
   capability reads reported that the broker was unconfigured. That does not establish the health
   of every deployment; it prevents a claim of autonomous broker operation from this session. E08.
5. **Verification can be partial.** R00's 57 focused tests and 14 lightweight scoped gates passed,
   and its live readiness query returned eight preparation rows. The complete scoped command
   nevertheless exited 75 because the host denied its heavy tail. These findings are attached to
   the unmerged repair, not presented as a fully admitted release. E08.

## A bounded demonstration

Choose one request and one repository. Follow its declared scope through implementation, an exact
source tree, the owning predicate, the PR/default-branch result and the next owner. Introduce a
controlled negative case, such as an invalid prerequisite receipt, and verify that it cannot admit
dependent work. Then verify that unrelated eligible work is still visible, while aggregate proof
continues to reject incomplete evidence.

Use synthetic requests and public-safe artifacts. Do not supply production credentials, customer
records or a fabricated user approval to make the demonstration succeed. This is a proposed
demonstration procedure; a completed public demonstration requires its own recorded execution.

## What this supports about the builder

The inspectable contribution is systems design across authority, verification, integration and
handoff boundaries, with an ability to diagnose and correct failures in those boundaries. A hiring
or buying decision should examine the linked implementation and discuss a concrete operating
problem. Repository volume alone does not establish quality, business value or executive scope.

The next commercial test is deliberately limited: can an evidence-backed audit help a named sponsor
make a better decision about one agent-assisted delivery initiative? Client outcomes, prices and
the expected economic benefit are not asserted here.

## Limits and review status

No controlled comparison, measured cost saving, enterprise reliability figure, customer adoption
claim or independent replication is established by these sources. The observations include failures
and unverified work. Current-source evidence can become stale when code, contracts or deployments
change.

The report is ready for a bounded independent factual/publication review. P05-W01 remains
unaccepted until that review, the claim-to-source audit and the required durable completion receipt
exist. A document merge alone cannot satisfy that condition.

- [Evidence appendix](limen-evidence-appendix.md)
- [Limitations and withheld claims](limen-limitations.md)
- [Bounded commercial contract](../commercial-contract.md)
