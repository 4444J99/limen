#!/usr/bin/env python3
"""Stop governor: the operator's recurring follow-ups, fired at the turn-end boundary.

The operator types the same short asks (continue, verify, closeout, status, next, merge) at the instant an
agent stops. This reads the Stop hook payload plus cheap live git state and, when a registered rule matches,
emits ONE bounded continuation ({"decision": "block", "reason": <prompt>}) written in the operator's own
lowercase lexicon, so the ask arrives without being typed. Hooks cannot type a slash command, so a rule fires
the prompt body the command would carry; `--emit <RULE>` prints the same text for manual use.

The registry is institutio/governance/post-opener-intents.json (stdlib only: this runs as a user hook on an
interpreter that may lack PyYAML). Every rule ships in mode "shadow": it logs would_block and changes nothing
until a promotion block makes it live. The drift predicate is scripts/check-stop-governor.py.

Fail-open by construction: any error, oversize or unparseable input, timeout or unwritable ledger allows the
stop (empty stdout, exit 0). It never raises, never prints message text, and never logs message text.

Hook mode:   stop-governor.py --vendor claude|codex --event Stop     (payload on stdin)
Offline:     --decide FILE [--git-state JSON]   dry-run one payload, no ledger writes
             --emit RULE                        print a rule's continuation text
             --list                             print each rule and its mode
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "post-opener-intents.json"

MAX_STDIN_BYTES = 1 << 20
ITIMER_SECONDS = 6
GIT_TIMEOUT_SECONDS = 2
TAIL_CHARS = 400
GATED_TAIL_CHARS = 600
DEFAULT_MAX_SESSION = 4
DEFAULT_DAILY_CAP = 40
PREFIX = "[stop-governor:"

# The detector vocabulary. The registry's rules must be exactly this set (the predicate holds that).
DETECTORS = ("CONT", "VERIFY", "CLOSE", "MERGE", "NEXT", "STATUS")


@dataclass(frozen=True)
class GitState:
    """What the git probe reports about the session's working tree. All reads, bounded."""

    toplevel: Path | None
    canonical: Path | None
    branch: str = ""
    dirty: bool = False
    ahead: int = 0
    has_upstream: bool = False
    commits_vs_main: int = 0

    @property
    def work_present(self) -> bool:
        return self.dirty or self.ahead > 0 or (not self.has_upstream and self.commits_vs_main > 0)

    @property
    def clean_pushed(self) -> bool:
        return (
            not self.dirty
            and self.has_upstream
            and self.ahead == 0
            and self.branch not in ("", "main", "master", "HEAD")
        )


@dataclass(frozen=True)
class Decision:
    action: str  # allow | block
    code: str
    rules: tuple[str, ...] = ()
    shadow: tuple[str, ...] = ()
    reason: str = ""
    log: bool = False
    fp: str = ""


# --------------------------------------------------------------------------- git probes


def _run_git(args: list[str], cwd: str) -> tuple[int, str]:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", LC_ALL="C")
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
    )
    return proc.returncode, proc.stdout


def probe_git(cwd: str) -> GitState | None:
    """Read-only git facts for `cwd`, or None when it is not a work tree or git cannot answer in time."""
    try:
        code, out = _run_git(["rev-parse", "--show-toplevel", "--git-common-dir"], cwd)
        lines = out.splitlines()
        if code != 0 or len(lines) < 2:
            return None
        toplevel = Path(lines[0])
        common = Path(lines[1])
        if not common.is_absolute():
            common = Path(cwd) / common
        canonical = common.resolve().parent
        branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)[1].strip()
        dirty = bool(_run_git(["status", "--porcelain", "--untracked-files=no"], cwd)[1].strip())
        up_code, up_out = _run_git(["rev-list", "--count", "@{upstream}..HEAD"], cwd)
        has_upstream = up_code == 0
        ahead = int(up_out.strip() or 0) if has_upstream else 0
        commits_vs_main = 0
        if not has_upstream:
            main_code, main_out = _run_git(["rev-list", "--count", "origin/main..HEAD"], cwd)
            commits_vs_main = int(main_out.strip() or 0) if main_code == 0 else 0
        return GitState(toplevel, canonical, branch, dirty, ahead, has_upstream, commits_vs_main)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# --------------------------------------------------------------------------- ledger


class FileLedger:
    """Per-session counters, a day counter, an O_EXCL claim per stop, and the metadata-only event log.

    Layout under the state dir (the canonical checkout's ignored logs/stop-governor):
      <vendor>-<sha16(session)>.json   {"total": n, "rules": {"CONT": n}}
      day-YYYYMMDD.json                {"total": n}
      claims/<sha24>                   one empty file per decided stop (duplicate registration stays silent)
      events.jsonl                     one metadata row per evaluated stop; never message text
    """

    def __init__(self, state_dir: Path):
        self.dir = state_dir

    def _sid(self, vendor: str, session: str) -> Path:
        return self.dir / f"{vendor}-{hashlib.sha256(session.encode()).hexdigest()[:16]}.json"

    def _day(self, now: float) -> Path:
        return self.dir / f"day-{datetime.fromtimestamp(now, UTC).strftime('%Y%m%d')}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _write(path: Path, data: dict[str, Any]) -> None:
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)

    def ready(self) -> bool:
        try:
            (self.dir / "claims").mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False

    def session(self, vendor: str, session: str) -> dict[str, Any]:
        return self._read(self._sid(vendor, session))

    def day_total(self, now: float) -> int:
        value = self._read(self._day(now)).get("total", 0)
        return value if isinstance(value, int) else 0

    def claim(self, key: str) -> bool:
        try:
            fd = os.open(self.dir / "claims" / key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        except OSError:
            return False
        os.close(fd)
        return True

    def record(self, vendor: str, session: str, rules: tuple[str, ...], now: float) -> bool:
        try:
            sess = self.session(vendor, session)
            counts = sess.get("rules") if isinstance(sess.get("rules"), dict) else {}
            for rule in rules:
                counts[rule] = int(counts.get(rule, 0)) + 1
            self._write(self._sid(vendor, session), {"total": int(sess.get("total", 0)) + 1, "rules": counts})
            self._write(self._day(now), {"total": self.day_total(now) + 1})
            return True
        except (OSError, ValueError):
            return False

    def log(self, row: dict[str, Any]) -> None:
        try:
            # Shadow decisions never reach ready(), so the log must make its own directory or no evidence accrues.
            self.dir.mkdir(parents=True, exist_ok=True)
            with open(self.dir / "events.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        except OSError:
            pass


class MemoryLedger:
    """A throwaway ledger for dry runs (`--decide`): same contract, no disk."""

    def __init__(self) -> None:
        self.sessions: dict[tuple[str, str], dict[str, Any]] = {}
        self.day = 0
        self.claims: set[str] = set()
        self.rows: list[dict[str, Any]] = []

    def ready(self) -> bool:
        return True

    def session(self, vendor: str, session: str) -> dict[str, Any]:
        return self.sessions.get((vendor, session), {})

    def day_total(self, now: float) -> int:
        return self.day

    def claim(self, key: str) -> bool:
        if key in self.claims:
            return False
        self.claims.add(key)
        return True

    def record(self, vendor: str, session: str, rules: tuple[str, ...], now: float) -> bool:
        sess = self.sessions.setdefault((vendor, session), {"total": 0, "rules": {}})
        sess["total"] += 1
        for rule in rules:
            sess["rules"][rule] = sess["rules"].get(rule, 0) + 1
        self.day += 1
        return True

    def log(self, row: dict[str, Any]) -> None:
        self.rows.append(row)


# --------------------------------------------------------------------------- registry and text


def load_registry(path: Path = REGISTRY) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("rules"), dict)
        or not isinstance(data.get("lexicon"), dict)
    ):
        return None
    return data


def _word_rx(terms: list[str]) -> re.Pattern[str]:
    # Anchored at a word start, open at the end: "send" also catches "sending". Over-matching only silences.
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(t) for t in terms) + ")", re.IGNORECASE)


def compose_reason(reg: dict[str, Any], rules: tuple[str, ...], fp: str) -> str:
    """The continuation: prefix, each rule's text, the gate clause, and the status suffix when a rule wants it."""
    parts = [str(reg["rules"][r]["text"]) for r in rules]
    parts.append(str(reg["gate_clause"]))
    if any(reg["rules"][r].get("suffix") for r in rules):
        parts.append(str(reg["status_suffix"]))
    return f"{PREFIX}{'+'.join(rules)}@{fp}] " + " ".join(parts)


def stop_key(vendor: str, session: str, message: str) -> tuple[str, str]:
    """(claim key, fingerprint). The claim key is per vendor, so a Claude and a Codex hook on one stop do not
    collide; the fingerprint is vendor-free, so the same stop yields byte-identical reason text on both."""
    digest = hashlib.sha256(message.encode()).hexdigest()
    key = hashlib.sha256(f"{vendor}|{session}|{digest}".encode()).hexdigest()
    return key, hashlib.sha256(f"{session}|{digest}".encode()).hexdigest()[:8]


def _int_env(env: dict[str, str], name: str, default: int) -> int:
    try:
        value = int(env.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


# --------------------------------------------------------------------------- pause marker


def pause_state(canonical: Path | None) -> tuple[str, bool]:
    """(state, merge_prohibited): state is none | wall | fence.

    Reads logs/AUTONOMY_PAUSED with the class parse scripts/session-orient.py uses: an explicit `class:
    fence|wall` wins; a legacy marker without one is a fence only when its reason names a peer. A wall, an
    unreadable marker, or anything unparseable suppresses every rule; a fence suppresses only MERGE.
    """
    if canonical is None:
        return "none", False
    marker = canonical / "logs" / "AUTONOMY_PAUSED"
    if not marker.exists():
        return "none", False
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return "wall", True

    def field(name: str) -> str:
        return next((ln.split(":", 1)[1].strip() for ln in lines if ln.strip().startswith(f"{name}:")), "")

    declared = field("class").lower()
    if declared in ("fence", "wall"):
        is_fence = declared == "fence"
    else:
        is_fence = bool(re.search(r"\bpeer\b|concurren|coordination", field("reason"), re.IGNORECASE))
    merge_blocked = bool(re.search(r"merge", field("prohibitions"), re.IGNORECASE)) or not is_fence
    return ("fence" if is_fence else "wall"), merge_blocked


# --------------------------------------------------------------------------- decide


def _allow(code: str, *, log: bool = False, fp: str = "", shadow: tuple[str, ...] = ()) -> Decision:
    return Decision("allow", code, log=log, fp=fp, shadow=shadow)


def decide(
    payload: dict[str, Any],
    *,
    vendor: str,
    registry: dict[str, Any],
    env: dict[str, str],
    probe: Callable[[str], GitState | None],
    ledger: Any,
    now: float | None = None,
) -> Decision:
    """The whole policy, pure over its inputs. Returns allow(<reason code>) or block with the continuation."""
    now = time.time() if now is None else now
    if payload.get("hook_event_name") != "Stop":
        return _allow("not_stop")
    if env.get("LIMEN_STOP_GOVERNOR", "1") == "0":
        return _allow("kill_switch")
    # A continuation already running (true) or a malformed flag yields; at most one block per Stop event. An
    # absent flag counts as "not continuing": requiring an explicit false would turn a harness that omits the
    # field on ordinary stops into a silent, undetectable no-op. A loop stays bounded either way by the
    # per-rule caps, the session cap and the harness's own consecutive-block cap.
    active = payload.get("stop_hook_active")
    if active is not None and active is not False:
        return _allow("continuation_active")
    mode = payload.get("permission_mode")
    if mode not in (registry.get("permission_modes", {}).get(vendor) or []):
        return _allow(f"mode:{mode}")
    if env.get("CLAUDE_JOB_DIR"):
        return _allow("background_job")
    if payload.get("session_crons"):
        return _allow("loop_owns_cadence")

    message = payload.get("last_assistant_message")
    message = message if isinstance(message, str) else ""
    if not message.strip():
        return _allow("empty")
    if "CLOSEOUT COMPLETE" in message:
        return _allow("fixed_point")
    if "BLOCKED:" in message:
        return _allow("blocked_once")

    lex = registry["lexicon"]
    tail = message[-TAIL_CHARS:]
    claim = bool(_word_rx(lex["completion_claim"]).search(tail))
    evidence = any(term.lower() in tail.lower() for term in lex["exit_evidence"])
    candidates: dict[str, bool] = {
        "CONT": any(term.lower() in tail.lower() for term in lex["permission_allowlist"]),
        "VERIFY": claim and not evidence,
        "CLOSE": claim,
        "MERGE": any(term.lower() in tail.lower() for term in lex["pr_mention"]) or bool(re.search(r"#\d{2,}", tail)),
        "NEXT": claim and evidence and not re.search(r"(?im)^\s*" + re.escape(lex["next_line"]), message),
        "STATUS": claim and lex["needs_you_line"] not in message.lower(),
    }
    wanted = [r for r in DETECTORS if candidates[r] and r in registry["rules"]]
    if not wanted:
        return _allow("no_signal")

    cwd = payload.get("cwd")
    git = probe(cwd) if isinstance(cwd, str) and cwd else None
    scope = registry.get("scope_marker", "")
    if git is None or git.toplevel is None or not (git.toplevel / scope).is_file():
        return _allow("out_of_scope")
    canonical = git.canonical
    if canonical is not None and (canonical / "logs" / "STOP_GOVERNOR_OFF").exists():
        return _allow("kill_switch")

    session = payload.get("session_id")
    sid = str(session) if session else ""
    key, fp = stop_key(vendor, sid, message)

    pause, merge_blocked = pause_state(canonical)
    if pause == "wall":
        return _allow("paused_wall", log=True, fp=fp)

    # Rules that need git state to apply.
    matched: list[str] = []
    for rule in wanted:
        if rule == "VERIFY" and not git.work_present:
            continue
        if rule == "MERGE" and (merge_blocked or not git.clean_pushed):
            continue
        if rule == "NEXT" and git.dirty:
            continue
        matched.append(rule)
    if "CONT" in matched:
        # The agent is asking to continue, not finishing: the question outranks a stray completion word.
        # A question about something that sends, deletes, spends or leaks is the operator's, never nudged.
        if registry["rules"]["CONT"].get("deny_gated") and _word_rx(lex["deny_terms"]).search(
            message[-GATED_TAIL_CHARS:]
        ):
            return _allow("gated_tail", log=True, fp=fp)
        matched = ["CONT"]
    if not matched:
        return _allow("no_signal")

    if vendor == "codex" and git.work_present:
        # Host admission's bounded closeout owns a first stop with unpublished work; never two blocks per event.
        return _allow("codex_admission_owns", log=True, fp=fp, shadow=tuple(matched))
    if not sid:
        return _allow("no_session", log=True, fp=fp, shadow=tuple(matched))

    sess = ledger.session(vendor, sid)
    used = sess.get("rules") if isinstance(sess.get("rules"), dict) else {}
    after_caps = [r for r in matched if int(used.get(r, 0)) < int(registry["rules"][r].get("cap", 1))]
    live = [r for r in after_caps if registry["rules"][r].get("mode") == "live"]
    shadow = tuple(r for r in after_caps if r not in live)
    if not live:
        # A cap that fired is the thing to see when tuning, so it outranks the shadow log line.
        code = "intent_cap" if len(after_caps) < len(matched) else "would_block"
        return Decision("allow", code, shadow=shadow, log=True, fp=fp)

    # Order: VERIFY then CLOSE compose into one reason; otherwise the first live rule in detector order.
    chosen = (
        tuple(r for r in ("VERIFY", "CLOSE") if r in live) if ("VERIFY" in live and "CLOSE" in live) else (live[0],)
    )
    if int(sess.get("total", 0)) >= _int_env(env, "LIMEN_STOP_GOVERNOR_MAX_SESSION", DEFAULT_MAX_SESSION):
        return _allow("session_cap", log=True, fp=fp, shadow=tuple(matched))
    if ledger.day_total(now) >= _int_env(env, "LIMEN_STOP_GOVERNOR_DAILY_CAP", DEFAULT_DAILY_CAP):
        return _allow("daily_cap", log=True, fp=fp, shadow=tuple(matched))
    if not ledger.ready():
        return _allow("no_ledger", shadow=tuple(matched))
    if not ledger.claim(key[:24]):
        return _allow("dup_claim")
    if not ledger.record(vendor, sid, chosen, now):
        return _allow("no_ledger", log=True, fp=fp)
    return Decision(
        "block", "continue", rules=chosen, shadow=shadow, reason=compose_reason(registry, chosen, fp), log=True, fp=fp
    )


def render(decision: Decision) -> str:
    """The only bytes a Stop hook may print: nothing, or one {decision, reason} object."""
    if decision.action != "block":
        return ""
    return json.dumps({"decision": "block", "reason": decision.reason}, ensure_ascii=False)


def log_row(vendor: str, payload: dict[str, Any], decision: Decision, now: float) -> dict[str, Any]:
    session = payload.get("session_id")
    return {
        "ts": datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vendor": vendor,
        "sid": hashlib.sha256(str(session).encode()).hexdigest()[:8] if session else "",
        "mode": payload.get("permission_mode"),
        "action": "would_block" if decision.code == "would_block" else decision.action,
        "code": decision.code,
        "rules": list(decision.rules),
        "shadow": list(decision.shadow),
        "fp": decision.fp,
    }


# --------------------------------------------------------------------------- fixtures (shared with the predicate)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        out[key] = _deep_merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def run_case(case: dict[str, Any], workdir: Path, registry: dict[str, Any] | None = None) -> tuple[Decision, str]:
    """Run one fixture through decide() against a throwaway tree and ledger under `workdir`."""
    base = registry if registry is not None else load_registry()
    if base is None:
        raise RuntimeError("registry unavailable")
    # Fixtures are self-contained: every rule starts shadow and a case patches in the live ones it needs, so
    # promoting a rule in the shipped registry never turns a fixture red.
    shadowed = _deep_merge(base, {"rules": {name: {"mode": "shadow"} for name in base.get("rules", {})}})
    reg = _deep_merge(shadowed, case.get("registry_patch") or {})
    canonical = workdir / "canonical"
    (canonical / "logs").mkdir(parents=True, exist_ok=True)
    for rel, text in (case.get("files") or {}).items():
        target = canonical / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    for rel in case.get("dirs") or []:  # a directory where a file is expected reads as an unreadable marker
        (canonical / rel).mkdir(parents=True, exist_ok=True)
    spec = case.get("git", "default")
    git: GitState | None
    if spec is None:
        git = None
    else:
        merged = {"branch": "feat/x", "dirty": False, "ahead": 0, "has_upstream": True, "commits_vs_main": 0}
        merged.update(spec if isinstance(spec, dict) else {})
        toplevel = canonical
        if not merged.pop("out_of_scope", False):
            marker = canonical / reg.get("scope_marker", "")
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("{}", encoding="utf-8")
        git = GitState(toplevel=toplevel, canonical=canonical, **merged)
    state = workdir / "state"
    if case.get("unwritable_state"):  # a file where the state dir should be: every ledger write fails
        state.write_text("", encoding="utf-8")
    ledger = FileLedger(state)
    pre = case.get("ledger_pre") or {}
    vendor = case.get("vendor", "claude")
    sid = str(case["payload"].get("session_id", ""))
    now = case.get("now", 1_700_000_000.0)
    if pre:
        ledger.ready()
        if "session" in pre:
            ledger._write(ledger._sid(vendor, sid), pre["session"])
        if "day_total" in pre:
            ledger._write(ledger._day(now), {"total": pre["day_total"]})
        if pre.get("claim_current"):
            message = case["payload"].get("last_assistant_message") or ""
            ledger.claim(stop_key(vendor, sid, message)[0][:24])
    decision = decide(
        case["payload"],
        vendor=vendor,
        registry=reg,
        env=dict(case.get("env") or {}),
        probe=lambda _cwd: git,
        ledger=ledger,
        now=now,
    )
    return decision, render(decision)


def case_failures(case: dict[str, Any], decision: Decision, output: str) -> list[str]:
    """Compare a decision with the fixture's hand-written expectation; empty list means it holds."""
    expect = case["expect"]
    bad: list[str] = []
    if decision.action != expect["action"]:
        bad.append(f"action {decision.action!r} != {expect['action']!r}")
    if decision.code != expect["code"]:
        bad.append(f"code {decision.code!r} != {expect['code']!r}")
    if "rules" in expect and list(decision.rules) != expect["rules"]:
        bad.append(f"rules {list(decision.rules)} != {expect['rules']}")
    bad += [f"shadow lacks {r}" for r in expect.get("shadow_has", []) if r not in decision.shadow]
    bad += [f"shadow has {r}" for r in expect.get("shadow_missing", []) if r in decision.shadow]
    if expect.get("output_empty") and output:
        bad.append("output is not empty")
    if "reason_prefix" in expect and not decision.reason.startswith(expect["reason_prefix"]):
        bad.append(f"reason does not start with {expect['reason_prefix']!r}")
    bad += [f"reason lacks {t!r}" for t in expect.get("reason_has", []) if t not in decision.reason]
    if decision.action == "block":
        try:
            shape = json.loads(output)
        except ValueError:
            shape = None
        if not isinstance(shape, dict) or set(shape) != {"decision", "reason"} or shape.get("decision") != "block":
            bad.append("output is not exactly one {decision: block, reason} object")
    elif output:
        bad.append("an allow printed output")
    return bad


# --------------------------------------------------------------------------- entry points


class _Budget(Exception):
    pass


def _on_alarm(_signum: int, _frame: Any) -> None:
    raise _Budget


def _canonical_state_dir(cwd: str, override: str | None) -> Path | None:
    if override:
        return Path(override)
    git = probe_git(cwd)
    return None if git is None or git.canonical is None else git.canonical / "logs" / "stop-governor"


def run_hook(args: argparse.Namespace) -> int:
    """Hook mode. Prints nothing or one JSON object, and always returns 0."""
    try:
        if hasattr(signal, "setitimer"):
            signal.signal(signal.SIGALRM, _on_alarm)
            signal.setitimer(signal.ITIMER_REAL, ITIMER_SECONDS)
        raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
        if len(raw) > MAX_STDIN_BYTES:
            return 0
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or args.event != "Stop":
            return 0
        registry = load_registry(Path(args.registry) if args.registry else REGISTRY)
        if registry is None:
            return 0
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
        state_dir = _canonical_state_dir(cwd, args.state_dir)
        ledger: Any = FileLedger(state_dir) if state_dir is not None else MemoryLedger()
        now = time.time()
        decision = decide(
            payload,
            vendor=args.vendor,
            registry=registry,
            env=dict(os.environ),
            probe=probe_git,
            ledger=ledger,
            now=now,
        )
        if decision.log:
            ledger.log(log_row(args.vendor, payload, decision, now))
        out = render(decision)
        if out:
            sys.stdout.write(out)
            sys.stdout.flush()
    except BaseException:  # noqa: BLE001 - a Stop hook must never fail the session, not even on a budget alarm
        return 0
    finally:
        if hasattr(signal, "setitimer"):
            signal.setitimer(signal.ITIMER_REAL, 0)
    return 0


def _fixed_probe(git: GitState | None) -> Callable[[str], GitState | None]:
    """A probe that reports the supplied state whatever the cwd (offline replay and tests)."""

    def probe(_cwd: str) -> GitState | None:
        return git

    return probe


def _cmd_decide(args: argparse.Namespace) -> int:
    registry = load_registry(Path(args.registry) if args.registry else REGISTRY)
    if registry is None:
        print("stop-governor: registry unavailable", file=sys.stderr)
        return 2
    payload = json.loads(Path(args.decide).read_text(encoding="utf-8"))
    state = json.loads(args.git_state) if args.git_state else None
    if state is not None:
        probe = _fixed_probe(
            GitState(
                toplevel=Path(state["toplevel"]) if state.get("toplevel") else None,
                canonical=Path(state["canonical"]) if state.get("canonical") else None,
                **{k: state[k] for k in ("branch", "dirty", "ahead", "has_upstream", "commits_vs_main") if k in state},
            )
        )
    else:
        probe = probe_git
    decision = decide(
        payload, vendor=args.vendor, registry=registry, env=dict(os.environ), probe=probe, ledger=MemoryLedger()
    )
    print(
        json.dumps(
            {
                "action": decision.action,
                "code": decision.code,
                "rules": list(decision.rules),
                "shadow": list(decision.shadow),
                "output": render(decision),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--vendor", choices=("claude", "codex"), default="claude")
    parser.add_argument("--event", default="Stop")
    parser.add_argument("--registry", help="registry override (tests)")
    parser.add_argument(
        "--state-dir", help="ledger directory override (tests); default is <canonical>/logs/stop-governor"
    )
    parser.add_argument("--decide", metavar="PAYLOAD.json", help="dry-run one payload, no ledger writes")
    parser.add_argument("--git-state", metavar="JSON", help="with --decide: supply git state instead of probing")
    parser.add_argument("--emit", metavar="RULE", help="print a rule's continuation text")
    parser.add_argument("--list", action="store_true", help="print each rule and its mode")
    args = parser.parse_args(argv)

    if args.list or args.emit or args.decide:
        registry = load_registry(Path(args.registry) if args.registry else REGISTRY)
        if registry is None:
            print("stop-governor: registry unavailable", file=sys.stderr)
            return 2
        if args.list:
            for name, rule in registry["rules"].items():
                print(f"{name}\t{rule.get('mode')}\tcap={rule.get('cap')}\tintent={rule.get('intent')}")
            return 0
        if args.emit:
            if args.emit not in registry["rules"]:
                print(f"stop-governor: unknown rule {args.emit}", file=sys.stderr)
                return 2
            print(compose_reason(registry, (args.emit,), "manual"))
            return 0
        return _cmd_decide(args)
    return run_hook(args)


if __name__ == "__main__":
    sys.exit(main())
