#!/usr/bin/env python3
"""check-effectors — the OUTBOUND-EFFECTORS registry's own drift predicate.

The fifth VIGILIA-shaped panel (institutio/governance/outbound-effectors.yaml) declares which
outward-facing actions may not run without a fresh, digest-bound proof-of-observation receipt.
Its siblings each carry a parity predicate — GATES/check-gates.py, SENSORS/check-sensors.py,
PARAMETERS/check-params.py, MAIL-TIERS/check-mail-tiers.py. This is the effector panel's.

Three finding classes, in ascending order of how much they cost to learn the hard way:

  A declaration — the registry is internally coherent: every effector declares the keys the
    guard reads, its `predicate:` names a file that exists on disk, and that predicate takes a
    `{target}` substitution. A predicate naming a file that was never written is the exact
    defect check-runner-coverage finding C caught on 2026-07-31: `github.comment` shipped
    pointing at scripts/preflight-thread-state.py while no such file existed, which — because
    the guard FAILS CLOSED inside its match — would have denied every `gh pr comment` in the
    estate the moment the hook was armed.

  B pattern — every `match:` regex compiles, and each `target.pattern` compiles with AT MOST
    ONE capture group. That bound is load-bearing, not stylistic. The guard extracts via
    `match.group(1) if match.groups() else match.group(0)`
    (scripts/hooks/outbound-preflight-guard.py:94), so a pattern with two groups silently keeps
    the first and discards the second. A two-part target — repo AND number — is therefore
    inexpressible, and a well-meant `(--repo (\\S+)\\s+)?([0-9]+)` would check the AMBIENT
    repo's #N while the command addresses a DIFFERENT repo's #N. Checking the wrong thread and
    reporting success is worse than refusing to look. The registry documents this constraint in
    a comment; this class is what makes the comment true.

  C coverage — the structural hole, and the reason this file is worth more than a schema lint.
    The guard is a PreToolUse(Bash) hook. It sees a COMMAND STRING that an agent is about to
    run. It cannot see, and can never see, `subprocess.run(["gh", "pr", "comment", url, ...])`
    executed from inside a Python module: there is no shell, no command string, no tool call.
    Every genuinely dangerous outward action in this estate takes that in-process form and runs
    UNATTENDED ON THE BEAT — repo visibility flips, PR merges that auto-deploy the live site,
    issue comments on third-party repositories, real SMTP sends. The hook covers the surface
    where a charter-reading model is already in the loop, and misses all the sharp ones.

    This class enumerates those sites mechanically and ratchets them. It does not pretend the
    known sites can be fixed at once; it pins them in a baseline so the surface is VISIBLE and
    CANNOT GROW. A newly-added ungated sender is a red check, not an archaeology session six
    months later. How many there are is stated in the baseline file and NOWHERE ELSE — this
    sentence used to restate the count and had already gone stale by the time it shipped: it
    said 17, the number a hand grep of `subprocess.run(["gh"` found, while the AST walk that
    actually runs here is invariant to how the argv reaches the process (call argument, prior
    name binding, local `sh()` wrapper) and so pins materially more. A count in prose is a
    second copy of a fact the registry owns, which is the same defect class this panel exists
    to gate.

    Deliberately NOT flagged: `osascript -e 'display notification ...'`
    (scripts/conducting-report.py, scripts/notify-events.py, scripts/_notify.py). That is a
    local desktop toast, not an outward send. Adding it would train readers to ignore class C,
    which is how a noisy gate becomes an advisory one.

Baseline: institutio/governance/ungated-effectors-baseline.txt. The gate fails on any NEW
finding. Findings are keyed by FILE AND VERB, never by line number, so ordinary edits to a
sender do not churn the baseline.

Usage:
    python3 scripts/check-effectors.py            # exit 1 on any NEW finding
    python3 scripts/check-effectors.py --update   # re-pin the baseline after a real fix
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GOV = ROOT / "institutio" / "governance"
REGISTRY = GOV / "outbound-effectors.yaml"
BASELINE = GOV / "ungated-effectors-baseline.txt"

# Required keys on every effector row — exactly the ones the guard reads. Keeping this list in
# sync with the guard is the point of class A; a key the guard needs and the registry omits is a
# runtime AttributeError on the one code path nobody exercises until it denies a real send.
REQUIRED_KEYS = ("title", "match", "target", "predicate", "max_age_seconds", "reason")

# Where in-process senders live. `web/` is excluded: its outward surface is the deployed Worker,
# gated by persona tokens rather than by a local receipt.
SCAN_ROOTS = ("scripts", "cli/src", "mcp", "ianva", "organs")

# `gh` subcommand pairs that MUTATE something outside this machine. Read verbs (view, list,
# status, diff, checks) are absent on purpose — they are how a predicate does its job, and
# flagging them would make the gate hostile to the very checks it wants written.
GH_WRITE_VERBS: frozenset[tuple[str, str]] = frozenset(
    {
        ("pr", "comment"),
        ("pr", "create"),
        ("pr", "merge"),
        ("pr", "edit"),
        ("pr", "close"),
        ("pr", "reopen"),
        ("pr", "review"),
        ("pr", "ready"),
        ("issue", "comment"),
        ("issue", "create"),
        ("issue", "edit"),
        ("issue", "close"),
        ("issue", "reopen"),
        ("issue", "delete"),
        ("repo", "create"),
        ("repo", "edit"),
        ("repo", "delete"),
        ("repo", "archive"),
        ("repo", "rename"),
        ("release", "create"),
        ("release", "edit"),
        ("release", "delete"),
        ("secret", "set"),
        ("secret", "delete"),
        ("workflow", "run"),
        ("workflow", "enable"),
        ("workflow", "disable"),
    }
)

# `gh api` is a write only when it carries a mutating method. Without this, every read-only
# `gh api repos/...` call in the estate would land in class C as noise.
GH_API_WRITE_FLAGS = ("-X", "--method")
GH_API_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Modules that put a message on the wire by themselves, with no subprocess in between.
#
# `aiosmtplib` is a drop-in async replacement for smtplib and imports cleanly past a two-name
# allowlist — it is listed here BEFORE anything uses it, on purpose. This is a ratchet, and a
# ratchet only works if the tooth is cut before the load arrives: adding the name the day someone
# reaches for it means class C is silent for exactly the commit that opens the hole. A name here
# that nothing imports costs nothing (the AST walk simply never matches it) and carries no
# false-positive surface, unlike a `match:` regex, which is evaluated against every command an
# agent runs and so cannot be widened speculatively.
SMTP_MODULES = frozenset({"smtplib", "yagmail", "aiosmtplib"})


def _iter_python_files() -> list[Path]:
    """Every tracked-looking .py file under SCAN_ROOTS, tests excluded.

    Tests are excluded because a test that BUILDS a `["gh", "pr", "merge", ...]` argv to assert a
    guard rejects it is the opposite of an ungated sender, and flagging fixtures would make the
    only honest response to this gate a baseline entry.
    """
    files: list[Path] = []
    for rel in SCAN_ROOTS:
        base = ROOT / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = set(path.parts)
            if "tests" in parts or "test" in parts or path.name.startswith("test_"):
                continue
            if "node_modules" in parts or ".venv" in parts or "__pycache__" in parts:
                continue
            files.append(path)
    return files


def _leading_constants(node: ast.List) -> list[str]:
    """The leading run of string constants in a list literal, stopping at the first variable.

    `["gh", "issue", "create", "--label", LABEL, ...]` yields the first four. That is enough to
    identify the verb pair, which is all class C needs — and stopping at LABEL rather than
    guessing its value keeps this a syntactic check with no evaluation.
    """
    out: list[str] = []
    for element in node.elts:
        if isinstance(element, ast.Constant) and isinstance(element.value, str):
            out.append(element.value)
        else:
            break
    return out


def _gh_write_verb(parts: list[str]) -> str | None:
    """The `<noun> <verb>` this argv performs, if it mutates anything outward."""
    if len(parts) < 3 or parts[0] != "gh":
        return None
    noun, verb = parts[1], parts[2]
    if (noun, verb) in GH_WRITE_VERBS:
        return f"gh {noun} {verb}"
    if noun == "api":
        for index, token in enumerate(parts):
            if token in GH_API_WRITE_FLAGS and index + 1 < len(parts):
                method = parts[index + 1].upper()
                if method in GH_API_WRITE_METHODS:
                    return f"gh api -X {method}"
    return None


def scan_file(path: Path) -> set[str]:
    """Outward-write capabilities this module performs in-process, as stable labels."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        # Every list literal, not merely subprocess-call arguments: autonomy-governor.py binds
        # `merge_cmd = ["gh", "pr", "merge", pr, "--squash"]` to a name first and runs it later,
        # so a call-argument-only walk would miss the single most consequential site in the file.
        if isinstance(node, ast.List):
            verb = _gh_write_verb(_leading_constants(node))
            if verb:
                found.add(verb)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in SMTP_MODULES:
                    found.add(f"import {alias.name.split('.')[0]}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in SMTP_MODULES:
                found.add(f"import {node.module.split('.')[0]}")
    return found


def check_declaration(registry: dict, findings: list[str]) -> dict:
    """Class A — the registry is coherent and every declared predicate exists on disk."""
    effectors = registry.get("effectors")
    if not isinstance(effectors, dict) or not effectors:
        findings.append("A registry-empty: outbound-effectors.yaml declares no effectors")
        return {}

    receipts_dir = str(registry.get("receipts_dir") or "")
    if not receipts_dir:
        findings.append("A receipts-dir-missing: outbound-effectors.yaml declares no receipts_dir")
    elif not receipts_dir.startswith("logs/"):
        findings.append(
            f"A receipts-dir-committed: receipts_dir '{receipts_dir}' is not under logs/ — "
            f"receipts are runtime state and must never enter a commit"
        )

    for eid, row in sorted(effectors.items()):
        if not isinstance(row, dict):
            findings.append(f"A effector-malformed: effector '{eid}' is not a mapping")
            continue

        for key in REQUIRED_KEYS:
            if key not in row:
                findings.append(f"A key-missing: effector '{eid}' declares no '{key}' — the guard reads it")

        if "max_age_seconds" in row:
            age = row["max_age_seconds"]
            # `isinstance(True, int)` is True in Python, so a stray `max_age_seconds: yes` in YAML
            # would otherwise read as the perfectly valid window of 1 second.
            if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
                findings.append(
                    f"A max-age-invalid: effector '{eid}' has max_age_seconds={age!r}; a "
                    f"non-positive freshness window makes every receipt eternally valid"
                )

        predicate = str(row.get("predicate") or "").strip()
        if predicate:
            if "{target}" not in predicate:
                findings.append(
                    f"A predicate-untargeted: effector '{eid}' predicate has no {{target}} "
                    f"substitution, so one receipt would satisfy every target"
                )
            # The script the predicate shells out to must exist. This is finding C of
            # check-runner-coverage, generalised: a declared predicate that is not on disk turns
            # a fail-closed guard into a total denial the moment it is armed.
            for token in predicate.split():
                if token.endswith(".py") or token.endswith(".sh"):
                    if not (ROOT / token).is_file():
                        findings.append(
                            f"A predicate-missing: effector '{eid}' predicate names {token}, "
                            f"which does not exist — arming the guard would deny every matching action"
                        )
                    break

    return effectors


def check_patterns(effectors: dict, findings: list[str]) -> None:
    """Class B — regexes compile, and no target pattern exceeds the single-group bound."""
    for eid, row in sorted(effectors.items()):
        if not isinstance(row, dict):
            continue

        matches = row.get("match")
        if not isinstance(matches, list) or not matches:
            findings.append(f"B match-empty: effector '{eid}' declares no match patterns, so it gates nothing")
        else:
            for pattern in matches:
                try:
                    re.compile(str(pattern))
                except re.error as exc:
                    findings.append(f"B match-uncompilable: effector '{eid}' pattern {pattern!r} — {exc}")

        target = row.get("target")
        if not isinstance(target, dict):
            findings.append(f"B target-malformed: effector '{eid}' target is not a mapping")
            continue
        if not target.get("kind"):
            findings.append(f"B target-kindless: effector '{eid}' target declares no kind")

        pattern = str(target.get("pattern") or "")
        if not pattern:
            findings.append(f"B target-patternless: effector '{eid}' target has no pattern; the guard extracts nothing")
            continue
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            findings.append(f"B target-uncompilable: effector '{eid}' target pattern — {exc}")
            continue
        if compiled.groups > 1:
            findings.append(
                f"B target-overgrouped: effector '{eid}' target pattern has {compiled.groups} "
                f"capture groups; the guard reads group(1) only, so groups 2+ are silently "
                f"discarded and the predicate would run against a PARTIAL target"
            )


def check_coverage(findings: list[str]) -> None:
    """Class C — in-process outward senders the PreToolUse(Bash) guard structurally cannot see."""
    for path in _iter_python_files():
        rel = path.relative_to(ROOT).as_posix()
        for verb in sorted(scan_file(path)):
            findings.append(
                f"C ungated-effector: {rel} performs `{verb}` in-process, where the "
                f"PreToolUse(Bash) guard is structurally blind — no command string ever exists"
            )


def read_baseline() -> set[str]:
    if not BASELINE.is_file():
        return set()
    return {
        line.strip() for line in BASELINE.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
    }


def write_baseline(findings: list[str]) -> None:
    header = (
        "# ungated-effectors-baseline — outward actions performed in-process, where a\n"
        "# PreToolUse(Bash) hook cannot reach them. Known and owned rather than silently\n"
        "# tolerated. The gate fails on any NEW finding; this list may only shrink.\n"
        "# Route the sender through the receipt check, then run:\n"
        "#   python3 scripts/check-effectors.py --update\n"
    )
    BASELINE.write_text(header + "\n".join(sorted(findings)) + ("\n" if findings else ""))


def collect() -> list[str]:
    findings: list[str] = []
    if not REGISTRY.is_file():
        return [f"A registry-missing: {REGISTRY.relative_to(ROOT)} does not exist"]
    try:
        registry = yaml.safe_load(REGISTRY.read_text()) or {}
    except yaml.YAMLError as exc:
        return [f"A registry-unparseable: outbound-effectors.yaml is not valid YAML — {exc}"]

    effectors = check_declaration(registry, findings)
    if effectors:
        check_patterns(effectors, findings)
    check_coverage(findings)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--update", action="store_true", help="re-pin the baseline to the current findings")
    args = parser.parse_args(argv)

    findings = collect()

    if args.update:
        write_baseline(findings)
        print(f"effectors: baseline updated with {len(findings)} finding(s) -> {BASELINE.relative_to(ROOT)}")
        return 0

    baselined = read_baseline()
    fresh = sorted(f for f in findings if f not in baselined)
    stale = sorted(baselined - set(findings))

    for finding in fresh:
        print(f"FAIL {finding}")
    for entry in stale:
        print(f"note baseline entry no longer reproduces (run --update to drop it): {entry}")

    if fresh:
        print(
            f"\neffectors: {len(fresh)} NEW finding(s) — an outward action with no reachable "
            f"gate is an ungoverned effector"
        )
        return 1

    print(f"effectors: no new findings ({len(baselined)} baselined)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
