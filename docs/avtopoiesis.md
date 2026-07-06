# AVTOPOIESIS

Generated: `2026-07-06T07:51:55+00:00`

## How Far

- Alive doors: `27/29` (`93.1%`).
- Mean score: `0.874`.
- Distance from ideal: `12.6%`.
- Weakest tense: `future`.
- Present tense source: `logs/organ-health.json` when available; heartbeat wiring fallback otherwise.
- Below-threshold doors by primary gap: `past` 1, `present` 0, `future` 1.

## Tense Averages

| Tense | Average |
|---|---:|
| `past` | `0.931` |
| `present` | `0.948` |
| `future` | `0.741` |

## Doors

| Door | Past | Present | Future | Score | State | Primary gap |
|---|---:|---:|---:|---:|---|---|
| `mail` | `0.00` | `1.00` | `0.00` | `0.330` | `nota` | `future` `1.000` |
| `positioning` | `0.00` | `0.50` | `0.50` | `0.330` | `nota` | `past` `1.000` |
| `backup` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `health` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `life` | `1.00` | `1.00` | `0.00` | `0.670` | `alive` | `future` `1.000` |
| `avtopoiesis` | `1.00` | `0.50` | `1.00` | `0.835` | `alive` | `present` `0.500` |
| `balance` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `feed` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `governance` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `heal` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `hygiene` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `nomenclator` | `1.00` | `0.50` | `1.00` | `0.835` | `alive` | `present` `0.500` |
| `pubpolicy` | `1.00` | `1.00` | `0.50` | `0.835` | `alive` | `future` `0.500` |
| `censor` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `continuation` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `contrib` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `corpus` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `corpus_feed` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `cvstos` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `drain` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `evocator` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `financial` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `insight_cadence` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `quicken` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `report` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `sync` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `vvltvs` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `walls` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |
| `web` | `1.00` | `1.00` | `1.00` | `1.000` | `alive` | `future` `0.000` |

## Largest Gaps

- `mail`: score `0.330`, primary gap `future` (`1.000`).
- `positioning`: score `0.330`, primary gap `past` (`1.000`).

## Evidence

Evidence is redacted metadata only: paths, configured signatures, liveness status, and counts.

| Door | Past evidence | Present evidence | Future evidence |
|---|---|---|---|
| `mail` | missing metabolize signature in mail-beat.sh | logs/organ-health.json:green | 2 open his-hand levers from his-hand-levers.json |
| `positioning` | missing metabolize signature in generate-positioning.py | logs/organ-health.json:gated | 1 open his-hand levers from his-hand-levers.json |
| `backup` | matched library-preserve.py:os.walk( | heartbeat-wiring:wired | 3 open his-hand levers from his-hand-levers.json |
| `health` | matched health-organ.py:.glob( | logs/organ-health.json:green | 4 open his-hand levers from his-hand-levers.json |
| `life` | matched life-organ.py:def census | logs/organ-health.json:green | 3 open his-hand levers from his-hand-levers.json |
| `avtopoiesis` | matched avtopoiesis.py:.glob( | logs/organ-health.json:gated | 0 open his-hand levers from his-hand-levers.json |
| `balance` | matched route.py:.glob( | heartbeat-wiring:wired | 1 open his-hand levers from his-hand-levers.json |
| `feed` | matched generate-backlog.py:--census,def census | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `governance` | matched governance-organ.py:.glob( | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `heal` | matched verify-dispatch.py:.glob(; health-organ.py:.glob(; heal-board.py:.glob( | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `hygiene` | matched clone-maintenance.sh:os.walk(,.glob(,glob.glob | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `nomenclator` | matched nomenclator.py:.iterdir(,--census,def census | logs/organ-health.json:gated | 0 open his-hand levers from his-hand-levers.json |
| `pubpolicy` | matched publication-policy.py:--census,def census | logs/organ-health.json:green | 1 open his-hand levers from his-hand-levers.json |
| `censor` | matched censor.py:--census,def census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `continuation` | matched continuation-beat.py:--census,def census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `contrib` | matched contributions-organ.py:.iterdir( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `corpus` | matched corpus-feed.py:rglob(; corpus-converge.py:rglob(,.glob(; media-atomize.py:os.walk(,.glob( | heartbeat-wiring:wired | 0 open his-hand levers from his-hand-levers.json |
| `corpus_feed` | matched corpus-feed.py:rglob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `cvstos` | matched cvstos-organ.py:.iterdir(,.glob(,def census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `drain` | matched drain.sh:--census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `evocator` | matched evocator.py:--census,def census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `financial` | matched financial-organ.py:rglob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `insight_cadence` | matched insight-route.py:.glob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `quicken` | matched quicken.py:.glob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `report` | matched conducting-report.py:--census,def census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `sync` | matched sync-release.sh:--census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `vvltvs` | matched vvltvs-organ.py:rglob( | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `walls` | matched credential-wall.py:--census,def census | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |
| `web` | matched usage-telemetry.py:rglob(; codex-token-accounting.py:rglob(; claude-usage.py:.glob(,glob.glob | logs/organ-health.json:green | 0 open his-hand levers from his-hand-levers.json |

## Commands

- Audit: `python3 scripts/avtopoiesis.py`
- Machine output: `python3 scripts/avtopoiesis.py --json`
- Strict predicate: `python3 scripts/avtopoiesis.py --strict`
- Refresh this receipt: `python3 scripts/avtopoiesis.py --write`
