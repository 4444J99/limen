# BIFRONS — the star ↔ contribution portal

> Janus, two-faced: every starred repo is both **absorbed** (inbound) and **contributed-to**
> (outbound); one `exchange_id` threads the traversal. Rendered by `scripts/bifrons-organ.py`
> from the shared portal store. **Nothing here sends** — the one external write (an upstream
> PR) is the human's hand, riding the existing outbound-send valve, never a BIFRONS lever.

## Absorption (inbound)

| stars | dossiers | resonance edges | transmutation proposals |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |

## Exchange lifecycle

_No exchanges yet — the portal store is empty or unreachable (honest dust)._

## The human gate (a valve, not a wall)

- **0** contribution(s) prepared and pooling at the gate (`PATCH_PREPARED`/`HUMAN_APPROVED`).
- **0** backflow signal(s) metabolized through the seven organs.
- The autonomous loop runs to `HUMAN_APPROVED`; only the upstream PR is his hand.

## Proof of life

- Portal store: `absent` (`~/.organvm/bifrons/portal.db`).
- Engine loop: `organvm portal metabolize` (bounded, idempotent, never submits).
- Outbound feeds SPECVLVM + `organvm/contrib/LEDGER.yaml` `source: starred` — not a rebuild.
