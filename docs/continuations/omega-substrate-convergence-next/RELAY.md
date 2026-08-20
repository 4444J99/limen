# Relay

The literal-substrate implementation is closed into three exact owner heads:

- Limen PR #1705 — `a8541912f1890353a358d37f3b4b7315a2a1bf8b`
- PORTVS PR #6 — `1bb241a108cbf0054f1daf7537feaa02393356b8`
- Domus PR #361 — `f56170eb28c51827d56767cd769a729ca0cb8146`

Across the three owner PRs, all 79 review threads were independently
adjudicated, replied to, and resolved, with no review debt remaining.
Exact-head remote checks are terminal green on all three owners.

Producer proof:

- Limen: 42 substrate tests, 50 focused correction/path/reaper tests, the
  38-test clone-reaper safety suite, 4,650 CLI tests, and 45 API tests passed;
  mypy, Ruff, path-contract, Python CI, 25/25 cheap scoped gates, and the
  reproducibly bootstrapped web/schema production build passed.
- PORTVS: 87 owner tests and 26 final focused tests passed; dependency lock,
  Ruff, formatting, `py_compile`, and Bash checks passed. Current plan, apply,
  and verify receipts are byte-identical across repeated runs; the historical
  four-action receipt remains separately preserved.
- Domus: 106 template checks, 22 Node tests, 334 BATS tests, and 418 Python
  tests passed, followed by 34 Home-guard and 25 implicated BATS correction
  predicates. Repeated no-apply Home receipts are byte-identical.
- Two protected Claude sessions and 466 diagram artifacts remain privately
  receipted and reconstructible.

The physical migration is not claimed complete. Its red state is owned by the
three PR receipts, Limen's migration registry, and this successor: PORTVS
records zero planned actions, 11 blockers, and 63 strict failures; Domus
records 17 planned actions, 2 protected blockers, and 22 violations; Limen
records 77 violations and zero unmeasured state. No repository or private
payload was moved, and no Home route was applied.

Human gate: Anthony reviews and merges the three owner PRs. The branches are
clean, pushed, reviewed, and mergeable; this closeout does not merge them.

Launch the next lane with:

```bash
workspace_root="${WORKSPACE_ROOT:-$HOME/Workspace}"
canonical_limen_root="${LIMEN_ROOT:-$workspace_root/library/engine/organvm/limen}"
canonical_capsule="$canonical_limen_root/.worktrees/omega-substrate-convergence-next"
legacy_capsule="$workspace_root/limen/.worktrees/omega-substrate-convergence-next"
if [[ -x "$canonical_capsule/.limen-workstream/kickstart.sh" ]]; then
  capsule_root="$canonical_capsule"
elif [[ -x "$legacy_capsule/.limen-workstream/kickstart.sh" ]]; then
  capsule_root="$legacy_capsule"
else
  printf 'Omega successor capsule is unavailable at canonical and migration paths\n' >&2
  exit 1
fi
cd "$capsule_root" && bash .limen-workstream/kickstart.sh
```

`producer-closeout.json` and `verify-producer-closeout.py` are the executable
producer fixed-point receipt.
