# Proposed technical contract

Status: **PHASE 0 PROPOSAL — SUBJECT TO BBNC ENTERPRISE STANDARDS AND ADR APPROVAL**

## Repository and runtime boundary

After authority is proven, the proposed defaults are Node.js 24 LTS, TypeScript strict mode,
Next.js 16, React 19, pnpm with exact lockfiles, PostgreSQL 17 with Drizzle migrations and row-level
security, and PostgreSQL full-text/trigram search. Exact security-patched versions are selected when
BBNC initializes each repository; a major-version change requires an ADR.

The proposed BBNC-owned deployment uses Azure Container Apps, Front Door Premium WAF and Private
Link, Blob Storage, Service Bus, Key Vault, Application Insights, and Log Analytics. Microsoft Entra
ID provides staff and B2B contractor OIDC, with phishing-resistant MFA for privileged roles. Bicep
defines infrastructure; GitHub Actions uses workload-identity federation; OpenTelemetry spans both
products. A conflicting BBNC enterprise standard may replace these defaults through an approved ADR
before repository initialization.

## Stewardship roles

The proposed application roles are Platform Administrator, Governance Steward, Executive Sponsor,
Initiative Owner, Contributor, Functional Reviewer, Release Authority, Auditor, and Integration
Service. A role alone grants nothing. Authorization also resolves organization, classification,
initiative class, delegation scope, effective dates, and separation-of-duty rules.

## Domain records

- OrganizationUnit, Principal, RoleAssignment, Delegation
- AuthorityInstrument, immutable AuthorityVersion, AuthorityRule
- WorkflowTemplate, GateDefinition, GateEvaluation
- Initiative, ValueCase, StagePackage
- Requirement, Milestone, Dependency
- Decision, Risk, Control, Exception, ConflictDisclosure
- ArtifactVersion, Evidence, ExternalRecordLink
- ApprovalRequest, immutable ApprovalDecision
- ReleaseRecord, immutable ReleaseManifest
- OutcomeMetric, OutcomeObservation, ImprovementRecord
- append-only AuditEvent
- PublicContent, MediaAsset, PublicationPackage, PublicationReceipt

## Internal API floor

The internal REST JSON API lives under `/api/v1` and publishes generated OpenAPI 3.1. It uses UUIDv7
identifiers, cursor pagination, UTC storage with Alaska-time presentation, RFC 9457 errors,
`ETag`/`If-Match` for edits, and `Idempotency-Key` for commands.

Principal resources and commands are:

- `/organization-units`, `/principals`, `/delegations`
- `/authority-instruments`, `/authority-rules`, `/workflow-templates`
- `/initiatives`, `/initiatives/{id}/stage-packages`
- `POST /initiatives/{id}/transitions`
- `/initiatives/{id}/risks`, `/gates`, `/evidence`, `/decisions`
- `POST /approval-requests/{id}/decision`
- `/initiatives/{id}/release-candidates`, `/releases`, `/outcomes`
- `/audit-exports`, `/portfolio/metrics`
- `/public-content`, `/publication-packages`, `/publication-receipts`

No generic update endpoint may change lifecycle state.

## Public-content contract

The proposed public types are Page, Service, Program, Opportunity, Deadline, Event, NewsArticle,
PressRelease, Publication, PolicyPosition, Initiative, Person, BusinessGroup, Company, Location,
ContactRoute, Alert, MediaAsset, and ExternalServiceLink.

Every record carries an owner, audience, topic, stable ID, slug, publication/effective/expiry/review
dates, locale, relationships, CTA, SEO/social metadata, accessibility state, and Stewardship release
provenance. Media additionally requires SHA-256, alt text, captions or transcripts, rights/consent
state, and culturally appropriate publication approval.

## Signed projection interface

The public-safe feed exposes:

- `GET /v1/publications?cursor=&limit=`
- `GET /v1/publications/{public_release_id}`
- `publication.released`, `publication.superseded`, and `publication.withdrawn` events

A package contains only schema version, opaque public release ID, type, revision, locale, slug,
publish/effective/expiry timestamps, allow-listed payload, public asset metadata and hashes, public
relationships and redirects, classification fixed to `public`, detached signature, key ID,
timestamp, nonce, and digest.

The public application verifies TLS, signature, key, timestamp, nonce, schema, classification,
asset hashes, links, accessibility fields, and redirects before an atomic publish. Rejected packages
enter quarantine and cannot change the live read model. A signed receipt closes publication.
