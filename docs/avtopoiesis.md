# AVTOPOIESIS

Generated: `2026-07-06T07:29:00+00:00`

## How Far

- Alive doors: `18/29` (`62.1%`).
- Mean score: `0.769`.
- Distance from ideal: `23.1%`.
- Weakest tense: `past`.
- Present tense source: `logs/organ-health.json` when available; heartbeat wiring fallback otherwise.
- Below-threshold doors by primary gap: `past` 10, `present` 0, `future` 1.

## Tense Averages

| Tense | Average |
|---|---:|
| `past` | `0.621` |
| `present` | `0.948` |
| `future` | `0.741` |

## Doors

| Door | Past | Present | Future | Score | State | Primary gap |
|---|---:|---:|---:|---:|---|---|
| `mail` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `positioning` | `0.00` | `0.50` | `0.50` | `0.330` | `nota` | `past` `1.000` |
| `feed` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `pubpolicy` | `0.00` | `1.00` | `0.50` | `0.495` | `nota` | `past` `1.000` |
| `censor` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `continuation` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `drain` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `evocator` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `report` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `sync` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `walls` | `0.00` | `1.00` | `1.00` | `0.660` | `nota` | `past` `1.000` |
| `backup` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `health` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `life` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `avtopoiesis` | `1.00` | `0.50` | `1.00` | `0.835` | `alive` | `present` `0.500` |
| `balance` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `governance` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `heal` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
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
- `drain`: score `0.660`, primary gap `past` (`1.000`).
- `evocator`: score `0.660`, primary gap `past` (`1.000`).
- `feed`: score `0.495`, primary gap `past` (`1.000`).
- `mail`: score `0.330`, primary gap `future` (`1.000`).
- `positioning`: score `0.330`, primary gap `past` (`1.000`).
- `pubpolicy`: score `0.495`, primary gap `past` (`1.000`).
- `report`: score `0.660`, primary gap `past` (`1.000`).
- `sync`: score `0.660`, primary gap `past` (`1.000`).

## Evidence

Evidence is redacted metadata only: paths, configured signatures, liveness status, and counts.

| Door | Past evidence | Present evidence | Future evidence |
|---|---|---|---|
| `mail` | missing metabolize signature in mail-beat.sh | logs/organ-health.json:green | 2 open his-hand levers from his-hand-levers.json |
| `positioning` | missing metabolize signature in generate-positioning.py | logs/organ-health.json:gated | 1 open his-hand levers from his-hand-levers.json |
| `feed` | missing metabolize signature in mine-backlog.py, generate-revenue-backlog.py, generate-organ-backlog.py | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `pubpolicy` | missing metabolize signature in publication-policy.py | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `censor` | missing metabolize signature in censor.py, sync-censor-issues.py, censor-view.py | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `continuation` | missing metabolize signature in continuation-beat.py | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `drain` | missing metabolize signature in drain.sh | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `evocator` | missing metabolize signature in evocator.py | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `report` | missing metabolize signature in conducting-report.py | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `sync` | missing metabolize signature in sync-release.sh, sync-censor-issues.py, sync-hishand-issues.py | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `walls` | missing metabolize signature in credential-wall.py, sync-hishand-issues.py | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `backup` | matched library-preserve.py:os.walk( | heartbeat-wiring:wired | 3 open his-hand levers from his-hand-levers.json |
| `health` | matched health-organ.py:.glob( | logs/organ-health.json:green | 4 open his-hand levers from his-hand-levers.json |
| `life` | matched life-organ.py:def census | logs/organ-health.json:green | 3 open his-hand levers from his-hand-levers.json |
| `avtopoiesis` | matched avtopoiesis.py:.glob( | logs/organ-health.json:gated | 0 open his-hand levers from his-hand-levers.json |
| `balance` | matched route.py:.glob( | heartbeat-wiring:wired | 1 open his-hand levers from his-hand-levers.json |
| `governance` | matched governance-organ.py:.glob( | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `heal` | matched verify-dispatch.py:.glob(; health-organ.py:.glob(; heal-board.py:.glob( | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `hygiene` | matched clone-maintenance.sh:os.walk(,.glob(,glob.glob | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `nomenclator` | matched nomenclator.py:.iterdir(,--census,def census | logs/organ-health.json:gated | 0 open his-hand levers from his-hand-levers.json |
| `contrib` | matched contributions-organ.py:.iterdir( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `corpus` | matched corpus-feed.py:rglob(; corpus-converge.py:rglob(,.glob(; media-atomize.py:os.walk(,.glob( | heartbeat-wiring:wired | 0 open his-hand levers from his-hand-levers.json |
| `corpus_feed` | matched corpus-feed.py:rglob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `cvstos` | matched cvstos-organ.py:.iterdir(,.glob(,def census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `financial` | matched financial-organ.py:rglob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `insight_cadence` | matched insight-route.py:.glob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `quicken` | matched quicken.py:.glob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `vvltvs` | matched vvltvs-organ.py:rglob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `web` | matched usage-telemetry.py:rglob(; codex-token-accounting.py:rglob(; claude-usage.py:.glob(,glob.glob | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |

## Commands

- Audit: `python3 scripts/avtopoiesis.py`
- Machine output: `python3 scripts/avtopoiesis.py --json`
- Strict predicate: `python3 scripts/avtopoiesis.py --strict`
- Refresh this receipt: `python3 scripts/avtopoiesis.py --write`
