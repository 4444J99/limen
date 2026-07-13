# BIFRONS — Micro face (the operator's own instance)

**Anthony's 419 stars, made into a living two-way portal.**

- **The estate:** `4444J99`'s 419 starred repos, synced idempotently via `gh api user/starred`
  (`starred_at` preserved) into the shared portal store `~/.organvm/bifrons/portal.db`.
- **Inbound:** each active public star gets a provenance-pinned S1 dossier (license + README +
  manifests + contribution files, each artifact hashed, code never executed); dossiers compile to
  resonance edges against the ORGANVM repos; high-resonance stars become draft internal transmutation
  PRs — never a default-branch write.
- **Outbound:** evidence-bearing stars become prepared contribution packets that **feed the existing
  SPECVLVM mirror + `organvm/contrib/LEDGER.yaml` `source: starred`** — not a parallel pipeline. The
  three merged upstream PRs SPECVLVM already tracks are the proof the outbound rail works.
- **The gate:** opening any upstream PR rides the same outbound-send valve every other organ defers
  to ("the send / the signature" — his hand). BIFRONS files **no lever of its own**.
- **Aliveness:** the `bifrons-portal` heartbeat sensor runs `scripts/bifrons-organ.py` on its cadence
  — absorb new stars, map, prepare, re-render `PORTAL.md`. It reads its own past each beat, runs
  unbidden, and asks nothing. `avtopoiesis.py --strict` counts it a live door.

Provenance: the ChatGPT "Alchemical GitHub Portal" design, realized as connective tissue across
`alchemia-ingestvm` (#11), `organvm-ontologia` (#17), `organvm-engine` (#166 + #167), and `limen`
(#944 name). Named BIFRONS to resolve the IANVA collision (INDEX·NOMINVM).
