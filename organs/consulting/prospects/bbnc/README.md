# BBNC Stewardship to BBNC.net — prospect packet

Status: **WORKSHOP READY / NOT COMMISSIONED / NOT SENT**

This public-safe packet converts the supplied product plan into the first executable delivery
boundary. It does not claim that Bristol Bay Native Corporation (BBNC) requested, approved, or
commissioned the work. It contains no personal data, signatures, pricing, credentials, private
BBNC material, or production access details.

Padavano is the current delivery identity. `Victoroff` appeared in the source plan, but the live
identity registry supersedes that retired label; no new artifact revives it.

## Product chain

```text
BBNC authority
  -> BBNC Stewardship workflow
  -> verified release
  -> signed public projection
  -> BBNC.net
```

BBNC Stewardship is the proposed internal authority-to-outcome platform. BBNC.net is the proposed
public projection. myBBNC and the existing voting, employment, application, compliance, and
subsidiary systems remain separate systems of record.

## Packet map

| Artifact | Purpose |
|---|---|
| [`product-boundary.md`](product-boundary.md) | Product, authority, data, and system boundaries |
| [`technical-contract.md`](technical-contract.md) | Proposed stack, domain, API, content, and projection contracts |
| [`delivery-roadmap.md`](delivery-roadmap.md) | Phase 0 through Omega with executable exit predicates |
| [`acceptance.md`](acceptance.md) | Cross-cutting test and acceptance contract |
| [`sources.md`](sources.md) | Public references and their limited evidentiary role |
| [`phase-0/workshop.md`](phase-0/workshop.md) | Facilitator-ready authority-and-ownership workshop |
| [`phase-0/website-modernization-charter.md`](phase-0/website-modernization-charter.md) | Unsigned charter to complete during the workshop |
| [`phase-0/preparation.json`](phase-0/preparation.json) | Machine-readable current state and human gates |
| [`../../validate-phase0.py`](../../validate-phase0.py) | Preparation and authority predicates |

## Executable boundary

The prepared packet must pass:

```bash
python3 organs/consulting/validate-consulting.py organs/consulting/prospects/bbnc.yaml
python3 organs/consulting/validate-phase0.py prepare \
  --packet organs/consulting/prospects/bbnc/phase-0/preparation.json
```

Phase 1 must not start unless BBNC has stored the executed charter in a BBNC-owned private system
and issued the redacted receipt described in `acceptance.md`. The authority check is intentionally
fail-closed when that receipt is absent:

```bash
python3 organs/consulting/validate-phase0.py authorize \
  --packet organs/consulting/prospects/bbnc/phase-0/preparation.json \
  --receipt /bbnc-owned/path/phase-0-authority-receipt.json
```

No signed charter, personal role assignment, or BBNC-private locator belongs in this public repo.
