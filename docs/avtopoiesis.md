# AVTOPOIESIS

Generated: `2026-07-06T01:25:15+00:00`

## How Far

- Alive doors: `10/29` (`34.5%`).
- Mean score: `0.635`.
- Distance from ideal: `36.5%`.
- Weakest tense: `past`.
- Below-threshold doors by primary gap: `past` 14, `present` 0, `future` 5.

## Tense Averages

| Tense | Average |
|---|---:|
| `past` | `0.345` |
| `present` | `0.948` |
| `future` | `0.621` |

## Doors

| Door | Past | Present | Future | Score | State | Primary gap |
|---|---:|---:|---:|---:|---|---|
| `backup` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `feed` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `health` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `mail` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `positioning` | `0.00` | `0.50` | `0.50` | `0.330` | `nota` | `past` `1.000` |
| `report` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `balance` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `drain` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `governance` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `hygiene` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `pubpolicy` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `censor` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `continuation` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `corpus_feed` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `evocator` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `financial` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `insight_cadence` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `walls` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `web` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `heal` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `life` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `sync` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `avtopoiesis` | `1.00` | `0.50` | `1.00` | `0.835` | `alive` | `present` `0.500` |
| `nomenclator` | `1.00` | `0.50` | `1.00` | `0.835` | `alive` | `present` `0.500` |
| `contrib` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `corpus` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `cvstos` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `quicken` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `vvltvs` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |

## Largest Gaps

- `backup`: score `0.330`, primary gap `future` (`1.000`).
- `balance`: score `0.495`, primary gap `past` (`1.000`).
- `censor`: score `0.660`, primary gap `past` (`1.000`).
- `continuation`: score `0.660`, primary gap `past` (`1.000`).
- `corpus_feed`: score `0.660`, primary gap `past` (`1.000`).
- `drain`: score `0.495`, primary gap `past` (`1.000`).
- `evocator`: score `0.660`, primary gap `past` (`1.000`).
- `feed`: score `0.330`, primary gap `future` (`1.000`).
- `financial`: score `0.660`, primary gap `past` (`1.000`).
- `governance`: score `0.495`, primary gap `past` (`1.000`).

## Commands

- Audit: `python3 scripts/avtopoiesis.py`
- Machine output: `python3 scripts/avtopoiesis.py --json`
- Strict predicate: `python3 scripts/avtopoiesis.py --strict`
- Refresh this receipt: `python3 scripts/avtopoiesis.py --write`
