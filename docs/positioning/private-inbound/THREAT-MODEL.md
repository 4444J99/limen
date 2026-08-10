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
| Premature surface activation | A form or address becomes public before C06 is approved | selected surface is `null`; live gate requires C06/P07 predicate receipt | live URL and rollback receipt under W01/W02 authority |
| Sensitive overcollection | Intake accepts credentials, identity, financial, medical, or unrelated fields | strict minimal schema and recursive denylist | rendered form inspection plus negative validation tests |
| Provenance spoofing or loss | A lead is routed without trustworthy surface/proof/audience context | both adapters require all three nonempty tags | adapter tests against the selected capture implementation |
| Cross-owner leakage | One client or operating owner can read another owner’s record | ledger keyspace starts with `owner_partition`; aggregate projection drops rows | storage-level partition and authorization tests in the private owner repository |
| Public artifact leakage | Logs, CI, PRs, or receipts expose names, addresses, requests, or drafts | public receipt allowlist and fixture-value redaction test | repository secret/PII scan plus log inspection on exact tested heads |
| Identifier correlation | A public record identifier can be reversed or joined back to a person | preflight IDs are synthetic-only; live IDs must be private random or keyed values and never enter public projections | ID-generation and receipt-redaction tests in the private owner repository |
| Duplicate amplification | Repeated provider delivery creates duplicate opportunities or drafts | deterministic dedupe key independent of provider event ID | provider retry and replay tests |
| Confident misclassification | A weak score is treated as a definitive lead class | minimum score plus winning-margin rule; every low-confidence case routes to review | labeled corpus confusion matrix and threshold receipt |
| Prompt or content injection | Lead text attempts to alter policy, invoke tools, or authorize effects | input is data only; no execution path; drafts are fixed templates with quoted context | adversarial fixture set and tool-capability audit |
| Draft becomes commitment | Generated text promises price, availability, acceptance, signature, or work | draft-only state and explicit prohibited commitments | rendered template review and negative commitment tests |
| Unauthorized outbound send | Capture or draft code gains transport capability | transport capability list is empty; send valve is hard closed and raises | zero-send counter plus network/transport audit across the full journey |
| Evidence laundering | Synthetic fixtures are cited as real client/recruiter validation | fixtures declare `synthetic`, use `.invalid`, and receipts say `synthetic_preflight` | real outcomes require separately sourced private receipts and cannot reuse this proof |
| Retention without purpose | Raw contact or message content persists after its operational need | storage is not implemented here; later adapter must define retention/deletion | private-owner retention policy and deletion/export tests |

## Fail-closed decisions

- No C06/P07 predicate receipt: no live capture integration.
- No selected capture surface: no form or mail adapter wiring.
- Missing consent, source tags, owner partition, or minimal required fields: reject capture.
- Any denied sensitive field: reject capture without echoing its value.
- Low score or narrow winning margin: manual review.
- Missing private storage adapter: no persistence outside the synthetic in-memory harness.
- Any attempted send: raise, increment the blocked-attempt counter, and keep external send count zero.

## Human gates

`HG-PUBLIC-IDENTITY` owns activation of an address, tagged CTA, form, or other public capture surface.
`HG-PUBLICATION-SEND` owns each outbound reply. Neither gate is pulled by this preflight, by a draft,
by a passing synthetic traversal, or by later capture activation.

## Rollback

The preflight rollback is deletion or reversion of this isolated package. Later live integration must
retain the program-owned routes: remove the alias or form and regenerate plain-text CTAs, disable
normalization while retaining provider custody, route everything to manual review, disable draft
families, export and disable the ledger view, and preserve only private, access-controlled receipts.
