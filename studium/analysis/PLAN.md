# Analysis layer — packaging the practice as data

> *"we create systems of interaction for studying and learning and trial and packaging as data
> analysis."* Every interaction the Studium generates is data; this layer packages it into a face the
> conductor can read — the professor's notebook for the book the seminar is breeding.

## The face
- [`scripts/studium-analysis.py`](../../scripts/studium-analysis.py) → `web/app/out/analysis.html`
  (mirrored to `public/`), served at `127.0.0.1:8788/analysis.html`. Same limen idiom as the daily and
  synthesis faces: data → HTML, fail-open, `_atomic_write`, meta-refresh — no network, cannot time out.

## Streams it reads (each fails open)
| Stream | Source | Live now? | View |
| --- | --- | :--: | --- |
| Authored corpus | `music/*/book-*.yaml` | ✓ | **force distribution** — the canon's centre of gravity (~51 arcs) |
| Synthesis spine | `synthesis/concepts.yaml` | ✓ | **concept reach** — works per encoding + counter-systems |
| His ledger | `ledger/*.md` + `logs/studium-state.json` | ✓ | **practice cadence** — streak, force-per-day, KEEP/REPLACE |
| Interaction events | `logs/studium-events.jsonl` | ☐ staged | **rubric trends · concept heat · claim survival** |

The first three are **real today** — the analysis face renders substance from the curriculum itself even
with zero events. The fourth populates as the seminar runs.

## The event stream
Defined in [`events-schema.yaml`](events-schema.yaml): append-only JSONL, **non-PII**, one object per
interaction (`daily_page`, `rubric_score`, `keep_replace`, `film_react`, `claim`, `trial_round`,
`attendance`). The daily face can emit `daily_page` (and the optional rubric/KEEP-REPLACE events) for the
solo practice; the trial protocol emits `claim` / `trial_round`; the rituals emit `attendance`.

## Privacy posture (hard — his gate)
- **Solo stream runs now.** His own ledger is his own data; no gate, no PII concern.
- **Community-scale collection is CONSENT-GATED.** Real participants' interactions are only ingested with
  explicit consent, and even then as **structure, never identity** — `actor` is an opaque consented id,
  never a name/handle/email, and event bodies (claim text, messages) stay out of the event log. Nothing is
  collected autonomously ([[known-owned-pervasive-then-idgaf]], [[no-never-happens-again]]).
- The point of "data analysis" here is the *aggregate*: which concepts get contested, which claims survive
  trial, which mediums move people — never surveillance of an individual.

## What this is for
The aggregate is the **dossier** behind `../community/current-inquiry.md` — the season's question answered
in data: which side keeps winning trials, where the canon's counter-systems bite hardest, which mediums
carry a force best. That dossier is the raw material the inquiry exists to produce.
