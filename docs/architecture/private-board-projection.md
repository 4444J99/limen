# Private canonical board and public aggregate projection

`organvm/limen` is public. The full task board therefore cannot be a tracked GitHub
artifact. The board contract is now additive:

- the authenticated `CONDUCT_KEEPER` Durable Object stores the canonical full board in
  a separate content-addressed chunk namespace;
- owner, client, QA, readiness, task lookup, and conduct mutation paths read that private
  board;
- GitHub `tasks.yaml` is only a public aggregate projection with counts and lifecycle
  totals and an empty `tasks` sequence;
- public status reads the aggregate projection and never needs private task material;
- local CLI dispatch may use `LIMEN_PRIVATE_TASKS` for an explicitly hydrated, off-disk
  full board. It never treats a second public branch as private custody.

## Bootstrap contract

The migration is one-way and fail-closed:

1. authenticate the compatibility principal;
2. `POST /api/board/initialize` once with the full board from private custody;
3. the keeper publishes the aggregate projection through the existing CAS publication
   branch and only then commits the private board;
4. subsequent conduct transitions publish aggregate counts after applying the event to
   the private board;
5. a missing private board returns `503` for private reads and cannot silently fall back
   to a public full board.

The public projection contains no task ID, title, repository, context, predicate, receipt,
assignment, dispatch history, or private portal budget. It is suitable for public health
surfaces and is not a dispatch source.

## Recovery

The Durable Object manifest/chunk namespace is separate from conduct state and uses the
same crash-safe manifest-switching primitive. Restore requires a private board backup or a
new authenticated bootstrap; no public repository branch is a restore source.

