# Product and authority boundary

## Product definition

The proposed program contains two connected products and preserves the existing transactional
estate:

1. **BBNC Stewardship** — a staff-only authority-to-outcome platform governed exclusively by
   BBNC-approved authority instruments, delegations, policies, and decisions.
2. **BBNC.net** — a rebuilt anonymous public site that ingests only signed, allow-listed public
   publication packages from Stewardship.
3. **Existing systems of record** — myBBNC plus existing voting, employment, application, policy,
   compliance, and subsidiary systems continue to own sensitive transactions and records.

Padavano supplies engineering under contract. Its delivery methods govern Padavano's conduct only;
they grant no authority inside BBNC.

## Governing layers

| Layer | Purpose | Owner | Allowed data in v1 |
|---|---|---|---|
| Root authority | Policies, resolutions, delegations, controls | BBNC | Only material BBNC authorizes for the platform |
| Stewardship | Initiatives, decisions, evidence, releases, outcomes | BBNC staff | Public and BBNC-approved Internal |
| Public projection | Anonymous BBNC.net experience | BBNC Communications | Public only |
| Transaction systems | Shareholder, employment, voting, applications | Existing system owners | Sensitive data remains there |
| Delivery | Engineering, warranty, support | Padavano contract | Minimum necessary, named, time-bounded access |

BBNC's mission, values, shareholder purpose, land stewardship, and long-term priorities organize
taxonomy and outcome measurement. Software does not decide cultural or institutional validity.

## Lifecycle and authorization floor

The proposed lifecycle is:

```text
draft -> submitted -> evaluation -> approved -> planning -> specification
      -> execution -> verification -> release_candidate -> released
      -> operating -> retired
```

`rejected`, `withdrawn`, and `superseded` are terminal dispositions. `changes_requested` returns the
current package for revision without erasing history.

The server-side floor is default deny:

- authority must resolve to an effective BBNC source and delegation;
- approval binds to one exact artifact revision;
- affected approvals and gates are invalidated by material change;
- initiative owners cannot be their sole release approver;
- missing gates, verification, risk ownership, rollback, or outcome ownership block release;
- exceptions are separately authorized, reasoned, visible, and time-bounded;
- released records are immutable and corrections create new versions;
- unknown classification is rejected as Restricted;
- v1 stores only Public and BBNC-approved Internal data;
- Confidential and Restricted material remains in its owning system behind an opaque reference;
- no AI may approve, interpret policy, accept risk, waive a control, transition state, or release.

## Proposed deployment boundary

After Phase 0 authorization, BBNC would own two private repositories:

- `bbnc-stewardship`: internal web/API, worker, domain kernel, public-content workspace,
  integrations, infrastructure, and tests;
- `bbnc-web`: public Next.js application, signed-package ingestion, public read model, search,
  redirects, infrastructure, and tests.

The public application cannot import internal domain code or query the internal database. A
versioned BBNC-owned OpenAPI and JSON Schema package is the only shared contract.

Repository creation, Azure/Entra provisioning, DNS, identities, keys, backups, logs, and production
access are forbidden before BBNC executes the Phase 0 charter and issues an authority receipt.

## Proposed signed public projection

The internal worker creates an immutable publication package, signs it using a BBNC-controlled key,
and writes it to a public-safe projection store. Public ingestion verifies transport, signature,
key, timestamp, nonce, schema, fixed `public` classification, asset hashes, links, accessibility
fields, and redirects. Invalid packages are quarantined and cannot change production. Publication
is atomic, returns a signed receipt, and retains the last-known-good release on failure. Withdrawal
uses a signed tombstone, never arbitrary deletion.

WordPress is a migration source, not the target architecture. Retirement occurs only after the new
site clears its rollback window and BBNC proves restoration under its approved retention process.
