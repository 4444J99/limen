# Claim correction, withdrawal, and source-change protocol

This protocol is the W07 companion to the W06 policy gate. It is deliberately
offline and source-safe: it validates exported claim metadata, stages generated
surfaces, and never publishes or contacts an external service.

## W05 integration seam

W05 remains the owner of `docs/positioning/claims-ledger.md` and its evidence
packets. When it is ready, it exports the following minimal contract for W06:

```json
{
  "schema_version": "limen.positioning.claim-ledger-export.v1",
  "forbidden_language": ["example prohibited wording"],
  "claims": [{
    "id": "lowercase.public-safe-id",
    "statement": "Bounded public wording.",
    "publication_status": "publishable",
    "visibility": "public",
    "source": {
      "url": "https://public.example/source",
      "observed_at": "2026-08-10T00:00:00Z",
      "sha256": "64 lowercase hex characters",
      "current_sha256": "optional current 64-character digest"
    },
    "valid_until": "2026-09-10T00:00:00Z"
  }]
}
```

`scripts/claim-policy.py` rejects private/restricted, withdrawn, unsourced,
stale, future-dated, malformed-timestamp, source-changed, inverted-validity, or
prohibited-language claims. Public sources must use credential-free HTTPS URLs.
Their hosts must be public DNS names on the default HTTPS port; localhost,
internal/special-use names, and IP literals fail closed. Claims and report paths
must be distinct files. `forbidden_language` must be present, although an empty
list is valid. The report contains only claim IDs and reason codes, never
statements, source URLs, or private data.

The generator-side surface manifest is likewise a small contract:

```json
{
  "schema_version": "limen.positioning.public-surface-manifest.v1",
  "surfaces": [{"id": "frontdoor", "path": "frontdoor.md", "claim_ids": ["claim.id"]}]
}
```

Each rendered claim must be bounded by
`<!-- positioning-claim: claim.id:start -->` and
`<!-- positioning-claim: claim.id:end -->`. The generator writes to a fresh
staging directory outside the source root. Every surface's bounded marker IDs
must equal that surface's manifest `claim_ids` before any output is written.
The policy report's `accepted_claim_ids` plus `rejected_claims[].claim_id` form
the complete adjudicated claim universe. A manifest claim outside that universe
is quarantined with the public-safe reason `absent_from_policy_report`; it never
passes through unchanged. A bounded marker omitted from its own surface manifest
is a malformed generation contract and stops the batch before any write. The
quarantine report contains public-safe IDs and reason codes only and always
records `publication_effect: none`.
The generator runs W06 and promotes no files when the policy report has a
rejected claim. This is the exact seam; neither this protocol nor W06 modifies
the W05 ledger or its evidence files.

## Incident classes and deterministic route

| Class | Detection | Immediate disposition | Restoration criterion |
| --- | --- | --- | --- |
| `unsupported` | missing statement or source contract | quarantine | an evidence-backed export row passes W06 |
| `stale` | `valid_until` predates the evaluation time | quarantine | refreshed evidence and a later validity bound pass W06 |
| `private_or_restricted` | non-public visibility or a source URL without a public DNS HTTPS host on the default port | quarantine | a public-safe replacement is independently reviewed |
| `forbidden_language` | configured prohibited wording | quarantine | corrected bounded wording passes W06 |
| `source_changed` | recorded and current source digests differ | quarantine | source is re-adjudicated and its digest is refreshed |
| `invalid_timestamp` | a claim-local `source.observed_at` or `valid_until` is missing or malformed | quarantine | both timestamps satisfy the RFC3339 UTC contract |
| `future_source` | source observation is later than the fixed evaluation time | quarantine | a real, non-future observation passes W06 |
| `invalid_validity_window` | validity ends before the source observation | quarantine | a chronologically valid evidence window passes W06 |
| `withdrawn_or_unapproved` | status is not `publishable` | quarantine | a new approved source row passes W06 |
| `absent_from_policy_report` | a surface manifest names a claim absent from both accepted and rejected policy verdicts | quarantine | the claim enters the W05 export, passes W06, and the surface is regenerated |

1. Create a correction record before regeneration. Do not repair public copy by hand.
2. Run `claim-policy.py` at a fixed RFC3339 `--as-of` time. A nonzero result is a
   quarantine decision, not a release decision.
3. Run `claim-surface-quarantine.py` against a fresh generated staging tree and
   the complete public-surface manifest. It produces quarantined copies only;
   it does not alter the source tree or publish. Claims absent from the complete
   policy verdict are quarantined with `absent_from_policy_report`, never copied
   through by omission.
4. Correct the ledger through its W05 owner, regenerate all declared public
   surfaces into a new staging tree, and require a clean policy report plus
   surface-manifest coverage before review.
5. A separate reviewed release process may promote the clean staged result.
   This protocol grants no publication authority.

## Correction record v1

The durable correction owner records only safe metadata:

```json
{
  "schema_version": "limen.positioning.correction-record.v1",
  "incident_id": "public-safe-identifier",
  "claim_ids": ["lowercase.public-safe-id"],
  "incident_class": "source_changed",
  "detected_at": "2026-08-10T00:00:00Z",
  "policy_report_sha256": "64 lowercase hex characters",
  "surface_manifest_sha256": "64 lowercase hex characters",
  "quarantine_state": "staged",
  "restoration_criterion": "new public claim export passes policy after regeneration"
}
```

Raw claim wording, private source material, contact data, and repository-private
details remain in their owning custody; they never belong in the correction
record or generated public surface.

## Synthetic drill

`python3 scripts/claim-quarantine-drill.py --fixture-dir scripts/tests/fixtures/positioning-claim-drill --json`
creates a disposable staging copy of two synthetic public surfaces. The fixture
has a deliberately changed source digest, so W06 rejects it. W07 then removes
the bounded synthetic claim from every manifest-declared surface, writes only
quarantined staging copies, and proves no publication effect.
