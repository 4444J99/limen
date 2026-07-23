# DECORVM — the Professionalization Keeper

*Decorum* is the Roman rhetorical virtue of "the fitting/becoming" — the propriety that makes a
public act land as dignified rather than embarrassing. DECORVM is the organ that guards it: a
continuous keeper that answers one question every beat — **is anything on a public surface currently
egg-facing?** — and drives each embarrassment class to structural closure so it never recurs.

## What it is

DECORVM owns no measurement machinery and no surface list. It **federates** the estate's six existing
quality organs and rolls their sub-verdicts into ONE answer:

| Department | Organ | Checks |
|-----------|-------|--------|
| experience | `scripts/experience-audit.py` | reachable / fast / light / no console errors |
| visual | `experience-judge` → `experience-judgments.yaml` | layout / typography / coherence / trust |
| seo | `scripts/seo-audit.py` | README/SEO 10-rung standard (scoped to value-repos) |
| countenance | `scripts/vvltvs-organ.py` | public numbers not drifting from SSOT |
| links | `scripts/link-health.py` | no dead links on the public front doors |
| moat | `scripts/moat-audit.py` | no private value leaked onto a public repo |

…and adds the **polish/voice lane** none of them covered: spellcheck (vendored typo map), bio/positioning
staleness (git authored age), narrative accuracy (claims vs contribution mix), and a model-in-the-loop
voice-judge queued whenever a prose surface changes.

## Files

- `scripts/decorum-keeper.py` — the federator + polish lane + effector. `--sweep` (default), `--doctor`
  (offline), `--json`, `--apply` (armed by `LIMEN_DECORUM_APPLY=1`).
- `institutio/governance/decorum-surfaces.yaml` — declared departments, severity floor, polish + off-platform config.
- `institutio/observatory/decorum-judgments.yaml` — the voice-judgment register (content-SHA pinned).
- `logs/decorum.json` / `logs/decorum.html` — the verdict + its public-safe face.
- Sensor `decorum` in `institutio/governance/sensors.yaml` (heartbeat, cadence 6, read-only default).

## Laws

- **Fail-open.** An unmeasured department is *skipped*, never *failed* — a keeper that cries wolf
  because a dependency is absent is its own egg-face.
- **Read-only by default.** The effector (one idempotent `DECORUM-<lane>-<surface>` ticket per finding,
  via the tabularius broker) mutates only when `LIMEN_DECORUM_APPLY=1` arms it. It never sends, never wipes.
- **Derive, never pin.** Surfaces come from the existing registries; the department set is declared data.

See `docs/IDEAL-FORMS-LEDGER.md` → **IF-DECORUM**.
