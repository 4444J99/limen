#!/usr/bin/env python3
"""RUNNER COVERAGE — every declared enforcement artifact must have something that RUNS it.

The check-*.py family all asks one question: *does the registry agree with the code?* Each member
verifies declaration↔file parity — the registry names a script, the script exists, the gate literal
appears in a beat source. Not one of them asks the question a level up: **who executes that file?**

That gap is not hypothetical. `scripts/metabolize.sh` exists, is syntactically valid, is named by
`gates.yaml`, and holds the gate literals for 39 sensors whose `source: [metabolize]` check-sensors.py
happily validates — and **nothing invokes it**. No tracked launchd plist, no other script, no CI
workflow. Those 39 sensors are declared, gated on, and have never executed. Worse, `verify-whole.sh`
skips three whole rungs on the recorded grounds that "the beat via metabolize.sh step 0e/0f/0g" runs
them: both sides believe the other one covers it, so the work is covered by neither.

check-sensors.py has an F "live reachability" check, but it is scoped `if "heartbeat" in source` —
metabolize-source sensors are exempt by construction, and its D check is satisfied by a literal
appearing *in a file* whether or not that file is ever run.

Exit 0 ⟺ every declared enforcement artifact has a runner:

  A runner reachability — every beat runner named by a sensor's `source:` is reachable from a
                          repo-tracked entrypoint (a `container/launchd/*.plist` Program/Arguments,
                          or a CI workflow `run:` step), directly or through invoking scripts.
  B probe scripts       — every `ideal-forms.yaml` probe command names a script that exists.
  C predicate scripts   — every `outbound-effectors.yaml` predicate names a script that exists. A
                          missing predicate is not inert: the guard fails closed inside its match,
                          so arming it would deny the whole effector class forever.
  D honest hooks        — a hook whose prose claims to block emits a real `permissionDecision`. A
                          hook that says HARD BLOCK and returns silence allows every call.
  E cited scripts       — a `censor/precedents.jsonl` record that cites a script cites a real one.
                          (`PREC-2026-07-10-declared-but-unwired-is-a-defect` cited
                          `scripts/trunk-ci-health.py`, which never existed in any commit.)

Reachability is deliberately proven from **repo-tracked** artifacts only. The operator's live
`~/Library/LaunchAgents` is a host fact and cannot be observed in CI (the environment split
`check-ideal-forms.py` enforces); a plist that is not tracked cannot prove anything to this gate.

Known-open findings live in `unreachable-runners-baseline.txt` — same idiom as
`undeclared-params-baseline.txt`. The gate fails on any NEW finding; the baseline keeps the existing
ones visible and owned in git rather than silently tolerated.

  python3 scripts/check-runner-coverage.py            # gate (CI): exit 1 on any new finding
  python3 scripts/check-runner-coverage.py --update   # fold current findings into the baseline
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GOV = ROOT / "institutio" / "governance"
SENSORS = GOV / "sensors.yaml"
IDEALS = GOV / "ideal-forms.yaml"
EFFECTORS = GOV / "outbound-effectors.yaml"
PRECEDENTS = ROOT / "censor" / "precedents.jsonl"
HOOKS_DIR = ROOT / "scripts" / "hooks"
BASELINE = GOV / "unreachable-runners-baseline.txt"

LAUNCHD_DIR = ROOT / "container" / "launchd"
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
SCRIPTS_DIR = ROOT / "scripts"

# A sensor's `source:` names a beat runner. An unmapped source is itself a finding — a runner nobody
# can name is a runner nobody can prove runs.
BEAT_SOURCE_SCRIPTS = {
    "metabolize": "scripts/metabolize.sh",
    "heartbeat": "scripts/heartbeat-loop.sh",
}

SCRIPT_PATH_RE = re.compile(r"scripts/[\w./-]+\.(?:py|sh)")

# What must appear just before a path for it to be an INVOCATION rather than a mention. This is the
# whole difficulty of the check: verify-whole.sh names metabolize.sh in a comment explaining why it
# skips work, and a substring search would read that as proof the runner runs.
# The interpreter is often held in a VARIABLE rather than named literally — the creds-hydrate plist
# runs `exec "$PY" "$LIMEN_ROOT/scripts/creds-hydrate.py"`, and a literal-only pattern reads that as
# prose. So: an execution verb, then any quoting/list punctuation, then any number of `$VAR`
# interpreter tokens, then an optional path head.
_EXEC_PREFIX = re.compile(
    r"\b(?:exec|command|source|bash|sh|zsh|python3?|env|uv\s+run)\b"
    r"[\"'\s,\[(]*"
    r"(?:\$\{?[A-Za-z_]\w*\}?[\"'\s]*)*"
    r"(?:[\w.${}/-]*/)?$"
)
# Command position: start of line, or after a shell separator — a directly-executed script.
_COMMAND_POS = re.compile(r"(?:^|[;&|(]|&&|\|\||\$\()\s*[\"']?[^\"'\s]*$")

BLOCK_LANGUAGE = re.compile(r"HARD BLOCK|\bden(?:y|ies|ied)\b|\bblocks?\b|\brefuses?\b", re.I)
# "never blocks", "cannot block", "so it never blocks an edit" are hooks documenting that they do
# NOT block. Reading those as a claim would make this gate demand the deletion of accurate prose.
NEGATED = re.compile(r"\b(?:never|cannot|can't|not|no|without|non)\b[\w\s,'-]{0,24}$", re.I)


def _strip_comments(text: str) -> str:
    """Drop whole-line comments. Prose about a runner is not a runner being run."""
    out = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def invoked_scripts(text: str) -> set[str]:
    """Repo-relative script paths this text actually INVOKES (not merely mentions)."""
    body = _strip_comments(text)
    found: set[str] = set()
    for match in SCRIPT_PATH_RE.finditer(body):
        line_start = body.rfind("\n", 0, match.start()) + 1
        prefix = body[line_start : match.start()]
        if _EXEC_PREFIX.search(prefix) or _COMMAND_POS.search(prefix):
            found.add(match.group(0))
    return found


def _plist_invocations(path: Path) -> set[str]:
    """A launchd plist runs whatever its <string> values name — Program or ProgramArguments."""
    text = path.read_text(errors="replace")
    found: set[str] = set()
    for value in re.findall(r"<string>(.*?)</string>", text, re.S):
        found.update(SCRIPT_PATH_RE.findall(value))
    return found


def _workflow_invocations(path: Path) -> set[str]:
    """Only `run:` bodies invoke. A workflow's `paths:` filter names files it WATCHES, not runs —
    counting those would make every registry-listed script look reachable."""
    try:
        doc = yaml.safe_load(path.read_text(errors="replace"))
    except yaml.YAMLError:
        return set()
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "run" and isinstance(value, str):
                    found.update(invoked_scripts(value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    return found


def reachable_scripts() -> set[str]:
    """Breadth-first closure from repo-tracked entrypoints over actual invocations."""
    frontier: set[str] = set()
    for plist in sorted(LAUNCHD_DIR.glob("*.plist")):
        frontier |= _plist_invocations(plist)
    for workflow in sorted(WORKFLOWS_DIR.glob("*.y*ml")):
        frontier |= _workflow_invocations(workflow)

    seen: set[str] = set()
    while frontier:
        rel = frontier.pop()
        if rel in seen:
            continue
        seen.add(rel)
        target = ROOT / rel
        if not target.is_file():
            continue
        frontier |= invoked_scripts(target.read_text(errors="replace")) - seen
    return seen


def check_runners(findings: list[str]) -> None:
    """A — every beat runner a sensor declares must be reachable from an entrypoint."""
    registry = yaml.safe_load(SENSORS.read_text())
    sensors = registry.get("sensors") or []
    if isinstance(sensors, dict):
        sensors = list(sensors.values())

    declared: dict[str, list[str]] = {}
    for sensor in sensors:
        sid = sensor.get("id") or sensor.get("gate") or "<unnamed>"
        for source in sensor.get("source") or []:
            declared.setdefault(str(source).strip(), []).append(sid)

    reachable = reachable_scripts()
    for source, users in sorted(declared.items()):
        script = BEAT_SOURCE_SCRIPTS.get(source)
        if script is None:
            findings.append(
                f"A runner-unmapped: sensor source '{source}' ({len(users)} sensor(s)) maps to no "
                f"known runner script — add it to BEAT_SOURCE_SCRIPTS or fix the source name"
            )
            continue
        if not (ROOT / script).is_file():
            findings.append(f"A runner-missing: source '{source}' names {script}, which does not exist")
            continue
        if script not in reachable:
            findings.append(
                f"A runner-unreachable: {script} (source '{source}', {len(users)} sensor(s)) is "
                f"invoked by NO tracked launchd plist, CI workflow, or reachable script — those "
                f"sensors are declared and never execute"
            )


def _cited_scripts(text: str) -> set[str]:
    return set(SCRIPT_PATH_RE.findall(text or ""))


def check_probes(findings: list[str]) -> None:
    """B — an ideal's probe must name a script that exists, or it can never measure anything."""
    ideals = yaml.safe_load(IDEALS.read_text()).get("ideals") or {}
    for iid, row in sorted(ideals.items()):
        probe = row.get("probe")
        if not probe:
            continue
        command = probe if isinstance(probe, str) else str(probe.get("command") or "")
        for script in sorted(_cited_scripts(command)):
            if not (ROOT / script).is_file():
                findings.append(f"B probe-missing: ideal '{iid}' probes {script}, which does not exist")


def check_predicates(findings: list[str]) -> None:
    """C — an effector's predicate must exist. The guard fails closed inside its match, so a missing
    predicate does not degrade to 'unproven' — it denies the entire effector class permanently."""
    effectors = yaml.safe_load(EFFECTORS.read_text()).get("effectors") or {}
    for eid, row in sorted(effectors.items()):
        for script in sorted(_cited_scripts(str(row.get("predicate") or ""))):
            if not (ROOT / script).is_file():
                findings.append(
                    f"C predicate-missing: effector '{eid}' requires {script}, which does not exist "
                    f"— arming this effector would deny every matching command"
                )


def claims_to_block(text: str) -> bool:
    """An AFFIRMATIVE claim to block, and only from a hook that could block.

    Two gates, both learned by running this check against the real hook set. Only a `PreToolUse`
    hook can deny — SessionStart/PostToolUse hooks have no deny channel, so blocking words in them
    are prose, never a claim. And a claim must not be negated: `lint-edited-file.sh` says "ALWAYS
    exits 0 (advisory) so it never blocks an edit", which is the opposite of claiming to block.
    """
    if "PreToolUse" not in text:
        return False
    for match in BLOCK_LANGUAGE.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        if not NEGATED.search(text[line_start : match.start()]):
            return True
    return False


def check_hooks(findings: list[str]) -> None:
    """D — a hook that claims to block must emit a decision. Silence on stdout means ALLOW."""
    if not HOOKS_DIR.is_dir():
        return
    for hook in sorted(HOOKS_DIR.iterdir()):
        if hook.suffix not in (".py", ".sh") or not hook.is_file():
            continue
        text = hook.read_text(errors="replace")
        if claims_to_block(text) and "permissionDecision" not in text:
            findings.append(
                f"D hook-dishonest: {hook.relative_to(ROOT)} uses blocking language but never emits "
                f"permissionDecision — it allows every call it claims to stop"
            )


def check_precedents(findings: list[str]) -> None:
    """E — a precedent's remedy must be real. A precedent citing a script that never existed records
    a correction nobody can run."""
    if not PRECEDENTS.is_file():
        return
    for line in PRECEDENTS.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            findings.append("E precedent-unparseable: a line in censor/precedents.jsonl is not JSON")
            continue
        pid = row.get("id", "<unnamed>")
        for script in sorted(_cited_scripts(json.dumps(row))):
            if not (ROOT / script).is_file():
                findings.append(f"E citation-missing: precedent '{pid}' cites {script}, which does not exist")


def read_baseline() -> set[str]:
    if not BASELINE.is_file():
        return set()
    return {
        line.strip() for line in BASELINE.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
    }


def write_baseline(findings: list[str]) -> None:
    header = (
        "# unreachable-runners-baseline — declared enforcement artifacts with no runner, known and\n"
        "# owned rather than silently tolerated. The gate fails on any NEW finding.\n"
        "# Fix the artifact, then run: python3 scripts/check-runner-coverage.py --update\n"
    )
    BASELINE.write_text(header + "\n".join(sorted(findings)) + ("\n" if findings else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", action="store_true", help="fold current findings into the baseline")
    args = parser.parse_args(argv)

    findings: list[str] = []
    check_runners(findings)
    check_probes(findings)
    check_predicates(findings)
    check_hooks(findings)
    check_precedents(findings)

    if args.update:
        write_baseline(findings)
        print(f"runner-coverage: baseline updated with {len(findings)} finding(s) -> {BASELINE.relative_to(ROOT)}")
        return 0

    baseline = read_baseline()
    fresh = [f for f in findings if f not in baseline]
    stale = sorted(baseline - set(findings))

    for finding in sorted(fresh):
        print(f"FAIL {finding}")
    for entry in stale:
        print(f"note baseline entry no longer reproduces (run --update to drop it): {entry}")

    if fresh:
        print(f"\nrunner-coverage: {len(fresh)} NEW finding(s) — a declared artifact with no runner is inert")
        return 1

    held = len(findings)
    print(
        f"runner-coverage: no new findings ({held} baselined) — every declared runner reaches an "
        f"entrypoint, every probe/predicate/citation names a real script, every blocking hook decides."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
