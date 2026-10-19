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

Shape of a decision: prefilter() runs every check that needs no I/O (event, kill switch, mode, fleet markers,
the message itself), so a read-only or irrelevant stop pays nothing; only a stop with a lexical candidate
probes git, once; decide_with_state() then arbitrates the rules, enforces caps atomically under a lock, and
returns allow(<reason code>) or block(<continuation>).

Fail-open by construction: any error, oversize or unparseable input, timeout or unwritable ledger allows the
stop (empty stdout, exit 0). It never raises, never prints message text, and never logs message text.

Hook mode:   stop-governor.py --vendor claude|codex --event Stop     (payload on stdin)
Offline:     --decide FILE [--git-state JSON]   dry-run one payload, no ledger writes
             --emit RULE                        print a rule's continuation text
             --list                             print each rule and its mode
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # POSIX advisory locking; without it the ledger runs unlocked rather than failing
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "post-opener-intents.json"

MAX_STDIN_BYTES = 1 << 20
ITIMER_SECONDS = 6
GIT_CALL_TIMEOUT_SECONDS = 2
GIT_BUDGET_SECONDS = 4.5
LOCK_WAIT_SECONDS = 1.0
TAIL_CHARS = 400
GATED_TAIL_CHARS = 600
SEARCH_CHARS = 2000
DEFAULT_MAX_SESSION = 4
DEFAULT_DAILY_CAP = 40
PREFIX = "[stop-governor:"
KILL_VALUES = ("0", "false", "off", "no")
# Markers scripts dispatch.py sets on every fleet lane (bounded, receipted, not an interactive session).
FLEET_ENV = ("LIMEN_WORK_KEY", "LIMEN_TASK_ID", "LIMEN_ATTEMPT_DEADLINE")
# Git picks these up from the environment and would silently redirect a probe made in another directory.
GIT_ENV_STRIP = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)

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
    upstream_gone: bool = False

    @property
    def work_present(self) -> bool:
        """Unpublished work: tracked or untracked changes, commits ahead of the branch's own upstream, or
        commits on a branch with no upstream of its own. A gone upstream (a squash-merged, deleted remote
        branch) is unknown, not work."""
        if self.dirty or self.ahead > 0:
            return True
        return not self.has_upstream and not self.upstream_gone and self.commits_vs_main > 0

    @property
    def clean_pushed(self) -> bool:
        return (
            not self.dirty
            and self.has_upstream
            and self.ahead == 0
            and self.branch not in ("", "main", "master", "HEAD")
        )


@dataclass(frozen=True)
class Lexical:
    """What the message alone says: computed with no I/O, so a stop that needs nothing pays nothing."""

    message: str
    wanted: tuple[str, ...]
    gated: bool


@dataclass(frozen=True)
class Decision:
    action: str  # allow | block
    code: str
    rules: tuple[str, ...] = ()
    shadow: tuple[str, ...] = ()
    reason: str = ""
    log: bool = False
    fp: str = ""
    # Carried for the caller's logging only; excluded from equality and repr.
    ledger: Any = field(default=None, compare=False, repr=False)
    key: str = field(default="", compare=False, repr=False)


# --------------------------------------------------------------------------- git probes


def _run_git(args: list[str], cwd: str, deadline: float) -> tuple[int, str]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired("git", 0)
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_STRIP}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    proc = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=min(GIT_CALL_TIMEOUT_SECONDS, remaining),
        check=False,
    )
    return proc.returncode, proc.stdout


def probe_git(cwd: str) -> GitState | None:
    """Read-only git facts for `cwd` in two or three bounded calls, or None when it is not a work tree or git
    cannot answer in time. One `status --porcelain=v2 --branch` carries the branch, its upstream, ahead count and
    every tracked or untracked change."""
    try:
        deadline = time.monotonic() + GIT_BUDGET_SECONDS
        code, out = _run_git(["rev-parse", "--show-toplevel", "--git-common-dir"], cwd, deadline)
        lines = out.splitlines()
        if code != 0 or len(lines) < 2:
            return None
        toplevel = Path(lines[0])
        common = Path(lines[1])
        if not common.is_absolute():
            common = Path(cwd) / common
        common = common.resolve()
        # The shared checkout is the parent of its .git; any other layout (separate git dir, bare clone) falls
        # back to this tree so the marker, kill switch and ledger are looked up beside the files being worked on.
        canonical = common.parent if common.name == ".git" else toplevel

        code, out = _run_git(["status", "--porcelain=v2", "--branch", "--untracked-files=normal"], cwd, deadline)
        if code != 0:
            return None
        branch, upstream, ahead, has_ab, dirty = "", "", 0, False, False
        for line in out.splitlines():
            if line.startswith("# branch.head "):
                branch = line[len("# branch.head ") :].strip()
            elif line.startswith("# branch.upstream "):
                upstream = line[len("# branch.upstream ") :].strip()
            elif line.startswith("# branch.ab "):
                ahead, has_ab = int(line.split()[2]), True
            elif not line.startswith("#"):
                dirty = True
        if branch == "(detached)":
            branch = "HEAD"
        upstream_gone = bool(upstream) and not has_ab
        # A branch that merely tracks origin/main (a worktree cut from it) has no upstream of its own.
        own_upstream = bool(upstream) and has_ab and upstream.rsplit("/", 1)[-1] not in ("main", "master")
        commits_vs_main = 0
        if not own_upstream and not upstream_gone:
            if upstream and has_ab:
                commits_vs_main = ahead
            else:
                main_code, main_out = _run_git(["rev-list", "--count", "origin/main..HEAD"], cwd, deadline)
                commits_vs_main = int(main_out.strip() or 0) if main_code == 0 else 0
        return GitState(
            toplevel,
            canonical,
            branch,
            dirty,
            ahead if own_upstream else 0,
            own_upstream,
            commits_vs_main,
            upstream_gone,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


# --------------------------------------------------------------------------- ledger


def check_caps(
    session: dict[str, Any],
    day_total: int,
    rules: tuple[str, ...],
    caps: dict[str, int],
    max_session: int,
    daily_cap: int,
) -> str:
    """The cap verdict shared by every ledger: '' when the rules may fire, else the reason code."""
    used = session.get("rules") if isinstance(session.get("rules"), dict) else {}
    if any(int(used.get(r, 0)) >= int(caps.get(r, 1)) for r in rules):
        return "intent_cap"
    if int(session.get("total", 0)) >= max_session:
        return "session_cap"
    if day_total >= daily_cap:
        return "daily_cap"
    return ""


class FileLedger:
    """Per-session counters, a day counter, an O_EXCL claim per stop, and the metadata-only event log.

    Layout under the state dir (the canonical checkout's ignored logs/stop-governor):
      <vendor>-<sha16(session)>.json   {"total": n, "rules": {"CONT": n}}
      day-YYYYMMDD.json                {"total": n}
      claims/<sha24>                   one empty file per decided stop (duplicate registration stays silent)
      claims/log-<sha20>               one per logged stop (a duplicate registration logs once)
      .lock                            flock target: check, claim and record happen as one step
      events.jsonl                     one metadata row per evaluated stop; never message text
    """

    def __init__(self, state_dir: Path):
        self.dir = state_dir

    def _sid(self, vendor: str, session: str) -> Path:
        return self.dir / f"{vendor}-{hashlib.sha256(session.encode()).hexdigest()[:16]}.json"

    def _day(self, now: float) -> Path:
        return self.dir / f"day-{datetime.fromtimestamp(now, timezone.utc).strftime('%Y%m%d')}.json"

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
        except OSError:  # includes FileExistsError: someone already decided this stop
            return False
        os.close(fd)
        return True

    @contextlib.contextmanager
    def _locked(self) -> Iterator[bool]:
        """Hold the ledger lock; yield False when it could not be taken in time (the caller fails open)."""
        if fcntl is None:
            yield True
            return
        try:
            fd = os.open(self.dir / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        except OSError:
            yield False
            return
        try:
            deadline = time.monotonic() + LOCK_WAIT_SECONDS
            held = False
            while not held:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held = True
                except OSError:
                    if time.monotonic() >= deadline:
                        break
                    time.sleep(0.01)
            yield held
        finally:
            os.close(fd)  # closing the descriptor releases the lock

    def reserve(
        self,
        vendor: str,
        session: str,
        rules: tuple[str, ...],
        key: str,
        now: float,
        caps: dict[str, int],
        max_session: int,
        daily_cap: int,
    ) -> str:
        """Check the caps, claim the stop and charge the counters as ONE step. 'ok' or the reason it may not."""
        if not self.ready():
            return "no_ledger"
        with self._locked() as held:
            if not held:
                return "no_ledger"
            verdict = check_caps(
                self.session(vendor, session), self.day_total(now), rules, caps, max_session, daily_cap
            )
            if verdict:
                return verdict
            if not self.claim(key):
                return "dup_claim"
            try:
                sess = self.session(vendor, session)
                counts = sess.get("rules") if isinstance(sess.get("rules"), dict) else {}
                for rule in rules:
                    counts[rule] = int(counts.get(rule, 0)) + 1
                self._write(self._sid(vendor, session), {"total": int(sess.get("total", 0)) + 1, "rules": counts})
                self._write(self._day(now), {"total": self.day_total(now) + 1})
            except (OSError, ValueError):
                return "no_ledger"
            return "ok"

    def claim_log(self, key: str) -> bool:
        """True the first time a stop is logged, so a duplicate registration cannot inflate the evidence."""
        return self.ready() and self.claim(f"log-{key[:20]}")

    def log(self, row: dict[str, Any]) -> None:
        try:
            # Shadow decisions never reserve, so the log must make its own directory or no evidence accrues.
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

    def reserve(
        self,
        vendor: str,
        session: str,
        rules: tuple[str, ...],
        key: str,
        now: float,
        caps: dict[str, int],
        max_session: int,
        daily_cap: int,
    ) -> str:
        verdict = check_caps(self.session(vendor, session), self.day, rules, caps, max_session, daily_cap)
        if verdict:
            return verdict
        if not self.claim(key):
            return "dup_claim"
        sess = self.sessions.setdefault((vendor, session), {"total": 0, "rules": {}})
        sess["total"] += 1
        for rule in rules:
            sess["rules"][rule] = sess["rules"].get(rule, 0) + 1
        self.day += 1
        return "ok"

    def claim_log(self, key: str) -> bool:
        return self.claim(f"log-{key[:20]}")

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


def _phrase_rx(terms: list[str]) -> re.Pattern[str]:
    """Whole-word match for each phrase (spaces match any run of whitespace)."""
    body = "|".join(re.escape(t).replace(r"\ ", r"\s+") for t in terms)
    return re.compile(r"(?<![A-Za-z0-9])(?:" + body + r")(?![A-Za-z0-9])", re.IGNORECASE)


def _pattern_rx(patterns: list[str]) -> re.Pattern[str]:
    """Alternation of regex fragments, anchored at a word start AND a word end, case-insensitive: 'post' is
    caught as post/posted/posting but not inside 'postgres', and 'tokens?' not inside 'tokenizer'."""
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(patterns) + r")(?![A-Za-z0-9])", re.IGNORECASE)


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

    def field_of(name: str) -> str:
        return next((ln.split(":", 1)[1].strip() for ln in lines if ln.strip().startswith(f"{name}:")), "")

    declared = field_of("class").lower()
    if declared in ("fence", "wall"):
        is_fence = declared == "fence"
    else:
        is_fence = bool(re.search(r"\bpeer\b|concurren|coordination", field_of("reason"), re.IGNORECASE))
    merge_blocked = bool(re.search(r"merge", field_of("prohibitions"), re.IGNORECASE)) or not is_fence
    return ("fence" if is_fence else "wall"), merge_blocked


# --------------------------------------------------------------------------- decide


def _allow(
    code: str,
    *,
    log: bool = False,
    fp: str = "",
    shadow: tuple[str, ...] = (),
    ledger: Any = None,
    key: str = "",
) -> Decision:
    return Decision("allow", code, log=log, fp=fp, shadow=shadow, ledger=ledger, key=key)


def _claims_completion(tail: str, lex: dict[str, Any]) -> bool:
    """A completion word that is not negated within the three words before it ('not done', "isn't finished")."""
    completion = _phrase_rx(lex["completion_claim"])
    negation = re.compile(
        r"(?:(?<![A-Za-z0-9])(?:" + "|".join(re.escape(w) for w in lex["negation"] if w != "n't") + r")|n't)"
        r"\s+(?:\w+\s+){0,2}$",
        re.IGNORECASE,
    )
    return any(not negation.search(tail[max(0, m.start() - 40) : m.start()]) for m in completion.finditer(tail))


def prefilter(
    payload: dict[str, Any], *, vendor: str, registry: dict[str, Any], env: dict[str, str]
) -> Decision | Lexical:
    """Every check that needs no I/O, cheapest first. A Decision means 'allow, and nothing was probed'."""
    if payload.get("hook_event_name") != "Stop":
        return _allow("not_stop")
    if env.get("LIMEN_STOP_GOVERNOR", "1").strip().lower() in KILL_VALUES:
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
    # Claude Code sets this to 1 in an attended session and 0 under `claude -p` (observed on 2.1.303; it is NOT on
    # the documented env-vars page). It is only ever used to YIELD on an explicit 0, so if it disappears the
    # governor falls back to today's behavior instead of failing.
    if env.get("CLAUDE_CODE_SESSION_ATTENDED") == "0":
        return _allow("unattended")
    if any(env.get(name) for name in FLEET_ENV):
        return _allow("fleet_lane")
    if env.get("CLAUDE_JOB_DIR"):
        return _allow("background_job")
    if payload.get("session_crons"):
        return _allow("loop_owns_cadence")
    if payload.get("background_tasks"):
        return _allow("background_tasks")

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
    recent = message[-SEARCH_CHARS:]
    claim = _claims_completion(tail, lex)
    failed = bool(_phrase_rx(lex["failure_terms"]).search(tail))
    evidence = bool(_phrase_rx(lex["exit_evidence"]).search(tail)) and not failed
    asks_question = bool(re.search(r"\?[\s*_\"')\]>`]*\Z", message))
    cont = (asks_question and bool(_phrase_rx(lex["permission_questions"]).search(tail))) or bool(
        _phrase_rx(lex["handbacks"]).search(tail)
    )
    names_pr = bool(_pattern_rx(lex["pr_patterns"]).search(tail)) and not _pattern_rx(lex["hold_patterns"]).search(tail)
    next_given = bool(re.search(lex["next_line"], recent))
    candidates = {
        "CONT": cont,
        "VERIFY": claim and not evidence,
        "CLOSE": claim,
        "MERGE": names_pr,
        "NEXT": claim and evidence and not next_given,
        "STATUS": claim and lex["needs_you_line"] not in recent.lower(),
    }
    wanted = tuple(r for r in DETECTORS if candidates[r] and r in registry["rules"])
    if not wanted:
        return _allow("no_signal")
    gated = bool(_pattern_rx(lex["deny_patterns"]).search(message[-GATED_TAIL_CHARS:]))
    return Lexical(message, wanted, gated)


def decide_with_state(
    payload: dict[str, Any],
    lexical: Lexical,
    *,
    vendor: str,
    registry: dict[str, Any],
    env: dict[str, str],
    git: GitState | None,
    ledger_factory: Callable[[GitState], Any],
    now: float,
) -> Decision:
    """Everything that needs the tree or the ledger. `git` was probed once, by the caller."""
    scope = registry.get("scope_marker", "")
    if git is None or git.toplevel is None or not (git.toplevel / scope).is_file():
        return _allow("out_of_scope")
    canonical = git.canonical
    if canonical is not None and (canonical / "logs" / "STOP_GOVERNOR_OFF").exists():
        return _allow("kill_switch")

    session = payload.get("session_id")
    sid = str(session) if session else ""
    key, fp = stop_key(vendor, sid, lexical.message)
    ledger = ledger_factory(git)
    if ledger is None:
        return _allow("no_ledger")
    pause, merge_blocked = pause_state(canonical)
    if pause == "wall":
        return _allow("paused_wall", log=True, fp=fp, ledger=ledger, key=key)

    rules = registry["rules"]
    sess = ledger.session(vendor, sid) if sid else {}
    used = sess.get("rules") if isinstance(sess.get("rules"), dict) else {}

    matched: list[str] = []
    for rule in lexical.wanted:
        if rule == "VERIFY" and not git.work_present:
            continue
        if rule == "MERGE" and (merge_blocked or not git.clean_pushed):
            continue
        if rule == "NEXT" and git.dirty:
            continue
        matched.append(rule)

    if "CONT" in matched:
        cont = rules["CONT"]
        live_open = cont.get("mode") == "live" and int(used.get("CONT", 0)) < int(cont.get("cap", 1))
        gated = bool(cont.get("deny_gated")) and lexical.gated
        if "MERGE" in matched:
            matched.remove("CONT")  # a merge question is MERGE's domain; scripts/merge-policy.sh decides
        elif live_open:
            if gated:
                return _allow("gated_tail", log=True, fp=fp, ledger=ledger, key=key)
            matched = ["CONT"]  # the agent is asking, not finishing: the question outranks a stray completion word
        elif gated:
            matched.remove("CONT")  # a shadow or spent CONT neither collapses live rules nor logs a gated ask
    if not matched:
        return _allow("no_signal")
    if not sid:
        return _allow("no_session", log=True, fp=fp, shadow=tuple(matched), ledger=ledger, key=key)

    caps = {r: int(rules[r].get("cap", 1)) for r in matched}
    after_caps = [r for r in matched if int(used.get(r, 0)) < caps[r]]
    live = [r for r in after_caps if rules[r].get("mode") == "live"]
    shadow = tuple(r for r in after_caps if r not in live)
    if not live:
        # A cap that fired is the thing to see when tuning, so it outranks the shadow log line.
        code = "intent_cap" if len(after_caps) < len(matched) else "would_block"
        return Decision("allow", code, shadow=shadow, log=True, fp=fp, ledger=ledger, key=key)

    # VERIFY then CLOSE compose into one reason; otherwise the first live rule in detector order.
    chosen = (
        tuple(r for r in ("VERIFY", "CLOSE") if r in live) if ("VERIFY" in live and "CLOSE" in live) else (live[0],)
    )
    verdict = ledger.reserve(
        vendor,
        sid,
        chosen,
        key[:24],
        now,
        caps,
        _int_env(env, "LIMEN_STOP_GOVERNOR_MAX_SESSION", DEFAULT_MAX_SESSION),
        _int_env(env, "LIMEN_STOP_GOVERNOR_DAILY_CAP", DEFAULT_DAILY_CAP),
    )
    if verdict != "ok":
        return _allow(
            verdict, log=verdict not in ("dup_claim", "no_ledger"), fp=fp, shadow=tuple(matched), ledger=ledger, key=key
        )
    return Decision(
        "block",
        "continue",
        rules=chosen,
        shadow=shadow,
        reason=compose_reason(registry, chosen, fp),
        log=True,
        fp=fp,
        ledger=ledger,
        key=key,
    )


def decide(
    payload: dict[str, Any],
    *,
    vendor: str,
    registry: dict[str, Any],
    env: dict[str, str],
    probe: Callable[[str], GitState | None],
    ledger_factory: Callable[[GitState], Any],
    now: float | None = None,
) -> Decision:
    """The whole policy over injected probes: prefilter, one git probe, then arbitration."""
    now = time.time() if now is None else now
    lexical = prefilter(payload, vendor=vendor, registry=registry, env=env)
    if isinstance(lexical, Decision):
        return lexical
    cwd = payload.get("cwd")
    git = probe(cwd) if isinstance(cwd, str) and cwd else None
    return decide_with_state(
        payload, lexical, vendor=vendor, registry=registry, env=env, git=git, ledger_factory=ledger_factory, now=now
    )


def render(decision: Decision) -> str:
    """The only bytes a Stop hook may print: nothing, or one {decision, reason} object. ASCII-only, so a
    non-UTF-8 stdout cannot turn a decided block into a swallowed one after the counters were charged."""
    if decision.action != "block":
        return ""
    return json.dumps({"decision": "block", "reason": decision.reason}, ensure_ascii=True)


def log_row(vendor: str, payload: dict[str, Any], decision: Decision, now: float) -> dict[str, Any]:
    session = payload.get("session_id")
    return {
        "ts": datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
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
        if not merged.pop("out_of_scope", False):
            marker = canonical / reg.get("scope_marker", "")
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("{}", encoding="utf-8")
        git = GitState(toplevel=canonical, canonical=canonical, **merged)
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
        ledger_factory=lambda _git: ledger,
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
        if not output.isascii():
            bad.append("output is not ASCII-only")
    elif output:
        bad.append("an allow printed output")
    return bad


# --------------------------------------------------------------------------- entry points


class _Budget(Exception):
    pass


def _on_alarm(_signum: int, _frame: Any) -> None:
    raise _Budget


def _hook_ledger_factory(state_dir: str | None) -> Callable[[GitState], Any]:
    """Hook mode only ever uses the file ledger; no resolvable state dir means no ledger and so no block."""

    def factory(git: GitState) -> Any:
        if state_dir:
            return FileLedger(Path(state_dir))
        if git.canonical is not None:
            return FileLedger(git.canonical / "logs" / "stop-governor")
        return None

    return factory


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
        env = dict(os.environ)
        lexical = prefilter(payload, vendor=args.vendor, registry=registry, env=env)
        if isinstance(lexical, Decision):
            return 0  # nothing to say and nothing probed: plan mode, the kill switch, a quiet stop all end here
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else os.getcwd()
        now = time.time()
        decision = decide_with_state(
            payload,
            lexical,
            vendor=args.vendor,
            registry=registry,
            env=env,
            git=probe_git(cwd),
            ledger_factory=_hook_ledger_factory(args.state_dir),
            now=now,
        )
        out = render(decision)
        if out:
            sys.stdout.write(out)
            sys.stdout.flush()
        # Log after the output left, so a row says "block" only for a block the model could have received.
        if decision.log and decision.ledger is not None and decision.ledger.claim_log(decision.key):
            decision.ledger.log(log_row(args.vendor, payload, decision, now))
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
                **{
                    k: state[k]
                    for k in ("branch", "dirty", "ahead", "has_upstream", "commits_vs_main", "upstream_gone")
                    if k in state
                },
            )
        )
    else:
        probe = probe_git
    ledger = MemoryLedger()
    decision = decide(
        payload,
        vendor=args.vendor,
        registry=registry,
        env=dict(os.environ),
        probe=probe,
        ledger_factory=lambda _git: ledger,
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
