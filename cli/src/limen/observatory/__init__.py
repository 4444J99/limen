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

This scaffold ships the spine (config, gh, ledger, executive, doctor); the analytical
and reconcile modules are added by later build steps and picked up by the convener.
"""

from limen.observatory import config, gh, ledger, executive, doctor

__all__ = ["config", "gh", "ledger", "executive", "doctor"]
