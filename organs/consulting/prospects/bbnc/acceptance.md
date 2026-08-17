# Acceptance and evidence contract

## Phase 0 authority receipt

The executed charter and signatures remain in a BBNC-owned private system. Before Phase 1, BBNC
provides a redacted machine-readable receipt with schema `bbnc.phase0.authority-receipt.v1`.
`validate-phase0.py authorize` requires:

- the exact engagement ID and delivery identity;
- a SHA-256 digest for the executed charter;
- executed and effective timestamps;
- explicit acceptance of `phase-1-current-state-discovery` only;
- opaque principal references for all required BBNC roles;
- passed evidence for contracting, data, authority, security, acceptance, and account gates;
- BBNC ownership evidence for repositories, subscription, identity, domain/DNS, keys, backups,
  logs, and audit exports;
- verification by an authorized BBNC role.

The receipt contains no signatures, names, credentials, contract body, private paths, or BBNC data.
The public prospect packet does not record commission or approval.

## Governance and authorization

- Every protected transition has positive and negative authorization tests.
- Expired or revoked delegation cannot act.
- Conflict disclosure invokes the configured recusal rule.
- Cross-organization discovery is denied in UI, API, search, export, and aggregate drill-down.
- Material revision invalidates only affected approvals.
- Missing gate, evidence, risk acceptance, rollback, owner, or outcome plan blocks release.
- Successful release produces independently verifiable immutable hashes and a manifest.

## Publication boundary

- Signature, replay, key rotation, schema mismatch, asset corruption, partial package, expiry,
  supersession, withdrawal, and feed outage fail closed.
- Internal comment, deliberation, risk record, personal identifier, confidential evidence, and
  nonpublic initiative ID never enter payloads, logs, analytics, search, caches, browser storage,
  source maps, or errors.
- Last-known-good public content remains available during internal-platform and feed outages.

## Public experience

- At least 90% unassisted completion for BBNC-approved top tasks in representative testing.
- Critical searches return the correct current result in the top three.
- Every known legacy URL has an approved terminal mapping; no chains, loops, soft 404s, or broken
  internal links.
- Every external system has a named owner, explicit handoff, automated monitor, and fallback contact.
- WCAG 2.2 AA passes automated and manual keyboard, screen-reader, mobile-menu, zoom/reflow,
  contrast, focus, error, caption, transcript, and accessible-document testing.
- Mobile and desktop p75 targets are LCP at most 2.5 seconds, INP at most 200 milliseconds, and CLS
  at most 0.1.
- Critical content remains usable without JavaScript under 1.6 Mbps and 400 ms simulated latency.

## Security, reliability, continuity

- OWASP ASVS Level 2 verification for internal and public administrative surfaces.
- Independent penetration test with zero unresolved critical/high findings.
- Internal availability target 99.9%; public target 99.95%.
- RPO 15 minutes; internal RTO four hours; public RTO two hours; public rollback within 15 minutes.
- PostgreSQL point-in-time recovery for 35 days, encrypted nightly recovery copies, and quarterly
  isolated restore tests.
- Capacity for 200 concurrent internal users and five times expected public campaign traffic.
- Signed artifacts, SBOM, provenance, exact-head CI evidence, and immutable release records for every
  production release.
