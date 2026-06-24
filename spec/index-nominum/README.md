# INDEX·NOMINVM — the institution of names

*The registry of names, and the magistrate who keeps it.* This is the home of every naming
decision in the estate: how a thing may be spelled, structured, identified, and voiced. It is the
third register of the constitution's four-part Latin index apparatus — `Index Rerum Faciendarum`
(things to do), `Index Locorum` (places), **`Index Nominum`** (names), `Index Rerum` (things) —
declared in `organvm-corpvs-testamentvm` as `IRF-IDX-002` and, until now, unbuilt.

Naming is **cross-cutting**: it governs both the `organvm` portfolio and the life-pillars
(Academia · Legal · Social). So it lives at the META/constitutional layer, not inside any one
pillar — one canon, enforced everywhere.

---

## The five layers

The institution unifies naming knowledge that today is smeared across the estate. Layer one is
in-canon and enforced; the rest are convergence targets (Phase III).

| Layer | Governs | Status | Converge from |
|---|---|---|---|
| **Orthographia** | letterforms — `U→V`, `J→I`, `W→VV`, `QU→QV`; the forbidden set | ✅ in canon | `NAMING.md` |
| **Morphologia** | structure `essence--function--cadence` + Latin token vocab (Machina·Codex·Speculum·Materia…) | ◻ scattered | `…/standards/22-essence-function-naming-convention.md` · `organvm/brainstorm-…/03-latin-naming-schema…` |
| **Identitas** | identity math — content-addressed UID, genus–differentia | ◻ scattered | `organvm/system-system--system--monad/system--naming-calculus.md` |
| **Lentes** | semantic naming-chains (13 substrates × 7 traditions, HYDOR…) | ◻ scattered | `sovereign-systems--elevate-align/src/data/aesthetics-vocabulary.ts` |
| **Vox** | editorial voice, frontmatter + tag governance | ◻ scattered | `organvm/editorial-standards/` |

---

## The files

- **`NAMING.md`** (repo root) — the human charter for **Orthographia**: the principle, the two
  tiers (substitutions that survive into a domain · layout that lives only in the wordmark), the
  avoid-list, registers, and worked examples.
- **`canon.yaml`** — the machine form CENSOR reads. Substitutions, the forbidden set, the
  morphology grammar + token vocabulary, the layer map. *Derive-never-pin:* retune a rule here and
  the enforcer follows; no substitution is hardcoded in the script.
- **`roll.yaml`** — the census: the roll of canonical names. Every entry must satisfy the canon or
  CENSOR issues a nota. Seeded from the canon already in use (`LIMEN`, `STVDIVM`, `VLTIMA`,
  `ORGANVM`, `CORPVS`, `SPECVLA`, `AVDITOR MVNDI`, `QVICKEN`, `STYX`…).

---

## CENSOR — the enforcer

`scripts/censor.py`. In Rome the *censor* kept the census — the album of names — and enforced the
*regimen morum*, marking any violation with the **nota censoria**. The mapping is exact.

```
python3 scripts/censor.py                  # validate the roll; exit 1 on any nota   (CI gate)
python3 scripts/censor.py --apply          # also write logs/censor.json            (organ-health probe)
python3 scripts/censor.py --check "<name>" # derive a candidate's canon form        (mint helper)
```

`--check` is the everyday tool — call it before minting any title, product, or domain:

```
$ python3 scripts/censor.py --check "Studium IV"
  candidate : Studium IV
  wordmark  : STVDIVM IV
  domain    : stvdivm-iv
    ✗ orthography: 'Studium IV' → canon 'STVDIVM IV'
```

**Where it's wired (built on the existing organ pattern, not a new silo):**

- **CI gate** — a `python`-job step in `.github/workflows/ci.yml` validates the canon on every PR
  touching `spec/**` or `scripts/**`. Always-on; protects the roll regardless of the heartbeat gate.
- **Heartbeat organ** — `C_CENSOR` beat in `scripts/heartbeat-loop.sh`, gated **OFF** by default
  (`LIMEN_CENSOR=1` is your knob) so estate-wide enforcement only fires when you bless it.
- **Organ-health rung** — registered in `scripts/organ-health.py` (`CENSOR`), so the organism feels
  whether it's firing; reads `gated (intentional)` until enabled, never a false `down`.

---

## The plan

| Phase | What | Owner / gate |
|---|---|---|
| **I — CENSOR** | canon + roll + enforcer + CI gate + heartbeat beat + organ-health rung | ✅ built (this worktree) |
| **II — Incorporation** | PR to `organvm-corpvs-testamentvm`: register `INDEX·NOMINVM` as `IRF-IDX-002`; mirror the canon as canonical | **your gate** |
| **III — Convergence** | fold Morphologia · Identitas · Lentes · Vox in; close gaps (domain registry, branch/PR style guide, unified glossary, design-token export) | deliberate sweep |
| **IV — Estate rollout** | CENSOR as a required check across the 149-repo registry | **your gate** |

---

## Adding a name

Append to `roll.yaml` with `display` (the wordmark) and `domain` (the lowercased, substitution-only
label). Run `python3 scripts/censor.py` — green means it's in canon, a `✗ nota` tells you the
derived correct form. The roll is the census; keeping it true is keeping the institution honest.
