# AVTOPOIESIS

Generated: `2026-07-06T06:10:58+00:00`

## How Far

- Alive doors: `18/29` (`62.1%`).
- Mean score: `0.729`.
- Distance from ideal: `27.1%`.
- Weakest tense: `future`.
- Present tense source: `logs/organ-health.json` when available; heartbeat wiring fallback otherwise.
- Below-threshold doors by primary gap: `past` 7, `present` 0, `future` 4.

## Tense Averages

| Tense | Average |
|---|---:|
| `past` | `0.621` |
| `present` | `0.948` |
| `future` | `0.621` |

## Doors

| Door | Past | Present | Future | Score | State | Primary gap |
|---|---:|---:|---:|---:|---|---|
| `feed` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `mail` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `positioning` | `0.00` | `0.50` | `0.50` | `0.330` | `nota` | `past` `1.000` |
| `report` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `sync` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `drain` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `pubpolicy` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `censor` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `continuation` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `evocator` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `walls` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `backup` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `heal` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `health` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `life` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `avtopoiesis` | `1.00` | `0.50` | `1.00` | `0.835` | `alive` | `present` `0.500` |
| `balance` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `governance` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `hygiene` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `nomenclator` | `1.00` | `0.50` | `1.00` | `0.835` | `alive` | `present` `0.500` |
| `contrib` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `corpus` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `corpus_feed` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `cvstos` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `financial` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `insight_cadence` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `quicken` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `vvltvs` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `web` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |

## Largest Gaps

- `censor`: score `0.660`, primary gap `past` (`1.000`).
- `continuation`: score `0.660`, primary gap `past` (`1.000`).
- `drain`: score `0.495`, primary gap `past` (`1.000`).
- `evocator`: score `0.660`, primary gap `past` (`1.000`).
- `feed`: score `0.330`, primary gap `future` (`1.000`).
- `mail`: score `0.330`, primary gap `future` (`1.000`).
- `positioning`: score `0.330`, primary gap `past` (`1.000`).
- `pubpolicy`: score `0.495`, primary gap `past` (`1.000`).
- `report`: score `0.330`, primary gap `future` (`1.000`).
- `sync`: score `0.330`, primary gap `future` (`1.000`).

## Commands

- Audit: `python3 scripts/avtopoiesis.py`
- Machine output: `python3 scripts/avtopoiesis.py --json`
- Strict predicate: `python3 scripts/avtopoiesis.py --strict`
- Refresh this receipt: `python3 scripts/avtopoiesis.py --write`
