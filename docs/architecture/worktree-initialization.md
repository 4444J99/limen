# Transactional linked-worktree initialization

Local dispatch creates each checkout through `limen.worktree_initialization.v1` instead of exposing a
partially populated final root.

1. Resolve the requested checkout ref and create a uniquely named sibling staging root.
2. Verify the staging root's exact HEAD and branch, index tree against the HEAD tree, working tree
   against the index, and absence of untracked paths.
3. Prove the staging root and final parent share a filesystem, record `state=moving`, and atomically
   rename the root into its final location.
4. Atomically repair the Git worktree backlink and repeat the full validation at the final root.
5. Publish `state=published` only after the final validation passes.

The receipt journal lives in the repository's private Git common directory, outside tracked source.
Its states are `staging`, `validated`, `moving`, `published`, and `crashed`; a crash receipt also
names its phase and typed failure code. An abrupt process death still leaves the last pre-operation
state, so recovery can distinguish an unvalidated staging root from a root moved before final
validation.

Initialization never invokes reset, clean, or recursive deletion. Any failed staging or final root,
branch, index, and working-tree content remain in place for the receipt-backed sanctioned
abandonment workflow.
