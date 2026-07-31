# docs/diurnal — the day, in three phases

One dated page per day: `YYYY-MM-DD.md`. Written by the `diurnal` organ
(`scripts/diurnal.py`), whose sections are declared in
[`institutio/governance/diurnal.yaml`](../../institutio/governance/diurnal.yaml) and held
in parity by `scripts/check-diurnal.py`.

## The three phases reach toward each other

| Phase | Reaches **back** | Reaches **forward** |
|---|---|---|
| **morning** (06:00) | last evening's carry; the night's alerts | the full dashboard, plus `claims[]` — falsifiable predictions the evening will score |
| **midday** (12:00) | re-probes each morning claim mid-flight | `corrections[]`; pushes **only** on drift, so a silent noon means the morning still holds |
| **evening** (21:00) | scores every claim `held` / `missed` / `noop` | `carry[]` for tomorrow, and `cuts[]` |

A claim is *"section X's metric will fall below N today."* Scoring a claim and scoring a
section are **one measurement** — which is what makes the cut loop evidence-based rather
than a matter of taste.

## Two doctrines, both inherited from `ideal-forms.yaml`

**Freshness is derived, never asserted.** A stale *cache* may hold a wrong value, so its
value is withheld and the age is named. A stale *registry* holds a frozen but still-true
value, so it is reported and annotated `FROZEN`. Neither is ever printed as if current.
This organ exists because ~198 runtime artifacts had no freshness index — and on
2026-07-31 `session-orientation.md` reported "Autonomy — PAUSED" after the marker was gone.

**You cannot prune what you cannot score.** A section with `metric: null` is
`cuttable: false`, enforced by check C of `scripts/check-diurnal.py`. A cuttable section
with no metric would accrue an unfalsifiable noop streak and eventually delete itself on
no evidence at all.

## Cut authority, and its six bounds

The evening phase — and only the evening phase — may cut a section that scored noop for
`LIMEN_DIURNAL_CUT_THRESHOLD` (default 5) consecutive **engaged** days.

1. `protected: true` sections are never cuttable, whatever they score.
2. The threshold is also the observation runway: no cut can fire in the first 5 engaged days.
3. A day with no commits is **unscored**, not noop — a week away cannot prune the dashboard.
4. Cut sections **keep probing silently and auto-restore** if their probe raises an
   exception. Cutting is demotion, never blindness.
5. `LIMEN_DIURNAL_CUT_MAX_PER_DAY` (default 1) bounds a cascade.
6. Every cut is receipted in `logs/diurnal/cuts.jsonl` and reversed by
   `python3 scripts/diurnal.py --uncut <section>`.

Fleet-wide cuts — retiring a dead producer, silencing a long-stale artifact — **never**
auto-apply. The evening names them as proposals; landing one takes a PR
(`scripts/ship-docs.sh`).

## Your own text survives

Only content between `<!-- diurnal:<phase>:start -->` and `<!-- diurnal:<phase>:end -->`
is ever rewritten (the `scripts/studium.py` never-overwrite-his-hand precedent). Anything
you type outside those markers persists across every regeneration — and a note you add to
a section is the strongest possible evidence it is *not* noop.

## Running it

```bash
export LIMEN_ROOT=/Users/4jp/Workspace/limen   # the LIVE organism, never a worktree
python3 scripts/diurnal.py --phase morning --dry-run   # render to stdout, write nothing
python3 scripts/diurnal.py --list                      # sections, streaks, cut state
python3 scripts/diurnal.py --uncut <section>           # restore a cut section
```

The organ **refuses to emit** against a root with no `logs/.voice/` — a worktree's `logs/`
holds two files where the live root's holds ~198, and reporting a false "all quiet" is
worse than emitting nothing.

On the beat it needs no invocation: sensor `diurnal` (gate `LIMEN_DIURNAL`, cadence
`LIMEN_BEAT_DIURNAL`) visits it every couple of beats, and a phase that is not yet due
exits before doing any work. Time-of-day gating is wall-clock inside the script — the
registry cadence is beat-modulo only.
