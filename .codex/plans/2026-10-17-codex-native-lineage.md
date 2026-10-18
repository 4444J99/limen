# Codex native lineage compatibility

## Objective

Allow Codex child-thread session metadata that declares `thread_spawn.parent_thread_id` but omits `forked_from_id`, while retaining strict recursive parent existence and same-session validation.

## Evidence

Codex 0.163.0 emitted a child header whose session ID matched its live `CODEX_SESSION_ID` and declared parent, with a matching root header; `forked_from_id` was absent. The observer rejected it as `native_ancestry_invalid`.

## Steps

1. Add a regression for the observed child/root header shape and prove it fails.
2. Relax only the `transcript_witness` check to allow absent `forked_from_id` when parent is explicit; retain rejection when a supplied fork ID conflicts.
3. Run focused ownership tests and the implicated scoped source gate.
4. Commit and push the plan, then commit and push the fix on `fix/codex-native-lineage-20261017`; open a PR. Do not merge or install the runtime.

## Acceptance

Observed valid lineage passes; conflicting fork ID, missing parent, absent parent header, and cross-session parent remain rejected. Focused tests and scoped gate pass.
