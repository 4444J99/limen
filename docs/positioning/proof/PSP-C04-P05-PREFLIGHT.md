# PSP-C04 P05 proof-production preflight

Status: **PREPARED/PREFLIGHT**. This package is deliberately non-publishing and cannot close
PSP-P05 or PSP-C04 while PSP-C02 and PSP-C03 remain open.

The machine-readable contract is
[`psp-c04-proof-contract.json`](psp-c04-proof-contract.json). It turns the P05 scope into six
bounded production contracts without borrowing identity, audience, offer, or CTA decisions from
the unfinished C03 lane.

## 1. Source and claim resolution

Every public sentence must resolve through this chain:

`claim id -> canonical wording -> dated source -> exact head/immutable receipt -> status -> disclosure level -> limitations -> withdrawal action`

Missing, stale, contradictory, private, or implication-only evidence fails closed. A valid source
must include an observation date. A repository assertion is useful discovery input but is not a
publishable status. Adoption, revenue, rankings, percentile claims, and private implementation
details remain withheld unless a later independent primary receipt changes their ledger state.

## 2. Surface-by-claim audit

The later resolver will emit one row for every material claim found on the portfolio front door,
flagship pages, resume, personal profile, organization profile, and flagship repositories. Each
row carries claim id, source ids, observation date, status, disclosure level, drift verdict, and
action. A surface is not clear because its prose sounds plausible; every material cell must resolve
or the containing claim is quarantined.

Current front-door observation on 2026-08-10: the portfolio leads with repository/test volume and
renders a top-percent throughput statement. Those are audit inputs, not approved C04 copy. The
current release stays untouched and the ranking language remains withheld under the claims policy.

## 3. Cost and failure analysis reproduction

The analysis must distinguish model cost, human time, retry cost, failed work, blocked work, and
verification cost over a declared date window and denominator. It must publish a distribution and
missingness record, not a single flattering average. Price-list estimates cannot be described as
actual spend, and failed work cannot be assigned zero cost. If attribution, sampling, privacy, or
denominator checks fail, the analysis is withheld.

## 4. Exact-head flagship receipts

Limen, the UCC Public-Records Intelligence Platform, and AI Chat Exporter each require a fresh
default-branch head, the exact predicate, environment, timestamps, exit code, artifact digest, and
limitations. The only allowed outcomes are `current_pass`, `current_fail`, `not_current`, or
`blocked_external`. A live endpoint alone and a historical green workflow alone are both
insufficient.

## 5. Synthetic-only architecture demonstration

The later demonstration uses invented, non-personal packet, lease, receipt, failure, and recovery
records. It must show the bounded authority and failure branches, not only the happy path. It may
not ingest task-board bodies, operational identifiers, customer material, credentials, private
repository names, or private evidence. This preflight defines the story and safety acceptance only;
it creates no route, component, mock, server, or deployable demo.

## 6. External validation rubric

Acceptable validation is an independent reproduction, dated technical review, consented
collaborator outcome, or reviewed publication/talk with traceable provenance. Each object records
independence, method, claim scope, limitations, date, consent, and withdrawal. The request package
does not leave the repository until `HG-PUBLICATION-SEND` is satisfied. This lane performs no
outreach, send, upload, or publication.

## Formalization boundary

After C02 and C03 close, the resolver may automatically refresh exact heads, bind merged evidence
and claim rows, emit the surface audit, instantiate reproduction requests, and withhold expired
sources. Publication, outreach, claim promotion, visual selection, phase closure, and deployment
always remain separate gates.
