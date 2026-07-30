# Session atom streaming

Limen consumes session-meta atoms through `limen.session_atoms`. The adapter
derives the owner root from `LIMEN_SESSION_META` and selects
`ingest/atoms-store/CURRENT` by default.

Selection is fail-closed:

- Any present `CURRENT` or `generations/` marker is v2 state. Limen delegates
  validation and ordered iteration to session-meta's `atoms_store.py`.
- Corrupt, incomplete, or unreadable v2 state raises an error. Limen never
  hides that condition by opening a legacy file.
- V1 JSONL is available for one release only when `LIMEN_EXPORT_ATOMS`
  explicitly names it and no v2 state exists. An implicit
  `ingest/atoms.jsonl` is not a source.

`corpus-feed.py` publishes v2 in its direct-atomizer fallback and verifies the
selected stream before reporting success. `corpus-converge.py` keeps only its
bounded newest candidate heap while iterating. `session-corpus-ledger.py`
counts the selected stream without loading the collection into memory.

These readers do not migrate, copy, delete, or rewrite a live atom store.
