"""VIGILIA — the autonomic executive (the missing hands).

The somatic system (the ``limen`` daemon, its arms, dispatch) is mature; the
*autonomic* system — the layer that keeps the computer itself alive while the
body works — was absent. Three faults in 18h on 2026-06-25, all one disease:

  * VITALS     — 08:47 kernel panic (memory livelock). Diagnosed, no hand.
  * CONTINUITY — ~13:42 a session thread handed off as a 200-char stub.
  * INTEGRITY  — a "Claude app is corrupt" dialog (autoupdater/signature churn).

Each had a diagnosis and a lever on file; none had a *hand*. This package is the
hand: three small, fail-open organs that ride the already-resident heartbeat
(no new resident process — separation of powers: EXECUTE rides the beat).

Every threshold is a declared parameter in ``institutio/governance/parameters.yaml``
(read via :mod:`limen.vigilia.params`). Federation, not fusion: these organs are
indexed in ``institutio/registry/organs.yaml``, not merged into a pile.
"""

from limen.vigilia import continuity, executive, integrity, params, vitals

__all__ = ["continuity", "executive", "integrity", "params", "vitals"]
