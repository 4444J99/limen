#!/usr/bin/env bash
# Shared interpreter resolver for the gate rail (verify-scoped.sh, merge-policy.sh).
#
# Source this file and call `limen_gate_python`; it prints ONE absolute interpreter path that can
# `import yaml` and returns 0, or prints the install hint on stderr and returns 1. The gate scripts
# (`scripts/check-*.py`, verify.py, the deploy-regex derivation) all import PyYAML, but a bare
# `python3` is whatever the caller's PATH happens to put first — on this host an agent shell resolves
# Homebrew's newest python (no PyYAML) while a Terminal resolves one that has it. Resolving once, here,
# makes the rail independent of the caller's PATH instead of patching each caller's PATH.
#
# Resolution order:
#   1. $LIMEN_GATE_PYTHON — an explicit override; used when it can import yaml (a broken one warns and
#      is skipped, never trusted).
#   2. Every PATH hit (not just the first — a shadowed interpreter is still a candidate) of each name in
#      $LIMEN_GATE_PYTHON_CANDIDATES (default: python3.13 python3 python3.12 python3.14 python3.11):
#      the first with the FULL gate toolchain (yaml + pytest + ruff, i.e. `pip install -e 'cli[test]'`)
#      wins, because the lint/test gates run `python3 -m ruff` / `-m pytest`; failing that, the first
#      that can import yaml alone (the check-*.py and merge-policy paths still work; the ruff/pytest
#      gates then fail with their own install hint).
#
# Nothing is installed and no shell config is touched; an unresolved rail fails loudly, never with a
# bare ModuleNotFoundError traceback.

limen_gate_python_has() { # interpreter, import-statement
  "$1" -c "$2" >/dev/null 2>&1
}

limen_gate_python() {
  local candidates="${LIMEN_GATE_PYTHON_CANDIDATES:-python3.13 python3 python3.12 python3.14 python3.11}"
  local name hit tried="" yaml_only=""

  if [[ -n "${LIMEN_GATE_PYTHON:-}" ]]; then
    if limen_gate_python_has "$LIMEN_GATE_PYTHON" 'import yaml'; then
      printf '%s\n' "$LIMEN_GATE_PYTHON"
      return 0
    fi
    echo "gate-python: LIMEN_GATE_PYTHON=$LIMEN_GATE_PYTHON cannot import yaml; ignoring it and searching PATH." >&2
    tried="$LIMEN_GATE_PYTHON "
  fi

  for name in $candidates; do
    while IFS= read -r hit; do
      [[ -n "$hit" ]] || continue
      if limen_gate_python_has "$hit" 'import yaml, pytest, ruff'; then
        printf '%s\n' "$hit"
        return 0
      fi
      if [[ -z "$yaml_only" ]] && limen_gate_python_has "$hit" 'import yaml'; then
        yaml_only="$hit"
      else
        tried="$tried$hit "
      fi
    done < <(type -ap "$name" 2>/dev/null || true)
  done

  if [[ -n "$yaml_only" ]]; then
    echo "gate-python: using $yaml_only (PyYAML only — no interpreter on PATH has pytest+ruff; the lint/test gates will say so: pip install -e 'cli[test]')." >&2
    printf '%s\n' "$yaml_only"
    return 0
  fi

  {
    echo "gate-python: no interpreter on PATH can import PyYAML — the gate rail cannot run."
    echo "  tried: ${tried:-<no candidate found on PATH: $candidates>}"
    echo "  fix:   install PyYAML for one of them, e.g.  python3.13 -m pip install PyYAML"
    echo "         (a Homebrew python needs a venv or --break-system-packages: PEP 668), or point the rail at one"
    echo "         that has it:  export LIMEN_GATE_PYTHON=/path/to/python"
  } >&2
  return 1
}
