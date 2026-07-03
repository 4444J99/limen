# A-MAVS-OLEVM — MICRO FACE
## The 444-file archive, ET4L, and LOCREANCE

*Anthony's live artist instance. Internal review only.*

> **What you are reading:** the micro face is the proof that the reusable
> studio/temple platform holds against a real body of work. The macro platform
> is in [`MACRO-FACE.md`](MACRO-FACE.md).

---

## Why these three chambers

| Chamber | Stress test | Why it matters |
|---|---|---|
| 444-file photo archive | Primary source body with file sprawl risk | Proves the Vault and Catalog can preserve provenance before curation begins |
| ET4L | Thematic series extracted from the archive | Proves the Gallery and Press can turn cataloged work into a coherent exhibition argument |
| LOCREANCE | Active, growing practice body | Proves the Studio and Calendar can handle continuing production without losing custody state |

Together they test preservation, exhibition, and active practice — the three rhythms
every working artist navigates simultaneously.

---

## Fleet standing

| Chamber | Current standing | Next gate | Artist gate |
|---|---|---|---|
| 444-file photo archive | CATALOGED | Preservation report to CURATED | Anthony confirms provenance and risk status |
| ET4L | CURATED | Statement + caption set to STAGED | Anthony rewrites and approves exhibition language |
| LOCREANCE | RAW | Intake batch to CATALOGED | Anthony confirms what enters the body of work |

No chamber publishes, alters source files, or treats generated material as original work.

---

## Chamber 1: 444-file photo archive

**What this proves:** a raw archive can be made navigable without rewriting the
artist's source files.

**Mandate:** hold the archive as source truth: stable intake, provenance, custody
state, and preservation risk before any exhibition selection.

**What exists now:**

- Chamber record in `chambers/photo-archive.yaml` — validated against organ rules 1-6
- CATALOGED standing with provenance metadata stubbed for all 444 files
- Source file inventory captured: medium (photography), human owner identified,
  scope boundary set
- Catalog records propose the same five-primitive completeness the platform requires:
  Member (each piece), Mandate (archive integrity), Standing (cataloged),
  Standard (review-ready criteria), Governance (artist-gated progression)
- Human gates documented: provenance confirmation, preservation-risk decision,
  curation eligibility approval

**What the Vault currently holds:**
- Stable chamber identity record
- Medium: photography
- Human owner: Anthony J. Padavano
- Standing: CATALOGED as of 2026-07-03
- Next standing: CURATED (advances, never regresses)
- Standard rubric: "A file is review-ready only when source path, medium,
  date/provenance note, custody state, and risk posture are explicit"
- Artist gate: true for all outward progression
- Evidence anchored to KERNEL.md, MACRO-FACE.md, and MICRO-FACE.md

**Next proof step:**

Issue the preservation report: what is stable, what is at risk, what needs a
format or custody decision, and which pieces are eligible for first grouping.

The report will cover:
- File format stability across the 444-item corpus
- Custody continuity gaps (if any)
- Pieces whose provenance is complete enough for exhibition eligibility
- First recommended grouping candidates for the Gallery

---

## Chamber 2: ET4L

**What this proves:** a thematic series can be extracted from the archive without
collapsing curation into a file dump.

**Mandate:** build the exhibition argument: selected works, sequence logic,
series statement, and caption set.

**What exists now:**

- Chamber record in `chambers/et4l.yaml` — validated against organ rules 1-6
- CURATED standing with selection proposed and Mandate named
- Series identity: ET4L — a thematic extraction from the 444-file photo archive
- Medium: mixed archive sequence (works drawn from the primary archive)
- Human gates documented: selection approval, statement rewrite, release event
  approval
- Standard rubric: "A series is stage-ready only when selection, sequence logic,
  title, statement, and caption set are present for artist rewrite"

**What the Gallery currently holds:**
- Selection logic documented: pieces named, series argument drafted
- Mandate scoped: convert a curated selection into an exhibition argument
  with statement, caption set, and staged package
- Exhibition arc positioned between CURATED and STAGED
- Artist authority preserved: the organ may propose language; Anthony signs it

**Next proof step:**

Draft the ET4L statement and caption set for artist rewrite.

The draft package will include:
- Series title (proposed)
- Exhibition statement — the argument the series makes, in the artist's idiom
- Per-piece captions: date, medium, provenance note, and context
- Sequence logic note: why the pieces are ordered as proposed
- A STAGED package ready for Anthony's review: accept, revise, or reject

---

## Chamber 3: LOCREANCE

**What this proves:** an active practice can keep growing while the archive
remains orderly.

**Mandate:** keep new work from entering as undifferentiated residue. Intake must
name medium, provenance, custody state, and whether the piece is raw, cataloged,
or eligible for curation.

**What exists now:**

- Chamber record in `chambers/locreance.yaml` — validated against organ rules 1-6
- RAW standing with intake protocol defined and first cadence proposed
- Medium: ongoing mixed creative work (photography, writing, and other output)
- Human gates documented: accession approval, cadence approval, release readiness
  approval
- Standard rubric: "A new work enters the catalog only when medium, provenance,
  source custody, and intended chamber are explicit"
- Forbidden acts established: no source file alteration, no autonomous publication,
  no art-creation-on-behalf

**What the Studio currently holds:**
- Open intake stream with named boundary: what qualifies for accession
- Cadence proposal pending: how often new work is batched for Catalog entry
- Artist gate active before any work passes RAW → CATALOGED
- Evidence anchored to all three face documents

**Next proof step:**

Run one intake batch through the Vault and Catalog: stable records, standing
updates, and a decision list for what can become a Gallery grouping.

The intake batch will include:
- The candidate pieces and their provenance metadata
- Medium, source custody state, and creation dates
- A recommendation for which chamber each piece belongs in
- A cadence proposal for ongoing intake rhythm
- Standing update: RAW → CATALOGED for approved accessions

---

## What the three chambers prove together

1. **The artist remains sovereign.** All curation, language, preservation-risk
   decisions, and releases stay gated by Anthony.
2. **The archive becomes navigable.** Every chamber has Member, Mandate,
   Standing, Standard, and Governance.
3. **Exhibition is staged, not improvised.** Work moves from source custody to
   grouping to language to release with explicit gates.
4. **No source file is overwritten.** The organ records and proposes; it does
   not alter original art.
5. **The 9-chamber toolkit is real.** Vault, Catalog, Studio, Gallery, Archive,
   Press, Calendar, Atrium, and Scriptorium are each instantiated across the
   three micro chambers.

---

## Validation

Run:

```bash
python organs/artist/validate-artist.py --chambers
```

Expected result: all three chamber records pass the full six-rule artist-organ
validation suite (standing progression, artist gate, primitive completeness,
standard evidence, overreach prohibition, artifact requirement).

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (domain model),
[`MACRO-FACE.md`](MACRO-FACE.md) (platform face), [`CHARTER.md`](CHARTER.md)
(roles and workflows).*
