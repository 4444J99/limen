# Interactive work-universe view

The progress TUI is a renderer over one exact
`limen.progress-history-snapshot.v1` object. JSON, plain terminal output, and
the curses interface call the same view builder and retain the source snapshot
ID. They cannot silently compute separate progress denominators.

Run the history owner first so the TUI has durable input:

```bash
PYTHONPATH=cli/src python3 scripts/progress-history-selection.py --write
PYTHONPATH=cli/src python3 scripts/progress-tui.py
```

Non-interactive consumers can use the same snapshot:

```bash
PYTHONPATH=cli/src python3 scripts/progress-tui.py --plain --zoom leaves --debt-only
PYTHONPATH=cli/src python3 scripts/progress-tui.py --json --filter source_id=github-estate --filter terminal=false
PYTHONPATH=cli/src python3 scripts/progress-tui.py --snapshot <snapshot-id> --plain
```

Keys:

- arrows or `j`/`k`: move;
- Enter, right arrow, or `l`: zoom from macro to source/leaf/candidate and then detail;
- left arrow, `h`, or Backspace: return along the exact breadcrumb;
- `f`: enter any scalar leaf dimension as `field=value`;
- `c`: clear filters;
- `d`: toggle active-debt leaves;
- `v`: toggle verification-debt leaves;
- Space: pause/resume watch refresh;
- `r`: refresh immediately;
- `q`: exit.

The warning rail is rendered before rows at every zoom. Non-exhaustive owners,
source failures, coverage debt, unverified terminal leaves, and an unproven
zero-launch state remain visible; a progress bar never hides them. Leaf detail
shows only the normalized, private-safe history contract plus owner-configured
receipt, predicate, and evidence fields. Prompt bodies and raw private source
identities never enter the snapshot.
