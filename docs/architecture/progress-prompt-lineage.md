# Prompt/work lineage source contract

This source wraps the canonical prompt-atom authority seal and the existing
exact-ID estate reconciliation. It does not infer work from prompt wording.
Each atom remains independent, corrections retain predecessor edges, and
explicit references join atoms to task, pull-request, worktree, predicate,
supersession, blocker, and verified-outcome receipts.

The adapter refuses an exhaustive claim until the canonical prompt seal proves
exact `all/all` authority and the estate reconciliation covers the identical
set of current unresolved atom IDs. With the current partial authority seal it
does not traverse the private journal. Instead, it reports the advertised atom
denominator and zero normalized leaves as explicit coverage debt.

Full facts and raw prompt journals remain ignored/private. The tracked
projection strips prompt text, hashes atom identities, and caps its preview;
the source report still hashes and counts the full normalized leaf set.

```bash
python3 scripts/progress-prompt-lineage.py --json --write
python3 scripts/progress-prompt-lineage.py --json --write-tracked
python3 scripts/progress-prompt-lineage.py --check --json
PYTHONPATH=cli/src python3 -m pytest cli/tests/test_progress_prompt_lineage.py -q
```

The first command refreshes only ignored runtime receipts and may validly
publish `semantic_status: partial`. The second is reserved for an isolated
keeper projection branch. The terminal `--check` stays red until prompt
authority and exact estate joining are both complete.
