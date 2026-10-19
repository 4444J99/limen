#!/usr/bin/env python3
"""check-stop-governor: exit 0 if and only if the stop governor's declared state holds.

The operator's recurring follow-up asks are declared data (institutio/governance/post-opener-intents.json)
and fired by scripts/stop-governor.py at the turn-end boundary. This predicate holds the two together and
holds the registry to the study that motivated it (docs/prompt-control-vocabulary-study.md, section 3):

  A  registry parity   16 intent ids and counts equal the study's section 3 table; the counts sum to the
                       study's total; every class carries what it must (stop rows name rules; the rest name
                       an owner); the rule set equals the governor's detector set
  B  promotion         a rule may be live only with a promotion block: replay or shadow evidence (n >= 30,
                       precision >= 0.80, MERGE >= 0.90) or an explicit operator decision reference
  C  text discipline   continuation texts are bounded, lowercase (operator voice), name only existing paths,
                       never name a slash command as the mechanism, and each carries one of the rule's own
                       lexicon phrases, every one of which appears verbatim in the study
  D  behavior          every fixture in scripts/tests/fixtures/stop-governor-cases.json holds through the
                       real decide(); every decision code is covered; the same stop yields byte-identical
                       output on Claude and Codex; forcing every rule to shadow silences every case
  E  hook contract     the real wrapper and the Codex runner arm print nothing on garbage, empty or oversize
                       input, an unwritable ledger or a shadow rule, and exactly one {decision, reason}
                       object when a live rule fires
  F  codex shape       the host-admission Stop continuation is {decision: block, reason}, with the legacy
                       halt shape tolerated through version skew and hookSpecificOutput rejected on Stop
  G  staged snippet    docs/keys/stop-governor-settings-snippet.json wires only Stop, fail-open, with a
                       bounded timeout, at targets that exist and are executable
  H  parameters        the three LIMEN_STOP_GOVERNOR* knobs are declared and the script's fallbacks equal
                       their declared defaults
  I  lever and valves  L-STOP-GOVERNOR-ARM and the two armed-valve rows exist and cite each other

Arming state (is the Stop entry present in the tracked settings yet?) is REPORTED by --armed and is never
part of the exit code: an unarmed governor is a filed lever, not a failing build.

Stdlib only. Writes nothing outside a temp dir. Run it bare and read its own exit code.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "post-opener-intents.json"
STUDY = ROOT / "docs" / "prompt-control-vocabulary-study.md"
SNIPPET = ROOT / "docs" / "keys" / "stop-governor-settings-snippet.json"
FIXTURES = ROOT / "scripts" / "tests" / "fixtures" / "stop-governor-cases.json"
GOVERNOR = ROOT / "scripts" / "stop-governor.py"
WRAPPER = ROOT / "scripts" / "hooks" / "stop-governor.sh"
RUNNER = ROOT / "scripts" / "hooks" / "codex-hook-runner.sh"
CODEX_HOOK = ROOT / "scripts" / "hooks" / "codex-host-admission.py"
PARAMETERS = ROOT / "institutio" / "governance" / "parameters.yaml"
LEVERS = ROOT / "his-hand-levers.json"
VALVES = ROOT / "spec" / "armed-valves.json"
LEVER_ID = "L-STOP-GOVERNOR-ARM"

CLASSES = {"stop", "irreducible", "owner-elsewhere", "deferred"}
IRREDUCIBLE = {"NEWTASK", "CONVO/INFO"}
PRECISION_FLOOR = {"default": 0.80, "MERGE": 0.90}
MIN_N = 30
MAX_TEXT = 600
MAX_COMPOSED = 1200
UPPER_OK = {"BLOCKED", "MERGE-MODE", "MERGE-HEAD"}
PATH_PREFIXES = ("scripts/", ".agents/", "institutio/", "docs/", "cli/")
REQUIRED_CODES = {
    "not_stop",
    "kill_switch",
    "continuation_active",
    "mode:*",
    "background_job",
    "loop_owns_cadence",
    "empty",
    "fixed_point",
    "blocked_once",
    "no_signal",
    "out_of_scope",
    "paused_wall",
    "would_block",
    "continue",
    "gated_tail",
    "codex_admission_owns",
    "no_session",
    "intent_cap",
    "session_cap",
    "daily_cap",
    "dup_claim",
    "no_ledger",
}
MIRRORS = (("claude-clean-cont", "codex-clean-cont"), ("claude-close", "codex-close"))

failures: list[str] = []


def fail(check: str, message: str) -> None:
    failures.append(f"[{check}] {message}")


def load_json(path: Path, check: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(check, f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} unreadable: {type(exc).__name__}")
        return None


def load_module(name: str, path: Path, extra_path: Path | None = None) -> Any:
    if extra_path is not None and str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses with postponed annotations need the module registered
    spec.loader.exec_module(module)
    return module


def study_rows(text: str) -> dict[str, int]:
    """(id -> n) from the first two columns of the section 3 table; the study's own labels are the ids."""
    rows: dict[str, int] = {}
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.startswith("## 3.")
            continue
        if not in_section:
            continue
        match = re.match(r"^\|\s*([A-Z][A-Z /+]*[A-Z])(?:\s*\(.*?\))?\s*\|\s*([\d,]+)\s*\|", line)
        if match:
            rows[match.group(1).replace(" ", "")] = int(match.group(2).replace(",", ""))
    return rows


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


# --------------------------------------------------------------------------- A


def check_registry_parity(reg: dict[str, Any], study_text: str, governor: Any) -> None:
    if not isinstance(reg.get("schema_version"), str):
        fail("A", "registry has no schema_version")
    study = study_rows(study_text)
    ref = reg.get("study_ref") or {}
    if not study:
        fail("A", "no intent rows parsed from the study's section 3 table")
    intents = reg.get("intents")
    rules = reg.get("rules")
    if not isinstance(intents, dict) or not isinstance(rules, dict):
        fail("A", "registry lacks intents or rules")
        return
    registry_n = {k: v.get("n") for k, v in intents.items()}
    if set(registry_n) != set(study):
        fail(
            "A",
            f"intent ids differ from the study: registry-only {sorted(set(registry_n) - set(study))}, "
            f"study-only {sorted(set(study) - set(registry_n))}",
        )
    for key in sorted(set(registry_n) & set(study)):
        if registry_n[key] != study[key]:
            fail("A", f"{key}: n={registry_n[key]} but the study table says {study[key]}")
    if sum(study.values()) != ref.get("total"):
        fail("A", f"study table sums to {sum(study.values())}, study_ref.total says {ref.get('total')}")
    for key, row in intents.items():
        cls = row.get("class")
        if cls not in CLASSES:
            fail("A", f"{key}: class {cls!r} is not one of {sorted(CLASSES)}")
        for field in ("owner", "claude_binding", "codex_binding", "evidence"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                fail("A", f"{key}: {field} is empty")
        listed = row.get("rules") or []
        if cls == "stop":
            if not listed:
                fail("A", f"{key}: class stop names no rules")
            for name in listed:
                if name not in rules:
                    fail("A", f"{key}: names rule {name} that is not declared")
        elif listed:
            fail("A", f"{key}: class {cls} must not carry rules")
        if key in IRREDUCIBLE and cls != "irreducible":
            fail("A", f"{key}: carries operator-only content and must be class irreducible")
    if set(rules) != set(governor.DETECTORS):
        fail("A", f"rules {sorted(rules)} != governor detectors {sorted(governor.DETECTORS)}")
    for name, rule in rules.items():
        owner = rule.get("intent")
        if owner not in intents:
            fail("A", f"rule {name}: intent {owner!r} is not an intent row")
        elif name not in (intents[owner].get("rules") or []):
            fail("A", f"rule {name}: its intent row {owner} does not list it")


# --------------------------------------------------------------------------- B


def check_promotion(reg: dict[str, Any]) -> None:
    for name, rule in (reg.get("rules") or {}).items():
        mode = rule.get("mode")
        if mode not in ("shadow", "live"):
            fail("B", f"rule {name}: mode {mode!r} is not shadow or live")
        cap = rule.get("cap")
        if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
            fail("B", f"rule {name}: cap must be an integer >= 1")
        promo = rule.get("promotion")
        if mode != "live":
            continue
        if not isinstance(promo, dict):
            fail("B", f"rule {name}: mode live without a promotion block")
            continue
        source = promo.get("source")
        if not isinstance(promo.get("date"), str) or not promo["date"]:
            fail("B", f"rule {name}: promotion has no date")
        if source in ("replay", "shadow"):
            floor = PRECISION_FLOOR.get(name, PRECISION_FLOOR["default"])
            if not isinstance(promo.get("n"), int) or promo["n"] < MIN_N:
                fail("B", f"rule {name}: promotion evidence needs n >= {MIN_N}")
            if not isinstance(promo.get("precision"), (int, float)) or promo["precision"] < floor:
                fail("B", f"rule {name}: promotion precision must be >= {floor}")
        elif source == "operator":
            if not isinstance(promo.get("decision_ref"), str) or not promo["decision_ref"].strip():
                fail("B", f"rule {name}: an operator promotion needs a decision_ref")
        else:
            fail("B", f"rule {name}: promotion source {source!r} is not replay, shadow or operator")


# --------------------------------------------------------------------------- C


def lowercase_discipline(label: str, text: str) -> None:
    for token in text.split():
        if "/" in token or "<" in token:
            continue
        bare = token.strip(".,;:!?'\"()")
        if bare in UPPER_OK or bare == bare.lower():
            continue
        fail("C", f"{label}: token {token!r} is not lowercase (operator voice)")


def check_text(reg: dict[str, Any], study_text: str, governor: Any) -> None:
    study = norm(study_text)
    rules = reg.get("rules") or {}
    for field in ("gate_clause", "status_suffix"):
        value = reg.get(field)
        if not isinstance(value, str) or not value.strip():
            fail("C", f"{field} is empty")
            continue
        lowercase_discipline(field, value)
    if "BLOCKED:" not in str(reg.get("gate_clause", "")):
        fail("C", "gate_clause must tell the agent to say BLOCKED: <atom> once")
    for name, rule in rules.items():
        text = rule.get("text")
        if not isinstance(text, str) or not text.strip():
            fail("C", f"rule {name}: text is empty")
            continue
        if len(text) > MAX_TEXT:
            fail("C", f"rule {name}: text is {len(text)} chars (max {MAX_TEXT})")
        lowercase_discipline(f"rule {name}", text)
        if re.search(r"(?:^|\s)/[a-z][a-z-]*(?=[\s.,;:?]|$)", text):
            fail("C", f"rule {name}: names a slash command as the mechanism (a hook cannot type one)")
        for token in text.split():
            bare = token.strip(".,;:!?'\"()")
            if bare.startswith(PATH_PREFIXES) and not (ROOT / bare).exists():
                fail("C", f"rule {name}: names {bare}, which does not exist")
        phrases = rule.get("lexicon")
        if not isinstance(phrases, list) or not phrases:
            fail("C", f"rule {name}: no lexicon phrases")
            continue
        for phrase in phrases:
            if norm(str(phrase)) not in study:
                fail("C", f"rule {name}: lexicon phrase {phrase!r} is not verbatim in the study")
        if not any(norm(str(p)) in norm(text) for p in phrases):
            fail("C", f"rule {name}: text carries none of its own lexicon phrases")
        composed = governor.compose_reason(reg, (name,), "00000000")
        if len(composed) > MAX_COMPOSED:
            fail("C", f"rule {name}: composed reason is {len(composed)} chars (max {MAX_COMPOSED})")
    if "VERIFY" in rules and "CLOSE" in rules:
        composed = governor.compose_reason(reg, ("VERIFY", "CLOSE"), "00000000")
        if len(composed) > MAX_COMPOSED:
            fail("C", f"VERIFY+CLOSE composed reason is {len(composed)} chars (max {MAX_COMPOSED})")


# --------------------------------------------------------------------------- D


def check_behavior(reg: dict[str, Any], governor: Any, cases_path: Path) -> int:
    cases = load_json(cases_path, "D")
    if not isinstance(cases, list) or not cases:
        fail("D", "fixture matrix is empty or unreadable")
        return 0
    seen: set[str] = set()
    codes: set[str] = set()
    outputs: dict[str, str] = {}
    all_shadow = {"rules": {name: {"mode": "shadow"} for name in reg.get("rules", {})}}
    for case in cases:
        cid = case.get("id", "?")
        if cid in seen:
            fail("D", f"duplicate fixture id {cid}")
        seen.add(cid)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                decision, output = governor.run_case(case, Path(tmp) / "a", registry=reg)
            for problem in governor.case_failures(case, decision, output):
                fail("D", f"{cid}: {problem}")
            outputs[cid] = output
            codes.add("mode:*" if decision.code.startswith("mode:") else decision.code)
            quiet = dict(case)
            quiet["registry_patch"] = governor._deep_merge(case.get("registry_patch") or {}, all_shadow)
            with tempfile.TemporaryDirectory() as tmp:
                _, silent = governor.run_case(quiet, Path(tmp) / "b", registry=reg)
            if silent:
                fail("D", f"{cid}: a shadow-only registry still printed output")
        except Exception as exc:  # noqa: BLE001 - a crashing case is a red check, not a crashed predicate
            fail("D", f"{cid}: crashed with {type(exc).__name__}: {exc}")
    for missing in sorted(REQUIRED_CODES - codes):
        fail("D", f"no fixture exercises decision code {missing}")
    for left, right in MIRRORS:
        if left not in outputs or right not in outputs:
            fail("D", f"mirror pair {left}/{right} is missing from the matrix")
        elif outputs[left] != outputs[right] or not outputs[left]:
            fail("D", f"{left} and {right} must produce byte-identical non-empty output")
    vendors = {c.get("vendor", "claude") for c in cases}
    if vendors != {"claude", "codex"}:
        fail("D", f"the matrix must cover claude and codex, found {sorted(vendors)}")
    return len(cases)


# --------------------------------------------------------------------------- E


def run_wrapper(argv: list[str], stdin: bytes, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(argv, input=stdin, capture_output=True, cwd=cwd, timeout=30, check=False)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


def check_hook_contract(reg: dict[str, Any]) -> None:
    cont = "I fixed the first two. Want me to also fix the other two?"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo = tmp_path / "repo"
        marker = repo / reg.get("scope_marker", "")
        marker.parent.mkdir(parents=True)
        marker.write_text("{}", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(repo)], check=False, capture_output=True)
        shadow = json.loads(json.dumps(reg))
        for rule in shadow["rules"].values():
            rule["mode"] = "shadow"
        live = json.loads(json.dumps(shadow))
        live["rules"]["CONT"]["mode"] = "live"
        live_path = tmp_path / "live.json"
        live_path.write_text(json.dumps(live), encoding="utf-8")
        shadow_path = tmp_path / "shadow.json"
        shadow_path.write_text(json.dumps(shadow), encoding="utf-8")
        payload = json.dumps(
            {
                "hook_event_name": "Stop",
                "session_id": "contract-1",
                "cwd": str(repo),
                "permission_mode": "default",
                "stop_hook_active": False,
                "last_assistant_message": cont,
            }
        ).encode()

        def wrapper(vendor: str, registry: Path, state: Path, stdin: bytes) -> tuple[int, str]:
            return run_wrapper(
                [
                    "bash",
                    str(WRAPPER),
                    "--vendor",
                    vendor,
                    "--event",
                    "Stop",
                    "--registry",
                    str(registry),
                    "--state-dir",
                    str(state),
                ],
                stdin,
                ROOT,
            )

        for label, stdin in (("garbage", b"not json"), ("empty", b""), ("oversize", b"x" * (1 << 21))):
            code, out = wrapper("claude", live_path, tmp_path / "s0", stdin)
            if code != 0 or out:
                fail("E", f"wrapper on {label} stdin: rc={code} stdout={out[:60]!r} (want rc 0, empty stdout)")
        code, out = wrapper("claude", live_path, tmp_path / "missing" / "nested", payload.replace(b"contract-1", b"c2"))
        if code != 0:
            fail("E", f"wrapper with a fresh state dir exited {code}")
        file_state = tmp_path / "state-is-a-file"
        file_state.write_text("", encoding="utf-8")
        code, out = wrapper("claude", live_path, file_state, payload)
        if code != 0 or out:
            fail("E", f"wrapper with an unwritable ledger: rc={code} stdout={out[:60]!r} (want rc 0, empty stdout)")
        code, out = wrapper("claude", shadow_path, tmp_path / "s1", payload)
        if code != 0 or out:
            fail("E", f"wrapper with a shadow rule printed {out[:60]!r}")
        code, claude_out = wrapper("claude", live_path, tmp_path / "s2", payload)
        try:
            shape = json.loads(claude_out)
            if set(shape) != {"decision", "reason"} or shape["decision"] != "block":
                fail("E", f"live Claude output is not exactly {{decision: block, reason}}: {sorted(shape)}")
        except ValueError:
            fail("E", f"live CONT through the Claude wrapper printed {claude_out[:60]!r}, not one JSON object")
        code, codex_out = run_wrapper(
            [
                "bash",
                str(RUNNER),
                "stop-governor",
                "--event",
                "Stop",
                "--registry",
                str(live_path),
                "--state-dir",
                str(tmp_path / "s3"),
            ],
            payload,
            ROOT,
        )
        if code != 0:
            fail("E", f"Codex runner arm exited {code}")
        if claude_out and codex_out != claude_out:
            fail("E", "the Codex runner arm and the Claude wrapper must print byte-identical output for one stop")


# --------------------------------------------------------------------------- F


def check_codex_shape() -> None:
    try:
        hook = load_module("codex_host_admission_under_check", CODEX_HOOK, ROOT / "cli" / "src")
    except Exception as exc:  # noqa: BLE001
        fail("F", f"cannot import codex-host-admission.py: {type(exc).__name__}: {exc}")
        return
    if hook._stop("x") != {"decision": "block", "reason": "x"}:
        fail("F", f"_stop emits {hook._stop('x')!r}; a continuation is {{decision: block, reason}}")
    valid = hook._valid_delegate_verdict
    accepts = [
        ({"decision": "block", "reason": "r"}, "Stop"),
        ({"continue": False, "stopReason": "r"}, "Stop"),
        ({"systemMessage": "m"}, "Stop"),
    ]
    rejects = [
        ({"decision": "block"}, "Stop"),
        ({"decision": "block", "reason": ""}, "Stop"),
        ({"reason": "r"}, "Stop"),
        ({"hookSpecificOutput": {"hookEventName": "Stop"}}, "Stop"),
        ({"decision": "block", "reason": "r"}, "UserPromptSubmit"),
    ]
    for output, event in accepts:
        if not valid(output, event):
            fail("F", f"validator rejects {output} on {event}")
    for output, event in rejects:
        if valid(output, event):
            fail("F", f"validator accepts {output} on {event}")


# --------------------------------------------------------------------------- G


def walk_keys(node: Any) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in walk_keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in walk_keys(v)}
    return set()


def check_snippet(snippet_path: Path) -> None:
    snippet = load_json(snippet_path, "G")
    if not isinstance(snippet, dict):
        return
    if {"async", "asyncRewake"} & walk_keys(snippet):
        fail("G", "the snippet must not use async or asyncRewake hooks")
    claude = (snippet.get("claude") or {}).get("hooks") or {}
    codex = (snippet.get("codex") or {}).get("hooks") or {}
    if set(claude) != {"Stop"}:
        fail("G", f"claude fragment must wire only Stop, found {sorted(claude)}")
    if set(codex) != {"Stop"}:
        fail("G", f"codex fragment must wire only Stop, found {sorted(codex)}")
    for vendor, hooks in (("claude", claude), ("codex", codex)):
        groups = hooks.get("Stop") or []
        entries = [h for g in groups for h in (g.get("hooks") or [])]
        if len(entries) != 1:
            fail("G", f"{vendor} fragment must carry exactly one Stop hook, found {len(entries)}")
        for entry in entries:
            timeout = entry.get("timeout")
            if entry.get("type") != "command" or not isinstance(timeout, int) or not 0 < timeout <= 10:
                fail("G", f"{vendor} Stop hook must be a command with a timeout of at most 10 seconds")
    claude_cmds = [h.get("command", "") for g in claude.get("Stop", []) for h in g.get("hooks", [])]
    for cmd in claude_cmds:
        if "[ -x " not in cmd or not cmd.rstrip().endswith("|| true") or "scripts/hooks/stop-governor.sh" not in cmd:
            fail(
                "G",
                "claude command must use the fail-open `[ -x ... ] && ... || true` idiom on scripts/hooks/stop-governor.sh",
            )
    codex_cmds = [h.get("command", "") for g in codex.get("Stop", []) for h in g.get("hooks", [])]
    for cmd in codex_cmds:
        if "codex-hook-runner.sh" not in cmd or "stop-governor" not in cmd:
            fail("G", "codex command must call codex-hook-runner.sh stop-governor")
    if "stop-governor)" not in RUNNER.read_text(encoding="utf-8"):
        fail("G", "codex-hook-runner.sh has no stop-governor case arm")
    for target in (WRAPPER, RUNNER, GOVERNOR):
        if not target.is_file() or not target.stat().st_mode & 0o111:
            fail("G", f"{target.relative_to(ROOT)} is missing or not executable")


# --------------------------------------------------------------------------- H


def param_block(text: str, key: str) -> dict[str, str] | None:
    match = re.search(rf"^  {re.escape(key)}:\n((?:    .*\n)+)", text, re.MULTILINE)
    if not match:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = re.match(r"^    (\w+):\s*(.*)$", line)
        if field:
            fields[field.group(1)] = field.group(2).strip().strip('"')
    return fields


def check_params(governor: Any) -> None:
    text = PARAMETERS.read_text(encoding="utf-8")
    expected = {
        "LIMEN_STOP_GOVERNOR": "1",
        "LIMEN_STOP_GOVERNOR_MAX_SESSION": str(governor.DEFAULT_MAX_SESSION),
        "LIMEN_STOP_GOVERNOR_DAILY_CAP": str(governor.DEFAULT_DAILY_CAP),
    }
    for key, default in expected.items():
        block = param_block(text, key)
        if block is None:
            fail("H", f"{key} is not declared in parameters.yaml")
            continue
        for field in ("default", "env", "owner"):
            if not block.get(field):
                fail("H", f"{key}: {field} is empty")
        if block.get("env") != key:
            fail("H", f"{key}: env is {block.get('env')!r}")
        if block.get("default") != default:
            fail("H", f"{key}: declared default {block.get('default')!r} != the script's fallback {default!r}")


# --------------------------------------------------------------------------- I


def check_lever_and_valves() -> None:
    levers = load_json(LEVERS, "I")
    if isinstance(levers, dict):
        lever = next((x for x in levers.get("levers", []) if x.get("id") == LEVER_ID), None)
        if lever is None:
            fail("I", f"lever {LEVER_ID} is not filed")
        else:
            if lever.get("status") not in {"open", "discharged", "retired", "needs_human", "optional", "blocked"}:
                fail("I", f"{LEVER_ID}: status {lever.get('status')!r} is not in the enum")
            if not isinstance(lever.get("issue"), int) or isinstance(lever.get("issue"), bool):
                fail("I", f"{LEVER_ID}: issue must be an integer")
    valves = load_json(VALVES, "I")
    if isinstance(valves, dict):
        rows = {
            r.get("id"): r for rows in valves.values() if isinstance(rows, list) for r in rows if isinstance(r, dict)
        }
        for vid in ("STOP_GOVERNOR_CLAUDE_STOP_WIRED", "STOP_GOVERNOR_CODEX_STOP_WIRED"):
            row = rows.get(vid)
            if row is None:
                fail("I", f"armed-valve row {vid} is missing")
            elif row.get("lever") != LEVER_ID or not row.get("needle"):
                fail("I", f"armed-valve row {vid} must cite {LEVER_ID} and carry a needle")


# --------------------------------------------------------------------------- armed (report only)


def report_armed() -> None:
    for label, path, needle in (
        ("claude", ROOT / ".claude" / "settings.json", "stop-governor.sh"),
        ("codex", ROOT / ".codex" / "hooks.json", "stop-governor"),
    ):
        try:
            armed = needle in json.dumps(json.loads(path.read_text(encoding="utf-8")).get("hooks", {}).get("Stop", []))
        except (OSError, ValueError):
            armed = False
        print(f"armed[{label}]: {'ARMED' if armed else 'PARKED (lever ' + LEVER_ID + ')'} - {path.relative_to(ROOT)}")


# --------------------------------------------------------------------------- main


def guarded(check: str, fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except Exception as exc:  # noqa: BLE001 - an unexpected crash is a red check naming its letter
        fail(check, f"check crashed with {type(exc).__name__}: {exc}")
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=str(REGISTRY), help="registry under test (default: the tracked one)")
    ap.add_argument("--snippet", default=str(SNIPPET))
    ap.add_argument("--cases", default=str(FIXTURES))
    ap.add_argument("--armed", action="store_true", help="also report whether each vendor's Stop entry is wired")
    args = ap.parse_args(argv)

    reg = load_json(Path(args.registry), "A")
    try:
        study_text = STUDY.read_text(encoding="utf-8")
    except OSError:
        fail("A", "docs/prompt-control-vocabulary-study.md is unreadable")
        study_text = ""
    governor = guarded("A", load_module, "stop_governor_under_check", GOVERNOR)
    cases = 0
    if isinstance(reg, dict) and governor is not None:
        guarded("A", check_registry_parity, reg, study_text, governor)
        guarded("B", check_promotion, reg)
        guarded("C", check_text, reg, study_text, governor)
        cases = guarded("D", check_behavior, reg, governor, Path(args.cases)) or 0
        guarded("E", check_hook_contract, reg)
        guarded("H", check_params, governor)
    guarded("F", check_codex_shape)
    guarded("G", check_snippet, Path(args.snippet))
    guarded("I", check_lever_and_valves)

    if args.armed:
        report_armed()
    if failures:
        print("STOP-GOVERNOR DRIFT")
        for line in failures:
            print(f"  {line}")
        print("FAILED: check-stop-governor")
        return 1
    rules = (reg or {}).get("rules", {})
    live = sum(1 for r in rules.values() if r.get("mode") == "live")
    print(
        f"check-stop-governor: OK - {len((reg or {}).get('intents', {}))} intents; {len(rules)} rules ({live} live); {cases} cases"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
