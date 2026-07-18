# Research backend

Limen invokes research; Studium Generale owns the workflow, profiles, schemas,
and acceptance rules in `organvm/praxis-perpetua`. A research provider is not a
Limen agent and is never added to the agent registry.

The canonical profile registry is loaded at execution time from
`governance/research-backend-profiles.yaml` in the Studium owner. Override its
location with `--catalog` or `LIMEN_RESEARCH_CATALOG` for an isolated branch or
fixture. Provider and model catalogs remain live external state: requests name
capabilities and constraints, not model identifiers.

## Prepare an attended run

```bash
limen research prepare request.yaml \
  --catalog /path/to/praxis-perpetua/governance/research-backend-profiles.yaml \
  --work-dir /private/research/handoff
```

For an eligible attended profile this writes:

- a ready-to-submit prompt for the **Limen Research** Project or Space;
- a typed `ManualHandoff` containing prompt and ingest references, never the prompt body;
- a sanitized `ResearchReceipt` with request/catalog hashes and zero variable
  cost.

Because no normalized report exists yet, `manual_pending` and pre-research
blocked receipts record `tracked_output_safe: false`.

`--launch` only opens the attended research page. It does not submit the
prompt, use Computer, schedule work, connect services, purchase credits, send
messages, or write to an external system.

The request must declare, using the exact canonical JSON types and owner
semantics:

- question and required capabilities;
- freshness and domain constraints;
- verification strength and minimum primary-source ratio;
- SGO preservation tier, external-transmission class, latency ceiling, and
  variable-spend ceiling;
- owner repo plus durable report, receipt, and raw-export references.

Client-private or essence-private requests require a `private-owner://...`
raw-export reference when the raw export is retained, plus
`external_transmission: forbidden`. The ingest gate proves the tracked owner
from its Git `origin`. A tracked raw-export reference must resolve to the exact
file beneath that owner root. A `private-owner://<owner-id>/<path>` reference
requires `--raw-owner-root`; the authority must match the request owner and the
export must resolve to that exact path. A private root nested inside the tracked
checkout is accepted only when the export is both untracked and ignored.

## Ingest the Markdown export

```bash
limen research ingest /private/research/export.md request.yaml \
  --catalog /path/to/praxis-perpetua/governance/research-backend-profiles.yaml \
  --owner-root /path/to/owner-repo \
  --handoff-receipt /private/research/SGO-REQ-....receipt.json \
  --verification-file /private/research/source-verifier-attestation.yaml \
  --sanitization-file /private/research/output-sanitization-attestation.yaml \
  --raw-owner-root /private/owners/limen \
  --operator-handling-seconds 840
```

The verifier requires the normalization appendix rendered in the attended
prompt: material claims, contradictions, unknowns, negative searches, novel
actionable findings, and a source manifest with retrieval metadata. It rejects
broken citations, unsupported material claims, missing retrieval dates, lost
source records, insufficient primary-source coverage, and path escape from the
declared owner root.

Provider labels such as `supported`, `Primary`, or a quality tier are never
accepted as proof. Studium's Source Verifier must attest the exact claim and
source sets, bind each exact source URL, attest whether it resolved,
independently grade each source, confirm its metadata, and bind the
attestation to the request and verification time. Limen performs no network
fetch during ingestion; this avoids treating an untrusted citation or redirect
as an SSRF-capable URL probe.

The Output Sanitizer must separately attest the exact raw Markdown export hash,
request, preservation tier, transmission authority, tracked-output safety,
redactions, and absence of credentials, private prompt bodies, and sensitive
raw material from tracked derivatives. The private raw Session export may echo
the submitted question or retain credential-shaped text, but it then requires
proven `private-owner://` custody. Limen normalizes it first, then
machine-scans the candidate EvidencePacket/report and receipt; an echoed prompt
or secret that survives into a tracked derivative fails closed.
`sanitized_only` outputs require at least one recorded redaction.

Both attestation shapes are canonical Studium schemas. The original
manual-pending receipt is also required so a changed request, catalog, or
selected profile cannot be ingested under a stale handoff.

Accepted exports become a claim-to-source `EvidencePacket` and sanitized
receipt. The report is written and checked before the terminal receipt is
emitted. Rejected exports write and check their typed `BlockedReceipt` before
their terminal research receipt. Missing or invalid sanitization proof records
`tracked_output_safe: false`; it is never inferred from preservation tier.
The attended handling duration is required at ingestion so the pilot gate is
measured rather than inferred. Writing and coding agents consume only accepted
packets.

## Automation remains fail-closed

- Missing API credentials or spend health never disables attended Pro
  handoffs.
- Search and synthesis API profiles cannot make a live call. Even when fixture
  health flags pass, Limen returns `BlockedReceipt` until a deliberate live
  adapter is implemented and enabled by the owner policy.
- Computer remains disabled until its live credit balance, refill state,
  prohibitions, and value case are verified.
- No profile silently falls back to a higher-cost, lower-privacy, or weaker
  verification surface.

Official product behavior is current external state, not a repository
constant. Research mode currently selects its own models; Perplexity Sessions
currently export Markdown; Search API discovery and generated synthesis are
separately metered surfaces. Re-check the official documentation before any
automation activation.
