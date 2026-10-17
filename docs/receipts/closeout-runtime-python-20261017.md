# Installed closeout interpreter correction

The a9010316 runtime admitted the real canonical checker command through native
PreToolUse. The command then failed importing rfc8785 because the shell wrapper
used ambient python3 instead of the installed runtime environment. The guard fix
is observed at runtime; successful closeout is not established.

The wrapper now selects its owning runtime's Python when invoked from the
installed source layout with its receipt and executable present. Source checkout
and no-argument estate behavior remain unchanged. A poisoned-PATH regression
failed with exit 99 before the repair, then passed using the full runtime venv.
Its first corrected fixture linked only a Python binary and lost venv discovery;
linking the whole fixture environment corrected that fixture error. One test
passed in 0.16 seconds. Ruff formatting passed; source checks are separate.

Native observation inspection found 512 retained events, all with unknown client
surface. No qualified per-surface cohort or 24-hour observation is claimed. Domus
issue #487 owns the existing native acceptance and evidence lineage. Do not
relabel old events or infer client identity from the provider label.
