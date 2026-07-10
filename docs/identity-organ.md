# Core-Identity Organ

The SSOT for the operator's **durable personal atoms** — legal name, date of birth, SSN,
mailing/home address, phone. Sibling of the [credential organ](../scripts/creds-hydrate.py):
credentials *rotate*, identity atoms *don't*, so they get separate homes, not one blob.

Built because a form-fill (`phi.pdf`, a HIPAA records request) surfaced that **the fact we had to
ask** for a DOB was the signal of a missing organ — per the charter's *build-the-organ-not-the-one-off*
law. Now "recreate this form with my info" is solved once for **every** form (SSA, bankruptcy,
housing, tax…): each is a consumer of this store.

## Two homes (both encrypted, neither in chat)

| Home | Role |
|------|------|
| `op://Private/Identity` (1Password) | **Live upstream** — source of truth when reachable |
| `~/Workspace/_life-private/identity.json` | **Offline mirror** — ARCA-sealed at rest (glob `_*-private` → `organvm/arca`, AES-256-CBC / PBKDF2-200k, key in Keychain), mode-700 dir, authoritative when `op` is down |

The atoms are **never recited in chat**. `identity.py` redacts SSN (`***-**-1234`) by default;
only a form-filler passes `--unsafe-ssn`, and only into a document the operator controls.

## Portal (`scripts/identity.py`)

```
identity.py get legal_name.first     # one atom
identity.py show                     # human view, SSN redacted
identity.py json [--unsafe-ssn]      # full record for a consumer
identity.py verify                   # PREDICATE: exit 0 iff required atoms present & valid
identity.py hydrate                  # pull op://Private/Identity -> mirror (op must be reachable)
```

`verify` is the "is it populated?" gate — exit 1 lists exactly the missing atoms. Schema:
`scripts/identity.schema.json`.

## Consuming it (form-fillers)

`scripts/fill-phi-jewishboard.py OUT.pdf [--draft]` recreates the Jewish Board PHI form from the
store (the source is a flat scan with no fillable fields, so we rebuild the layout and render via
Chrome headless). Any atom the store lacks renders as a blank to hand-write; once
`identity.py verify` exits 0, the PDF is complete. New forms follow the same shape: read
`identity.py json`, map atoms, render.

## Populating once

The mirror ships with name + emails seeded and the sensitive atoms (DOB, SSN, address, phone)
empty. Populate them **once**, then every form fills automatically:

1. **From 1Password** — enable the CLI desktop integration (1Password → Settings → Developer →
   *Integrate with 1Password CLI*), create/confirm an `Identity` item under Private, then
   `identity.py hydrate`.
2. **One-time entry** — edit `~/Workspace/_life-private/identity.json` (or hand the atoms to the
   session once); ARCA re-seals on the next beat.
