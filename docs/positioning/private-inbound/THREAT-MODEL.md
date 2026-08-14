# PSP-C07 private-inbound threat model

## Boundary and protected assets

The future funnel will handle contact identity, message content, consent, source/proof/audience
provenance, fit scores, routing decisions, draft bodies, opportunity stages, objections, and
outcomes. Those are private operational records. This repository may hold their schemas, synthetic
fixtures, aggregate-safe receipts, and public policy; it must not hold real lead payloads or private
opportunity evidence.

The trust boundary begins at the selected C06 capture surface and ends at repository-specific
private storage adapters. Public surfaces may create provenance tags, but they may not read private
records. Drafting may prepare a response, but it does not acquire send authority.

## Threats and controls

| Threat | Failure mode | Preflight control | Integration proof required later |
|---|---|---|---|
| Premature surface activation | A form or address becomes public before the commercial and public-surface prerequisites close | selected surface is `null`; live gate requires genuine W07 evidence, P04/P07 predicate receipts, a selected C06 surface, and separate leaf authority | live URL and rollback receipt under W01/W02 authority |
| Sensitive overcollection | Intake accepts credentials, identity, financial, medical, or unrelated fields | strict minimal schema and recursive denylist | rendered form inspection plus negative validation tests |
| Provenance spoofing or loss | A lead is routed without trustworthy surface/proof/audience context | both adapters require all three tags, a bounded character set, and no control characters | adapter tests against the selected capture implementation |
| Header or tag injection | Intake tags smuggle line breaks, headers, or unbounded values into a downstream adapter | source tags are normalized and rejected on controls, whitespace, or values outside the bounded pattern | provider-specific header encoding and negative tests |
| Oversize or adversarial intake | Huge or malformed fields exhaust a handler or bypass validation | exact per-field length limits, strict types, a bounded batch, and unknown-field rejection | ingress body/rate limits and load tests in the selected adapter |
| Cross-owner leakage | One client or operating owner can read another owner’s record | ledger keyspace starts with `owner_partition`; aggregate projection drops rows | storage-level partition and authorization tests in the private owner repository |
| Plaintext private custody | A ledger persists contact or request content without encryption or embeds key material in code | seal/open/delete adapter boundary rejects plaintext persistence; contract requires an external secret manager and contains no key material | real cipher, key rotation, backup, restore, and access-control predicates in the private owner repositories |
| Public artifact leakage | Logs, CI, PRs, or receipts expose names, addresses, requests, or drafts | public receipt allowlist and fixture-value redaction test | repository secret/PII scan plus log inspection on exact tested heads |
| Identifier correlation | A public record identifier can be reversed or joined back to a person | preflight IDs are synthetic-only; live IDs must be private random or keyed values and never enter public projections | ID-generation and receipt-redaction tests in the private owner repository |
| Duplicate amplification | Repeated provider delivery creates duplicate opportunities or drafts | deterministic dedupe key independent of provider event ID | provider retry and replay tests |
| Confident misclassification | A weak score is treated as a definitive lead class | minimum score plus winning-margin rule; every low-confidence case routes to review | labeled corpus confusion matrix and threshold receipt |
| Prompt or content injection | Lead text attempts to alter policy, invoke tools, or authorize effects | input is data only; no execution path; drafts are fixed templates with quoted context | adversarial fixture set and tool-capability audit |
| Draft becomes commitment | Generated text promises price, availability, acceptance, signature, or work | draft-only state and explicit prohibited commitments | rendered template review and negative commitment tests |
| Unauthorized outbound send | Capture or draft code gains transport capability | transport capability list is empty; send valve is hard closed and raises | zero-send counter plus network/transport audit across the full journey |
| Dashboard row leakage | A convenient view exports private contact or message rows | operator projection is partition-scoped and excludes contact/request fields; public dashboard is aggregate-only with row export disabled | authorization, export, and snapshot tests in the ledger owner repository |
| Evidence laundering | Synthetic fixtures are cited as real client/recruiter validation | fixtures declare `synthetic`, use `.invalid`, and receipts say `synthetic_preflight` | real outcomes require separately sourced private receipts and cannot reuse this proof |
| Retention without purpose | Raw contact or message content persists after its operational need | category defaults, immediate consent/deletion triggers, ledger/dedupe/sealed deletion, and identifier-free aggregate receipts | owner-ratified policy plus backup, deletion, and restoration tests |

## Fail-closed decisions

- No genuine five-reader W07 receipt: no P03/P04 progression and no live capture integration.
- Synthetic, model, author, or implementation-agent responses never satisfy the W07 gate.
- No P04 or P07 predicate receipt: no live capture integration.
- No selected capture surface: no form or mail adapter wiring.
- Missing consent, source tags, owner partition, or minimal required fields: reject capture.
- Unknown fields, oversize fields, or source-tag control characters: reject capture without echoing
  the submitted value.
- Any denied sensitive field: reject capture without echoing its value.
- Low score or narrow winning margin: manual review.
- Missing encryption/key-management adapter: no persistence outside the synthetic in-memory harness.
- Consent withdrawal, a verified deletion request, or expiration: delete the ledger row, dedupe key,
  derived draft, and sealed payload through private-owner adapters; expose only aggregate counts.
- Any attempted send: raise, increment the blocked-attempt counter, and keep external send count zero.

## Human gates

`HG-PUBLIC-IDENTITY` owns activation of an address, tagged CTA, form, or other public capture surface.
`HG-PUBLICATION-SEND` owns each outbound reply. Neither gate is pulled by this preflight, by a draft,
by a passing synthetic traversal, or by later capture activation.

## Rollback

The preflight rollback is deletion or reversion of this isolated package. Later live integration must
retain the program-owned routes: remove the alias or form and regenerate plain-text CTAs, disable
normalization while retaining provider custody, route everything to manual review, disable draft
families, disable the ledger view, apply the owner-ratified retention/deletion path, and preserve only
private, access-controlled receipts. A public row export is never part of rollback.
