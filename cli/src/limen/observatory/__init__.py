"""OBSERVATORY — GITVS's legibility twin.

GITVS runs ``observe → diff → reconcile`` on the estate's *configuration* (drift = ∅).
OBSERVATORY runs the same loop on the estate's **legibility & traction** — how the
world understands, trusts, uses, and circulates the estate — in the standard organ
two faces:

  * micro (internal legibility): are our own public numbers true & coherent?
    Sensor VVLTVS + ``face-ownership.json`` already exist; this organ supplies the
    missing reconcile *effector*.
  * macro (external legibility): why do comparable winners get adopted and we don't?
    A matched-cohort mechanism study that yields one reversible activation experiment.

Both faces write ONE append-only evidence store (``logs/observatory/*.jsonl``) and feed
ONE daily experiment selector; the experiment is always emitted as a human-gated
*proposal* (a lever + a task), never auto-applied to a public surface.

The full loop ships here: the spine (config, gh, ledger, executive, doctor), the
internal-legibility ``reconcile`` effector, the external-legibility research loop
(surface, collect, cohort, mechanism, estate), and the unified ``brief`` + ``lever``
(experiment selector + human-gated proposal). Beat wiring is the last build step.
"""

from limen.observatory import (
    config,
    gh,
    ledger,
    executive,
    doctor,
    reconcile,
    surface,
    collect,
    cohort,
    mechanism,
    estate,
    lever,
    brief,
)

__all__ = [
    "config",
    "gh",
    "ledger",
    "executive",
    "doctor",
    "reconcile",
    "surface",
    "collect",
    "cohort",
    "mechanism",
    "estate",
    "lever",
    "brief",
]
