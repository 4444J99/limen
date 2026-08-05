#!/usr/bin/env bash
# PreToolUse(Bash) hook: pytest-scope-guard — deny FULL-SUITE pytest outside verify.py.
#
# WHY: the charter (CLAUDE.md § Worktree Isolation & CI Gate Matrix) makes scoped
# verification the default gate — "a docs append must never pay for 1,200+ tests" — but the
# rule was prose-only: allow-trusted-cd-git.sh auto-approves pytest as trusted read-only.
# 2026-07-15 incident: one fleet session ran `cd cli && uv run python -m pytest tests/ -q`
# TWICE concurrently while Backblaze re-crawled post-reboot; the 16 GB host thrashed
# (swap 6.4/7.2 GiB, load 5.7). A direct full-suite run also bypasses verify.py's tier
# ordering, its env-scrub (`env -u LIMEN_API_TOKEN …`, gates.yaml pytest-cli), and the
# serialized-tier flock — so the deny is unconditional, not a serialize: flock-serializing
# a law violation would legitimize it.
#
# SCOPE — the deny is deliberately narrow (never false-positive-block a legitimate lane):
#   DENY only: a pytest invocation at command position whose EFFECTIVE directory sits in a
#     limen checkout (live root OR any worktree — detected by walking up to a dir holding
#     scripts/verify-scoped.sh, i.e. exactly where the lawful lane exists) AND whose path
#     args are all suite roots (tests/, cli/tests, web/api/tests) — or absent entirely
#     while the cwd is a suite parent. Directory + `-k expr` is still a full collection:
#     the collection cost is the harm — DENY.
#   PASS silently everything else: any file-component arg (.py / ::node), suite
#     SUBdirectories, other repos (no verify-scoped.sh above them), the verify wrappers
#     themselves (verify.py / verify-scoped.sh / verify-whole.sh in the command — they own
#     tiering + serialization), and EVERY parse failure. Heredocs and nested `bash -c`
#     are structurally invisible — the pytest-scope audit in claude-workflow-guard.py
#     (SessionEnd) is the backstop, matching the worktree-guard's daemon-lane precedent.
#
# Fail-open by construction: uncertainty exits 0 with no output. The hook never emits
# "allow", so it cannot widen the permission surface. Escape hatch: LIMEN_ALLOW_FULL_PYTEST=1
# (mirrors LIMEN_ALLOW_LIVE_COMMIT / LIMEN_ALLOW_OPUS_FANOUT; declared in parameters.yaml).
set -u

# Consume stdin FIRST, unconditionally — an early exit that leaves the payload
# writer facing a closed pipe turns into a BrokenPipeError upstream.
input="$(cat)"

[ "${LIMEN_ALLOW_FULL_PYTEST:-0}" = "1" ] && exit 0

# Cheap prefilter: almost every Bash call carries no pytest token — bail in O(1), no fork.
case "$input" in
  *pytest*) : ;;
  *) exit 0 ;;
esac

# The lawful lanes run pytest themselves — never second-guess them.
case "$input" in
  *verify.py*|*verify-scoped.sh*|*verify-whole.sh*) exit 0 ;;
esac

command -v python3 >/dev/null 2>&1 || exit 0

verdict="$(printf '%s' "$input" | python3 -c '
import json, os, re, shlex, sys

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cmd = (d.get("tool_input") or {}).get("command") or ""
cwd = d.get("cwd") or os.getcwd()

# pytest at command position, in any of its shapes:
#   pytest / .venv/bin/pytest / python[3[.x]] -m pytest / uv run [python -m] pytest,
# optionally behind `env VAR=… -u VAR …` or bare VAR=… assignments.
PYTEST = re.compile(
    r"(?:^|[;&|(]\s*|`\s*)\s*(?:command\s+)?"
    r"(?:env\s+(?:-u\s+\S+\s+|[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*"
    r"(?:uv\s+run\s+(?:--\S+\s+)*)?"
    r"(?:\S*python3?(?:\.\d+)?\s+-m\s+)?"
    r"(?:\S*/)?pytest\b")

# Args end at the first shell separator or redirection after the pytest token.
STOP = re.compile(r"\d*>|<|;|\||&")

# Flags that consume the next token when written space-separated.
VALUE_FLAGS = {"-k", "-m", "-p", "-o", "-W", "-c", "-n", "--tb", "--maxfail",
               "--durations", "--ignore", "--deselect", "--rootdir", "--confcutdir"}

def effective_dir(head):
    """Last cd clause before the pytest token, else the session cwd."""
    cds = re.findall(r"(?:^|[;&|]\s*)\s*cd\s+(\"[^\"]+\"|\x27[^\x27]+\x27|[^\s;&|]+)", head)
    if not cds:
        return cwd
    t = cds[-1]
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"\x27":
        t = t[1:-1]
    t = os.path.expanduser(t)
    if "$" in t:
        return None                                   # unresolved variable — cannot place
    return t if os.path.isabs(t) else os.path.join(cwd, t)

def checkout_root(path):
    """Walk up to the limen checkout containing path — the dir where the lawful
    scoped lane (scripts/verify-scoped.sh) exists. None ⇒ not this guard\x27s lane."""
    p = os.path.realpath(path)
    while True:
        if os.path.isfile(os.path.join(p, "scripts", "verify-scoped.sh")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent

for m in PYTEST.finditer(cmd):
    tail = cmd[m.end():]
    stop = STOP.search(tail)
    if stop:
        tail = tail[: stop.start()]
    try:
        tokens = shlex.split(tail)
    except ValueError:
        continue                                      # unparseable tail — fail open

    path_args, skip = [], False
    for tok in tokens:
        if skip:
            skip = False
            continue
        if tok.startswith("-"):
            if tok in VALUE_FLAGS:
                skip = True
            continue
        path_args.append(tok)

    if any(".py" in os.path.basename(a.split("::")[0]) or "::" in a for a in path_args):
        continue                                      # file-scoped — the lawful shape

    eff = effective_dir(cmd[: m.start()])
    if eff is None or not os.path.isdir(eff):
        continue                                      # cannot place — fail open
    root = checkout_root(eff)
    if root is None:
        continue                                      # other repo — not this guard\x27s lane

    suite_roots = {os.path.join(root, "tests"),
                   os.path.join(root, "cli", "tests"),
                   os.path.join(root, "web", "api", "tests")}

    if not path_args:
        # Bare pytest: full collection of whatever the cwd\x27s ini finds — deny only
        # from a suite parent or suite root, where that collection is the heavy estate.
        here = os.path.realpath(eff)
        if here in suite_roots or here in {root,
                                           os.path.join(root, "cli"),
                                           os.path.join(root, "web", "api")}:
            print("deny")
            sys.exit(0)
        continue

    resolved = []
    for a in path_args:
        p = os.path.expanduser(a)
        if "$" in p:
            resolved = None
            break                                     # unresolved variable — fail open
        p = p if os.path.isabs(p) else os.path.join(eff, p)
        if not os.path.isdir(p):
            resolved = None
            break                                     # nonexistent / not a dir — fail open
        resolved.append(os.path.realpath(p))
    if resolved is None:
        continue

    if all(p in suite_roots for p in resolved):
        print("deny")                                 # every arg is a whole suite
        sys.exit(0)
sys.exit(0)
' 2>/dev/null)"

[ "$verdict" = "deny" ] || exit 0

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"Full-suite pytest outside verify.py is blocked (scoped-verification law, CLAUDE.md § Worktree Isolation; 2026-07-15 host-thrash incident: two concurrent full cli suites + Backblaze re-crawl). Run `bash scripts/verify-scoped.sh` — it selects, tiers, env-scrubs and flock-serializes exactly the gates your diff implicates — or scope to the files under test (`pytest cli/tests/test_x.py`). A directory + -k is still a full collection. Escape hatch: LIMEN_ALLOW_FULL_PYTEST=1."}}\n'
exit 0
