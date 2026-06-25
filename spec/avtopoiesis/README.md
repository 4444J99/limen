# AVTOPOIESIS — the law that each door must be alive in its own existence

*Autopoiesis* (αὐτο-ποίησις, "self-making") is a system that continuously produces and maintains
the components that produce it. This institution turns that into the estate's **definition of done**:
a pillar or door is not finished when it ships — it is finished when it is **alive and self-keeping**.
At civilizational scale for a single person, the binding constraint is his attention, so the only way
the arithmetic closes is if every door runs itself. Autopoiesis is therefore not an aesthetic; it is
the load-bearing requirement.

## The three tenses of aliveness

A door is alive to the degree it holds all three at once:

| Tense | Question | Sensed by |
|---|---|---|
| **Past** | does it metabolize its own history? | its source regenerates state from the estate (a crawl/census), not a hand-fed input |
| **Present** | does it run unbidden? | wired to a heartbeat beat and not gated dormant |
| **Future** | does it self-evolve and ask less? | it carries no open his-hand lever of its own |

A door alive in all three needs nothing from his hand.

## NOT A SOLID — the law applied to its own encoding

The obvious way to enforce this — a committed scorecard, a hand-curated roster, a `done.sh` with a
hardcoded door-list — would itself be inert (no past, no future) and so would **fail its own test**.
So the gate (`scripts/avtopoiesis.py`) is built to stay liquid:

1. **It discovers its subjects.** The door-list is read from the living heartbeat (`discovery.source`
   in `canon.yaml`) every run — every `C_<NAME>` beat is a door. A new beat is audited automatically;
   nothing is typed into a roster.
2. **It derives its criteria** from `canon.yaml` (weights, threshold, senses). Retune a rule there and
   the gate follows — derive-never-pin, the same contract as NOMENCLATOR's `canon.yaml`.
3. **It regenerates its verdict** on every invocation. The scorecard is computed, never stored — there
   is no file-of-record to rot.
4. **It includes itself.** AVTOPOIESIS has its own heartbeat beat (`C_AVTOPOIESIS`, gated OFF by
   default), so it is discovered like any other door and judged by its own law — operational closure,
   the Maturana/Varela signature.

And liquid in time: `canon.yaml` carries its own `gaps_remaining`, and the gate reports
**distance-from-ideal** per tense, never a frozen pass/fail. The ideal form is approached, not reached.

## Using it

```
python3 scripts/avtopoiesis.py            # AUDIT — score every door, report distance-from-ideal
python3 scripts/avtopoiesis.py --strict   # PREDICATE — exit 1 if any door is below the alive threshold
python3 scripts/avtopoiesis.py --json     # machine form (organ-health / dashboards)
```

`--strict` is the aspiration predicate ("is the whole estate alive yet?") — it is honestly **non-zero
today**, and is intentionally *not* wired as a blocking CI gate. The durable in-CI predicate is
`cli/tests/test_avtopoiesis.py`, which proves the gate itself stays liquid.

## How a door earns its past tense — worked example (NAMING)

The first door made to pass was INDEX·NOMINVM. NOMENCLATOR validated a *hand-fed* `roll.yaml`, so its
past-tense scored `0.00`. Adding `nomenclator --census` — which crawls the living estate (the `spec/`
institutions and the heartbeat organs), derives each canon form, and reports drift — gave it a
**metabolize limb**: the roll now takes itself from the estate instead of being fed. Its past-tense
flipped to `1.00`. (Its present and future remain partial — it is gated by your knob and still owns one
lever — which the gate reports honestly rather than rounding up.)

## Where it is wired

- **Heartbeat organ** — `C_AVTOPOIESIS` in `scripts/heartbeat-loop.sh`, gated OFF by default
  (`LIMEN_AVTOPOIESIS=1` is your knob), mirroring the NOMENCLATOR beat.
- **Canon** — `spec/avtopoiesis/canon.yaml` (the tunable rubric; the single source the gate reads).
- **Predicate** — `cli/tests/test_avtopoiesis.py` (in the `pr-gate` pytest run).

## Gaps remaining (recorded, not hidden — a liquid law names its own incompleteness)

Tracked in `canon.yaml#gaps_remaining`. The largest: `organ-health.py`'s `_registry()` is still a
hand-roster that can drift from the heartbeat — the next convergence is to derive *its* door-list from
the same `discovery.source`, so there is one living door-list, not two.
