# A-MAVS-OLEVM - MICRO FACE
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

Together they test preservation, exhibition, and active practice.

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

- Chamber record in `chambers/photo-archive.yaml`
- CATALOGED standing with next gate set to CURATED
- Human gates for provenance confirmation and preservation-risk decisions

**Next proof step:**

Issue the preservation report: what is stable, what is at risk, what needs a
format or custody decision, and which pieces are eligible for first grouping.

---

## Chamber 2: ET4L

**What this proves:** a thematic series can be extracted from the archive without
collapsing curation into a file dump.

**Mandate:** build the exhibition argument: selected works, sequence logic,
series statement, and caption set.

**What exists now:**

- Chamber record in `chambers/et4l.yaml`
- CURATED standing with next gate set to STAGED
- Human gates for selection, statement, and release approval

**Next proof step:**

Draft the ET4L statement and caption set for artist rewrite. The organ may
propose language; Anthony signs the language.

---

## Chamber 3: LOCREANCE

**What this proves:** an active practice can keep growing while the archive
remains orderly.

**Mandate:** keep new work from entering as undifferentiated residue. Intake must
name medium, provenance, custody state, and whether the piece is raw, cataloged,
or eligible for curation.

**What exists now:**

- Chamber record in `chambers/locreance.yaml`
- RAW standing with next gate set to CATALOGED
- Human gates for accession and release cadence

**Next proof step:**

Run one intake batch through the Vault and Catalog: stable records, standing
updates, and a decision list for what can become a Gallery grouping.

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

---

## Validation

Run:

```bash
python organs/artist/validate-artist.py --chambers
```

Expected result: all three chamber records pass the first six artist-organ
rules.

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (domain model),
[`MACRO-FACE.md`](MACRO-FACE.md) (platform face), [`CHARTER.md`](CHARTER.md)
(roles and workflows).*
