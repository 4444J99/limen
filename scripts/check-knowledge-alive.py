#!/usr/bin/env python3
"""Knowledge-alive predicate: is the whole private-archive loop alive, end to end?

Exit 0 means the loop is alive, 1 means it is not (the last line names the first failing check), and 2
means the environment is unusable (a required tool or store is missing). A missing tool is never a
silent skip.

  python3 scripts/check-knowledge-alive.py --fixture    # hermetic: synthetic exports in a temporary store
  python3 scripts/check-knowledge-alive.py --live       # read-only over the registered store and ledger
  python3 scripts/check-knowledge-alive.py --live --write-receipt   # also file the counts-only receipt

The loop being proven:

  raw exports -> normalized archive -> prompt feed + receipt -> ledger ingest (--archive-feed)
              -> recurring-form index -> counts-only public receipt

Output is ten fixed-order lines (`check N <name>: ok|FAIL <reason>|skipped ...|not run`), then one last
line: `ALIVE <16 hex of the SHA-256 of the archive fingerprint>`, `NOT ALIVE: <check name>` or `UNUSABLE: <reason>`.
It carries no timestamps, titles, ids or conversation text, only counts and fixed phrases. The one path is
the engine that won check 1. A provider name appears where a check names the provider that failed.

The ten checks:

   1 tools            engine command found and its naming version meets the pinned minimum
   2 names            the engine accepts every name under the archive; each store directory starts with a kind
   3 registry         (live) check-corpora is green, every row key is a directory name, store is not the home
   4 archive          the engine verifies the archive and at least two providers are ok
   5 feed receipts    every feed has exactly one receipt bound to the manifest fingerprint and the feed bytes
   6 ledger binding   every feed row is an unknown-authority occurrence in the ledger; no operator authority
   7 recurring forms  the form builder verifies byte for byte and the form invariants hold
   8 privacy          roots are git-ignored or outside a work tree; no exact private value is public
   9 receipt          (live) the counts-only receipt for the current fingerprint exists
  10 determinism      the checks, run twice in-process, print identical bytes

Tool table (resolved in one place, `build_context`; each override is read from the environment):

  KNOWLEDGE_ALIVE_ENGINE          engine checkout directory (runs it as a module) or an executable file, used
                                  alone when set; unset means `cce` on PATH, then each checkout `corpus_resolve`
                                  knows. Every candidate is probed with `archive names --json` (exit 0, parses
                                  with kinds and naming_version) and the first that passes wins; none passing
                                  is `UNUSABLE: no working engine`. Check 1 reports the winner's path.
  KNOWLEDGE_ALIVE_LEDGER_SCRIPT   default scripts/prompt-atom-ledger.py
  KNOWLEDGE_ALIVE_FORMS_SCRIPT    default scripts/prompt-recurring-forms.py
  KNOWLEDGE_ALIVE_HOMING_SCRIPT   default scripts/check-atom-homing.py
  KNOWLEDGE_ALIVE_CORPORA_SCRIPT  default scripts/check-corpora.py

Engine commands used (the engine owns the naming contract; nothing here copies its kind table):

  archive names --json                     {"naming_version": N, "kinds": [...], "scopes": [...]}
  archive verify-names --root <archive>    exit 0 when every minted file and directory parses
  archive fixture --out <dir>              deterministic synthetic exports for two providers
  archive build|verify                     with --project-root --corpus-store-root --archive-root
  archive project feed --root <archive> --out <dir>
                                           feed-<provider>-prompts.jsonl plus
                                           receipt-<provider>-prompts-<16 hex>-<yyyymmdd>.json holding
                                           feed_sha256, rows, source_fingerprint, naming_version

Recurring-form builder contract (`prompt-recurring-forms.py`): `--root R --private-root P` with `--write`
or `--verify`; it writes `<P>/prompt-atoms/index-all-patterns.jsonl` (one row per member atom) and
`<P>/prompt-atoms/report-all-patterns.json` (counts: forms, members, atoms_considered, ungrouped_atoms,
forms_spanning_providers, forms_spanning_sources, trivial_forms).
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
for _path in (str(CLI_SRC), str(Path(__file__).resolve().parent)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from limen.prompt_corpus import (  # noqa: E402
    LedgerPaths,
    load_event_journal,
    load_json_strict,
    load_jsonl_strict,
    occurrence_from_event,
)

MINIMUM_NAMING_VERSION = 1
STORE_IDENTIFIER = "limen-private-archive"
ARCHIVE_DIRECTORY_NAME = "archive-all"
MANIFEST_FILE_NAME = "manifest-all.json"
FEED_DIRECTORY_NAME = "feed"
FORMS_INDEX_FILE_NAME = "index-all-patterns.jsonl"
FORMS_REPORT_FILE_NAME = "report-all-patterns.json"
RECEIPT_STEM = "receipt-knowledge-alive"
ARCHIVE_SOURCE_PREFIX = "archive-"
ARCHIVE_PROVENANCE = "unknown_user_input"
ELIGIBLE_CONVERSATION_KINDS = frozenset({"chat", "search", "activity"})
FINGERPRINT_PREFIX_LENGTH = 16
MINIMUM_SCANNED_VALUE_LENGTH = 12
MAXIMUM_INDEX_VALUE_LENGTH = 200
MAXIMUM_PUBLIC_FILE_BYTES = 20_000_000
MAXIMUM_NAME_LENGTH = 80
ENGINE_TIMEOUT_SECONDS = 900
TOOL_TIMEOUT_SECONDS = 300
FORM_NAME_PATTERN = re.compile(r"pattern-all-[0-9a-f]{16}")
NAME_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
FORBIDDEN_INDEX_KEYS = frozenset({"text", "raw_text", "intent", "title", "statement"})
REPORT_COUNT_KEYS = (
    "forms",
    "members",
    "atoms_considered",
    "ungrouped_atoms",
    "forms_spanning_providers",
    "forms_spanning_sources",
    "trivial_forms",
)
RECEIPT_REQUIRED_KEYS = ("day", "feed_sha256", "rows", "source_fingerprint", "naming_version")
PROVIDER_NAME = re.compile(r"[a-z0-9]+")
RECEIPT_NAME = re.compile(r"receipt-([a-z0-9]+)-prompts-([0-9a-f]{16})-([0-9]{8})\.json")

CHECK_NAMES = (
    "tools",
    "names",
    "registry",
    "archive",
    "feed receipts",
    "ledger binding",
    "recurring forms",
    "privacy",
    "receipt",
    "determinism",
)


class Unusable(Exception):
    """The environment cannot run the predicate at all (exit 2)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    stderr: str


def run_process(argv: list[str], *, env: dict[str, str], timeout: int) -> Completed:
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Completed(124, "", "timed out")
    return Completed(done.returncode, done.stdout, done.stderr)


def is_usage_error(done: Completed) -> bool:
    return done.returncode == 2 and "usage:" in done.stderr


class Engine:
    """Adapter that shells out to the engine command. Nothing else in this file knows how it is started."""

    def __init__(self, argv_prefix: list[str], extra_env: dict[str, str], origin: str = "") -> None:
        self.argv_prefix = argv_prefix
        self.extra_env = extra_env
        # Where this engine was found, as `<how> <path>`; check 1 reports it so a run names the winner.
        self.origin = origin

    def environment(self) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key != "CCE_CORPUS_STORE_ROOT"}
        for key, value in self.extra_env.items():
            existing = env.get(key)
            env[key] = f"{value}{os.pathsep}{existing}" if existing and key == "PYTHONPATH" else value
        return env

    def run(self, args: list[str], *, label: str | None = None, timeout: int = ENGINE_TIMEOUT_SECONDS) -> Completed:
        try:
            done = run_process([*self.argv_prefix, *args], env=self.environment(), timeout=timeout)
        except (FileNotFoundError, PermissionError):
            raise Unusable("engine command missing") from None
        if label is not None and is_usage_error(done):
            raise Unusable(f"engine command lacks {label}")
        return done


def parse_names(output: str) -> tuple[int, set[str]]:
    """Read `archive names --json`: the naming version and the set of kind words. Raises on anything else."""
    payload = json.loads(output)
    version = int(payload["naming_version"])
    kinds = payload["kinds"]
    # The engine lists each kind as a row carrying its rules; a bare word or a word-keyed map also reads.
    entries = kinds.keys() if isinstance(kinds, dict) else kinds
    return version, {str(entry["kind"] if isinstance(entry, dict) else entry) for entry in entries}


def engine_works(engine: Engine) -> bool:
    """A candidate engine is usable when `archive names --json` exits 0 and parses with its kinds and version."""
    try:
        done = engine.run(["archive", "names", "--json"], timeout=TOOL_TIMEOUT_SECONDS)
        if done.returncode != 0:
            return False
        parse_names(done.stdout)
    except (Unusable, ValueError, TypeError, KeyError, AttributeError):
        return False
    return True


def engine_candidates() -> Iterator[Engine]:
    """Candidates in order: the environment override, `cce` on PATH, then each known engine checkout.

    The override is exclusive. Someone who names an engine explicitly never gets a different one silently.
    """
    configured = os.environ.get("KNOWLEDGE_ALIVE_ENGINE")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            yield Engine([str(path)], {}, f"environment {path}")
        elif (path / "src" / "conversation_corpus_engine").is_dir():
            source = path / "src"
            yield Engine(
                [sys.executable, "-m", "conversation_corpus_engine.cli"],
                {"PYTHONPATH": str(source)},
                f"environment {source}",
            )
        return
    found = shutil.which("cce")
    if found:
        yield Engine([found], {}, f"PATH {found}")
    import corpus_resolve

    for source in corpus_resolve.cce_src_roots():
        if (source / "conversation_corpus_engine").is_dir():
            yield Engine(
                [sys.executable, "-m", "conversation_corpus_engine.cli"],
                {"PYTHONPATH": str(source)},
                f"checkout {source}",
            )


def locate_engine() -> Engine:
    """The first candidate engine that works. A crashing engine on PATH falls through to the next one."""
    for engine in engine_candidates():
        if engine_works(engine):
            return engine
    raise Unusable("no working engine")


def tool_script(variable: str, default: Path, reason: str) -> Path:
    path = Path(os.environ.get(variable) or default)
    if not path.is_file():
        raise Unusable(reason)
    return path


@dataclass
class Context:
    mode: str
    repo_root: Path
    engine: Engine
    ledger_script: Path
    forms_script: Path
    homing_script: Path
    corpora_script: Path
    store_root: Path
    archive_root: Path
    feed_dir: Path
    ledger_root: Path
    private_root: Path
    project_root: Path | None
    public_markdown: Path
    public_snapshot: Path
    public_seal: Path
    write_receipt: bool = False
    prepare_failure: tuple[str, str] | None = None
    # Where scratch directories go: the fixture's work directory, or None for the system temporary directory.
    work_dir: Path | None = None

    @property
    def private_dir(self) -> Path:
        return self.private_root / "prompt-atoms"

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    def custody_flags(self) -> list[str]:
        flags = ["--corpus-store-root", str(self.store_root), "--archive-root", str(self.archive_root)]
        if self.project_root is not None:
            flags += ["--project-root", str(self.project_root)]
        return flags

    def tool_environment(self) -> dict[str, str]:
        if self.is_live:
            return dict(os.environ)
        return {key: value for key, value in os.environ.items() if not key.startswith("LIMEN_")}

    def python_tool(self, script: Path, *args: str, timeout: int = TOOL_TIMEOUT_SECONDS) -> Completed:
        return run_process([sys.executable, str(script), *args], env=self.tool_environment(), timeout=timeout)

    def forms_arguments(self, mode_flag: str) -> list[str]:
        return ["--root", str(self.ledger_root), "--private-root", str(self.private_root), mode_flag]


@dataclass
class CheckResult:
    ok: bool
    detail: str = ""
    skipped: bool = False

    def render(self) -> str:
        if self.skipped:
            return f"skipped {self.detail}"
        return ("ok" if self.ok else "FAIL") + (f" {self.detail}" if self.detail else "")


State = dict[str, Any]


# --------------------------------------------------------------------------- readers


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


class MalformedRow(ValueError):
    """A line of a JSON-lines file is not a JSON object. It names the file and the line, never the content."""

    def __init__(self, name: str, line_number: int) -> None:
        super().__init__(f"line {line_number} of {name} is not a JSON object")


def read_rows(path: Path) -> Iterator[dict[str, Any]]:
    # Lines are decoded one at a time so a bad byte is reported at its own line, not at the start of a buffer.
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise MalformedRow(path.name, line_number) from None
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                raise MalformedRow(path.name, line_number) from None
            if not isinstance(row, dict):
                raise MalformedRow(path.name, line_number)
            yield row


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(ctx: Context) -> dict[str, Any] | None:
    return read_json(ctx.archive_root / MANIFEST_FILE_NAME)


def fingerprint_of(manifest: dict[str, Any] | None) -> str | None:
    value = (manifest or {}).get("source_fingerprint")
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d,}" % FINGERPRINT_PREFIX_LENGTH, value):
        return value
    return None


def providers_ok(manifest: dict[str, Any]) -> list[str]:
    providers = manifest.get("providers")
    if not isinstance(providers, dict):
        return []
    return sorted(name for name, info in providers.items() if isinstance(info, dict) and info.get("status") == "ok")


def conversations_file(ctx: Context, provider: str) -> Path:
    """The normalized conversations of one provider, named the way the engine's layout names them."""
    return ctx.archive_root / f"provider-{provider}" / f"collection-{provider}-conversations.jsonl"


def index_file(ctx: Context, provider: str) -> Path:
    return ctx.archive_root / f"provider-{provider}" / f"index-{provider}-conversations.jsonl"


def activity_day(value: Any) -> str | None:
    """The calendar day of a timestamp as yyyymmdd, or None when it holds no real day."""
    match = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", str(value or ""))
    if not match:
        return None
    try:
        dt.date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None
    return "".join(match.groups())


def latest_activity_day(ctx: Context, providers: list[str]) -> str | None:
    """Newest `last_activity` day over the normalized index, as yyyymmdd. Data, never the clock."""
    best: str | None = None
    for provider in providers:
        path = index_file(ctx, provider)
        if not path.is_file():
            continue
        for row in read_rows(path):
            day = activity_day(row.get("last_activity"))
            if day is not None and (best is None or day > best):
                best = day
    return best


def manifest_activity_day(manifest: dict[str, Any], providers: list[str]) -> str | None:
    """Newest `last_activity_max` day the manifest reports over the ok providers, as yyyymmdd.

    The manifest does carry a latest-activity stamp per provider, but the engine dates every feed receipt
    with the single newest day over all ok providers, so that global day is what each receipt must carry.
    """
    info = manifest.get("providers")
    info = info if isinstance(info, dict) else {}
    days: list[str] = []
    for name in providers:
        entry = info.get(name)
        day = activity_day(entry.get("last_activity_max")) if isinstance(entry, dict) else None
        if day is not None:
            days.append(day)
    return max(days) if days else None


def name_shape_problem(name: str, kinds: set[str]) -> str | None:
    if len(name) > MAXIMUM_NAME_LENGTH:
        return "longer than the name limit"
    if not NAME_PATTERN.fullmatch(name):
        return "not lowercase hyphenated words"
    if name.split("-", 1)[0] not in kinds:
        return "does not start with a listed kind"
    return None


def provider_of_feed(path: Path) -> str:
    return path.name.removeprefix("feed-").removesuffix("-prompts.jsonl")


def feed_files(ctx: Context) -> list[Path]:
    return sorted(ctx.feed_dir.glob("feed-*-prompts.jsonl")) if ctx.feed_dir.is_dir() else []


def feed_receipt_files(ctx: Context) -> list[Path]:
    return sorted(ctx.feed_dir.glob("receipt-*-prompts-*.json")) if ctx.feed_dir.is_dir() else []


def recount_eligible(ctx: Context, providers: list[str]) -> dict[str, int]:
    """Eligible asks counted straight from the normalized files, independent of the feed projector."""
    counts: dict[str, int] = {}
    for provider in providers:
        path = conversations_file(ctx, provider)
        total = 0
        if path.is_file():
            for conversation in read_rows(path):
                if conversation.get("kind") not in ELIGIBLE_CONVERSATION_KINDS:
                    continue
                messages = list(conversation.get("messages") or [])
                extra = conversation.get("extra") or {}
                messages += list(extra.get("alternate_messages") or []) if isinstance(extra, dict) else []
                total += sum(
                    1
                    for message in messages
                    if isinstance(message, dict) and message.get("role") == "user" and message.get("channel") == "typed"
                )
        counts[provider] = total
    return counts


# --------------------------------------------------------------------------- pure helpers


def registry_problems(registry: dict[str, Any], store_root: Path, home: Path) -> list[str]:
    """Registry versus disk for the private archive store. Pure so tests can feed it synthetic registries."""
    problems: list[str] = []
    stores = registry.get("stores") or {}
    if STORE_IDENTIFIER not in stores:
        problems.append("store is not declared")
    keys = sorted(
        key
        for key, row in (registry.get("corpora") or {}).items()
        if isinstance(row, dict) and row.get("store") == STORE_IDENTIFIER
    )
    if not keys:
        problems.append("store has no declared rows")
    names = sorted(child.name for child in store_root.iterdir() if child.is_dir()) if store_root.is_dir() else []
    for key in keys:
        if key not in names:
            problems.append("a row key is not a directory name")
            break
    for name in names:
        if name not in keys:
            problems.append("a directory has no row")
            break
    with contextlib.suppress(OSError):
        if home.resolve() == store_root.resolve():
            problems.append("store is the corpus home")
    return problems


def index_problems(rows: list[dict[str, Any]]) -> list[str]:
    """Invariants a recurring-form index must hold; count-level only, no values are reported."""
    problems: list[str] = []

    def too_long(value: Any) -> bool:
        if isinstance(value, str):
            return len(value) > MAXIMUM_INDEX_VALUE_LENGTH
        if isinstance(value, list):
            return any(too_long(item) for item in value)
        return False

    if any(FORBIDDEN_INDEX_KEYS & set(row) for row in rows):
        problems.append("index carries a text field")
    if any(too_long(value) for row in rows for value in row.values()):
        problems.append("index holds a value over the length limit")
    members = [str(row.get("atom_id") or "") for row in rows]
    if not all(members):
        problems.append("a member has no atom id")
    if len(set(members)) != len(members):
        problems.append("a member is in two forms")
    if not all(FORM_NAME_PATTERN.fullmatch(str(row.get("form") or "")) for row in rows):
        problems.append("a form name is malformed")
    return problems


def build_leak_index(values: set[str]) -> dict[str, list[tuple[str, int]]]:
    """Index exact values by their longest word run so one pass over a public text finds every hit."""
    index: dict[str, list[tuple[str, int]]] = {}
    for value in values:
        if len(value) < MINIMUM_SCANNED_VALUE_LENGTH:
            continue
        runs = re.findall(r"\w+", value)
        if not runs:
            continue
        key = max(runs, key=len)
        index.setdefault(key, []).append((value, value.find(key)))
    return index


def leaked_values(text: str, index: dict[str, list[tuple[str, int]]]) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(r"\w+", text):
        for value, offset in index.get(match.group(), ()):
            start = match.start() - offset
            if start >= 0 and text.startswith(value, start):
                found.add(value)
    return found


def root_is_private(path: Path) -> bool:
    """True when the path is outside every git work tree, or git-ignored inside one.

    Only git saying "not a git repository" (exit 128 with that phrase) means outside every work tree. A
    missing git binary, a permission error, a timeout or any other failure says nothing about the path, so
    it is an unusable environment rather than a quiet pass.
    """
    env = {**os.environ, "LC_ALL": "C"}

    def git(*arguments: str) -> Completed:
        try:
            return run_process(["git", *arguments], env=env, timeout=30)
        except OSError:
            raise Unusable("git is unavailable") from None

    inside = git("-C", str(path), "rev-parse", "--show-toplevel")
    if inside.returncode != 0:
        if inside.returncode == 128 and "not a git repository" in inside.stderr.lower():
            return True
        raise Unusable("git state cannot be read")
    top = Path(inside.stdout.strip())
    ignored = git("-C", str(top), "check-ignore", "-q", "--", str(path.resolve()))
    if ignored.returncode not in (0, 1):
        raise Unusable("git state cannot be read")
    return ignored.returncode == 0


# --------------------------------------------------------------------------- the ten checks


def check_tools(ctx: Context, state: State) -> CheckResult:
    done = ctx.engine.run(["archive", "names", "--json"], label="names")
    if done.returncode != 0:
        return CheckResult(False, "engine names command failed")
    try:
        version, kind_set = parse_names(done.stdout)
    except (ValueError, TypeError, KeyError, AttributeError):
        return CheckResult(False, "engine names output is unreadable")
    if version < MINIMUM_NAMING_VERSION:
        return CheckResult(False, f"naming version below {MINIMUM_NAMING_VERSION}")
    if not kind_set:
        return CheckResult(False, "engine lists no kinds")
    if not ctx.store_root.is_dir():
        return CheckResult(False, "store is missing")
    state["kinds"] = kind_set
    # The version the engine reported, not the pinned minimum: the receipt is written with and checked against it.
    state["naming_version"] = version
    return CheckResult(True, f"naming version {version}, {len(kind_set)} kinds, engine {ctx.engine.origin}")


def check_names(ctx: Context, state: State) -> CheckResult:
    done = ctx.engine.run(["archive", "verify-names", "--root", str(ctx.archive_root)], label="verify-names")
    if done.returncode != 0:
        return CheckResult(False, "the engine rejects a name under the archive")
    directories = sorted(child.name for child in ctx.store_root.iterdir() if child.is_dir())
    for name in directories:
        if name_shape_problem(name, state["kinds"]) is not None:
            return CheckResult(False, "a store directory name is not a listed kind")
    return CheckResult(True, f"{len(directories)} store directories")


def check_registry(ctx: Context, state: State) -> CheckResult:
    if not ctx.is_live:
        return CheckResult(True, "(live mode only)", skipped=True)
    import corpus_resolve

    corpora = ctx.python_tool(ctx.corpora_script)
    if corpora.returncode != 0:
        return CheckResult(False, "check-corpora is not green")
    problems = registry_problems(corpus_resolve.load_registry(), ctx.store_root, corpus_resolve.corpus_home())
    if problems:
        return CheckResult(False, problems[0])
    # The registry must name the very store under check, not another one that happens to look alike.
    if registered_store_root().resolve() != ctx.store_root.resolve():
        return CheckResult(False, "the registered store is not the store under check")
    registered_archive = corpus_resolve.corpus_root(ARCHIVE_DIRECTORY_NAME)
    if registered_archive is None or registered_archive.resolve() != ctx.archive_root.resolve():
        return CheckResult(False, "the registered archive is not the archive under check")
    return CheckResult(True, "registry matches the store")


def check_archive(ctx: Context, state: State) -> CheckResult:
    verify = ctx.engine.run(["archive", "verify", *ctx.custody_flags()])
    if verify.returncode != 0:
        return CheckResult(False, "the engine does not verify the archive")
    manifest = load_manifest(ctx)
    if manifest is None:
        return CheckResult(False, "manifest is missing")
    fingerprint = fingerprint_of(manifest)
    if fingerprint is None:
        return CheckResult(False, "manifest fingerprint is missing")
    providers = providers_ok(manifest)
    if len(providers) < 2:
        return CheckResult(False, "cross-provider unprovable")
    info = manifest["providers"]
    state.update(
        fingerprint=fingerprint,
        # The engine names a receipt by the first 16 hex of SHA-256 over the exact fingerprint string.
        prefix=hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:FINGERPRINT_PREFIX_LENGTH],
        providers=providers,
        # The day every receipt must carry: from the manifest, else from the normalized index. Never the clock.
        day=manifest_activity_day(manifest, providers) or latest_activity_day(ctx, providers),
        conversations=sum(int(info[name].get("conversations") or 0) for name in providers),
        messages=sum(int(info[name].get("messages") or 0) for name in providers),
    )
    return CheckResult(True, f"{len(providers)} providers, {state['conversations']} conversations")


def check_feed_receipts(ctx: Context, state: State) -> CheckResult:
    """Exactly one feed and one receipt for every ok provider in the manifest, and nothing else.

    A provider whose export holds no typed asks has an empty feed and a receipt that says `rows: 0` with the
    hash of the empty file; that is a legitimate pair and passes like any other.
    """
    providers: list[str] = state["providers"]
    feeds: dict[str, Path] = {}
    for feed in feed_files(ctx):
        provider = provider_of_feed(feed)
        if not PROVIDER_NAME.fullmatch(provider):
            return CheckResult(False, "a feed name is malformed")
        feeds[provider] = feed
    receipts: dict[str, list[Path]] = {}
    for path in feed_receipt_files(ctx):
        match = RECEIPT_NAME.fullmatch(path.name)
        if match is None:
            return CheckResult(False, "a receipt name is malformed")
        receipts.setdefault(match[1], []).append(path)
    for provider in sorted({*feeds, *receipts} - set(providers)):
        return CheckResult(False, f"{provider} has a feed or receipt but is not an ok provider")
    if state["day"] is None:
        return CheckResult(False, "the manifest holds no activity day")
    loaded: dict[str, dict[str, Any]] = {}
    for provider in providers:
        if provider not in feeds:
            return CheckResult(False, f"{provider} has no feed")
        found = receipts.get(provider, [])
        if not found:
            return CheckResult(False, f"{provider} has no receipt")
        if len(found) > 1:
            return CheckResult(False, f"{provider} has more than one receipt")
        feed, path = feeds[provider], found[0]
        name = RECEIPT_NAME.fullmatch(path.name)
        assert name is not None
        if name[2] != state["prefix"]:
            return CheckResult(False, f"{provider} receipt is for another fingerprint")
        if name_shape_problem(path.stem, state["kinds"]) or name_shape_problem(feed.stem, state["kinds"]):
            return CheckResult(False, f"{provider} feed or receipt name is malformed")
        receipt = read_json(path)
        if receipt is None or any(key not in receipt for key in RECEIPT_REQUIRED_KEYS):
            return CheckResult(False, f"{provider} receipt is unreadable or incomplete")
        if receipt["source_fingerprint"] != state["fingerprint"]:
            return CheckResult(False, f"{provider} receipt fingerprint differs from the manifest")
        if receipt["feed_sha256"] != file_sha256(feed):
            return CheckResult(False, f"{provider} feed differs from its receipt hash")
        if not isinstance(receipt["rows"], int) or isinstance(receipt["rows"], bool):
            return CheckResult(False, f"{provider} receipt row count is not a number")
        if activity_day(name[3]) != name[3] or receipt["day"] != name[3]:
            return CheckResult(False, f"{provider} receipt day differs from its name")
        if name[3] != state["day"]:
            return CheckResult(False, f"{provider} receipt day differs from the manifest's latest activity")
        try:
            rows = list(read_rows(feed))
        except OSError:
            return CheckResult(False, f"{provider} feed is unreadable")
        loaded[provider] = {"rows": rows, "receipt_rows": receipt["rows"], "feed_sha256": receipt["feed_sha256"]}
    state["feeds"] = loaded
    return CheckResult(True, f"{len(loaded)} feeds bound to the fingerprint")


@contextlib.contextmanager
def scratch_directory(ctx: Context) -> Iterator[Path]:
    """A private, empty directory for re-projected feeds, removed on the way out even after a failure.

    Fixture mode uses the work directory. Live mode uses <private root>/scratch/, created mode 0700, because
    the feeds hold private text and the system temporary directory is outside the private root.
    """
    if ctx.work_dir is not None:
        parent = ctx.work_dir
    else:
        parent = ctx.private_root / "scratch"
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=f"knowledge-alive-reproject-{os.getpid()}-", dir=parent))
    path.chmod(0o700)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def reprojection_problem(ctx: Context, state: State) -> str | None:
    """Re-project the feeds from the archive and compare bytes: the feed content is bound to the archive.

    Counts alone cannot tell a feed from the same number of different rows. The engine claims two runs write
    identical bytes, and this makes that claim a tested property of the live archive. The scratch directory
    sits under the work directory in fixture mode and under the private root in live mode, so private text
    never leaves the private root. It is always removed.
    """
    feeds: dict[str, dict[str, Any]] = state["feeds"]
    with scratch_directory(ctx) as out:
        arguments = ["archive", "project", "feed", "--root", str(ctx.archive_root), "--out", str(out)]
        if ctx.engine.run(arguments, label="project feed").returncode != 0:
            return "the engine cannot reproject the feeds"
        for provider in sorted(feeds):
            again = out / f"feed-{provider}-prompts.jsonl"
            if not again.is_file():
                return f"{provider} feed was not reprojected"
            reprojected = file_sha256(again)
            if reprojected != file_sha256(ctx.feed_dir / f"feed-{provider}-prompts.jsonl"):
                return f"{provider} feed differs from its reprojection"
            if reprojected != feeds[provider]["feed_sha256"]:
                return f"{provider} receipt hash differs from the reprojected feed"
    return None


def snapshot_problem(paths: LedgerPaths, occurrences: list[dict[str, Any]]) -> str | None:
    """Hold the private ledger snapshot to the journal: every archive occurrence in the journal is in it.

    The private snapshot is the ledger's checkpoint, written last. It records the occurrence count and the
    count per source family, so an archive occurrence that reached the journal but not the checkpoint shows
    up as a count that does not match. Counts only: no id or text is read or reported.
    """
    snapshot, errors = load_json_strict(paths.private_snapshot)
    if errors or not snapshot:
        return "the private ledger snapshot is missing or unreadable"
    counts = snapshot.get("counts")
    by_source = counts.get("sources") if isinstance(counts, dict) else None
    coverage = snapshot.get("coverage")
    if not isinstance(by_source, dict) or not isinstance(coverage, dict):
        return "the private ledger snapshot holds no occurrence counts"
    in_journal = Counter(
        str(row.get("source") or "")
        for row in occurrences
        if str(row.get("source") or "").startswith(ARCHIVE_SOURCE_PREFIX)
    )
    for source, count in in_journal.items():
        if by_source.get(source) != count:
            return "the private ledger snapshot lacks an archive occurrence that is in the journal"
    if coverage.get("occurrences") != len(occurrences):
        return "the private ledger snapshot count differs from the journal"
    return None


def check_ledger_binding(ctx: Context, state: State) -> CheckResult:
    feeds: dict[str, dict[str, Any]] = state["feeds"]
    recount = recount_eligible(ctx, list(feeds))
    wanted: set[str] = set()
    total = 0
    for provider, loaded in feeds.items():
        rows = loaded["rows"]
        if not (len(rows) == loaded["receipt_rows"] == recount[provider]):
            return CheckResult(False, "feed rows, receipt count and recount disagree")
        for row in rows:
            if not str(row.get("source", "")).startswith(ARCHIVE_SOURCE_PREFIX):
                return CheckResult(False, "a feed row is not from an archive source")
            if row.get("source") != f"archive-{provider}-messages":
                return CheckResult(False, "a feed row names the wrong provider")
            if row.get("provenance") != ARCHIVE_PROVENANCE:
                return CheckResult(False, "a feed row carries the wrong provenance")
            occurrence = occurrence_from_event(row)
            if occurrence["authority"] != "unknown":
                return CheckResult(False, "a feed row would carry operator authority")
            wanted.add(occurrence["occurrence_id"])
            total += 1
    if len(wanted) != total:
        return CheckResult(False, "occurrence ids are not unique")
    problem = reprojection_problem(ctx, state)
    if problem is not None:
        return CheckResult(False, problem)
    ledger_paths = LedgerPaths.for_root(ctx.ledger_root, private_root=ctx.private_root)
    journal = ledger_paths.event_journal
    if not journal.is_file():
        return CheckResult(False, "the ledger journal is missing")
    occurrences, atoms, errors = load_event_journal(journal)
    if errors:
        return CheckResult(False, "the ledger journal has errors")
    present = {row["occurrence_id"]: row for row in occurrences}
    for occurrence_id in wanted:
        row = present.get(occurrence_id)
        if row is None or not (row.get("atom_ids") or row.get("excluded_reason")):
            return CheckResult(False, "a feed occurrence is not in the ledger with atoms or a reason")
    raw_rows, raw_errors = load_jsonl_strict(journal)
    if raw_errors:
        return CheckResult(False, "the ledger journal has errors")
    for raw in raw_rows:
        entries = [raw.get("occurrence") or {}, *(raw.get("atoms") or [])]
        for entry in entries:
            if not isinstance(entry, dict) or not str(entry.get("source", "")).startswith(ARCHIVE_SOURCE_PREFIX):
                continue
            if entry.get("authority") == "operator" or entry.get("provenance") == "operator_typed":
                return CheckResult(False, "the journal holds operator authority for an archive source")
    problem = snapshot_problem(ledger_paths, list(present.values()))
    if problem is not None:
        return CheckResult(False, problem)
    state["occurrences_bound"] = len(wanted)
    state["feed_rows"] = total
    state["journal_atoms"] = {str(atom.get("atom_id")) for atom in atoms}
    state["journal_hashes"] = {str(row.get("prompt_hash")) for row in occurrences if row.get("prompt_hash")}
    return CheckResult(True, f"{total} feed rows bound as unknown authority")


def check_recurring_forms(ctx: Context, state: State) -> CheckResult:
    done = ctx.python_tool(ctx.forms_script, *ctx.forms_arguments("--verify"))
    if done.returncode != 0:
        return CheckResult(False, "the form builder does not verify")
    report = read_json(ctx.private_dir / FORMS_REPORT_FILE_NAME)
    if report is None or any(not isinstance(report.get(key), int) for key in REPORT_COUNT_KEYS):
        return CheckResult(False, "the form report is missing or incomplete")
    try:
        rows = list(read_rows(ctx.private_dir / FORMS_INDEX_FILE_NAME))
    except OSError:
        return CheckResult(False, "the form index is missing or unreadable")
    problems = index_problems(rows)
    if problems:
        return CheckResult(False, problems[0])
    if report["members"] != len(rows) or report["members"] + report["ungrouped_atoms"] != report["atoms_considered"]:
        return CheckResult(False, "members and ungrouped atoms do not add up to the atoms considered")
    forms: dict[str, set[str]] = {}
    for row in rows:
        forms.setdefault(str(row["form"]), set()).add(str(row.get("provider") or ""))
    spanning = sum(1 for providers in forms.values() if len(providers - {""}) >= 2)
    if report["forms"] != len(forms) or report["forms_spanning_providers"] != spanning:
        return CheckResult(False, "the form report disagrees with the index")
    if not {str(row["atom_id"]) for row in rows} <= state["journal_atoms"]:
        return CheckResult(False, "a form member is not an atom in the ledger")
    if not ctx.is_live and spanning < 1:
        return CheckResult(False, "no form spans two providers")
    state.update(forms=len(forms), forms_spanning=spanning)
    return CheckResult(True, f"{len(forms)} forms, {len(rows)} members, {spanning} spanning two or more providers")


def collect_private_values(ctx: Context, state: State) -> set[str]:
    values: set[str] = set(state["journal_hashes"])
    for loaded in state["feeds"].values():
        for row in loaded["rows"]:
            text = str(row.get("text") or "")
            values.add(hashlib.sha256(text.encode("utf-8")).hexdigest())
            # The typed text itself. Only an exact copy (after strip) is found, so a public file that rewraps or
            # edits an ask is a design limit of an exact-value scan; build_leak_index drops the short ones.
            values.add(text.strip())
    for provider in state["providers"]:
        index_path = index_file(ctx, provider)
        conversations_path = conversations_file(ctx, provider)
        if index_path.is_file():
            for row in read_rows(index_path):
                values.update(str(row.get(key) or "") for key in ("uid", "title"))
        if conversations_path.is_file():
            for conversation in read_rows(conversations_path):
                values.add(str(conversation.get("uid") or ""))
                messages = list(conversation.get("messages") or [])
                extra = conversation.get("extra") or {}
                messages += list(extra.get("alternate_messages") or []) if isinstance(extra, dict) else []
                values.update(str(m.get("id") or "") for m in messages if isinstance(m, dict))
    values.discard("")
    return values


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def public_files(ctx: Context) -> tuple[list[Path], str | None]:
    """The tracked public files to scan, or the name of a required one that is missing.

    Three are required: the ideal-forms ledger, the public ledger markdown and the authority seal. The public
    snapshot defaults to a file inside the private root, where it is not git-tracked and not public, so any
    candidate that resolves inside the private root is left out of the scan rather than counted as scanned.
    """
    docs = ctx.repo_root / "docs"
    required = [docs / "IDEAL-FORMS-LEDGER.md", ctx.public_markdown, ctx.public_seal]
    for path in required:
        if not path.is_file():
            return [], path.name
    candidates = [*required, ctx.public_snapshot]
    if (docs / "receipts").is_dir():
        candidates += sorted(path for path in (docs / "receipts").rglob("*") if path.is_file())
    seen: set[Path] = set()
    files = [
        path
        for path in candidates
        if path.is_file() and not is_inside(path, ctx.private_root) and not (path in seen or seen.add(path))
    ]
    return files, None


def check_privacy(ctx: Context, state: State) -> CheckResult:
    for root in (ctx.store_root, ctx.archive_root):
        if not root_is_private(root):
            return CheckResult(False, "a root is inside a work tree and not git-ignored")
    files, missing = public_files(ctx)
    if missing is not None:
        return CheckResult(False, f"required public file {missing} is missing")
    if not files:
        return CheckResult(False, "no public file was scanned")
    index = build_leak_index(collect_private_values(ctx, state))
    for path in files:
        if path.stat().st_size > MAXIMUM_PUBLIC_FILE_BYTES:
            return CheckResult(False, "a public file is too large to scan")
        if leaked_values(path.read_text(encoding="utf-8", errors="replace"), index):
            return CheckResult(False, "a public file holds an exact private value")
    homing = ctx.python_tool(ctx.homing_script)
    if homing.returncode != 0:
        return CheckResult(False, "check-atom-homing is not green")
    checked = sum(len(v) for v in index.values())
    return CheckResult(True, f"{len(files)} public files scanned, {checked} values checked, none found")


def receipt_name(state: State, day: str) -> str:
    return f"{RECEIPT_STEM}-{state['prefix']}-{day}"


def receipt_counts(state: State) -> dict[str, int]:
    return {
        "conversations": state["conversations"],
        "feed_rows": state["feed_rows"],
        "forms": state["forms"],
        "forms_spanning_providers": state["forms_spanning"],
        "messages": state["messages"],
        "occurrences_bound": state["occurrences_bound"],
        "providers": len(state["providers"]),
    }


def receipt_body(state: State, day: str) -> dict[str, Any]:
    return {
        "counts": receipt_counts(state),
        "date": day,
        "fingerprint": state["prefix"],
        "kind": "receipt",
        # The version the engine reported in check 1, not the pinned minimum.
        "naming_version": state["naming_version"],
    }


def receipt_mismatch(body: dict[str, Any], name: str, state: State) -> str | None:
    """The first field where a stored receipt disagrees with this run, as a fixed phrase, or None.

    The shape check alone passes a receipt copied from another run. This binds the body to the run:
    the fingerprint prefix, the day in the receipt's own name, the engine's naming version and the counts.
    """
    if body["fingerprint"] != state["prefix"]:
        return "fingerprint"
    if body["date"] != name.rsplit("-", 1)[-1]:
        return "date"
    if body["naming_version"] != state["naming_version"]:
        return "naming version"
    if body["counts"] != receipt_counts(state):
        return "counts"
    return None


def receipt_is_counts_only(body: dict[str, Any]) -> bool:
    counts = body.get("counts")
    if set(body) != {"counts", "date", "fingerprint", "kind", "naming_version"} or not isinstance(counts, dict):
        return False
    return all(isinstance(value, int) for value in counts.values()) and all(
        isinstance(body[key], str) and len(body[key]) <= 32 for key in ("date", "fingerprint", "kind")
    )


def check_receipt(ctx: Context, state: State) -> CheckResult:
    if not ctx.is_live:
        return CheckResult(True, "(live mode only)", skipped=True)
    day = state["day"]
    if day is None:
        return CheckResult(False, "no activity day in the manifest")
    name = receipt_name(state, day)
    if name_shape_problem(name, state["kinds"]) is not None:
        return CheckResult(False, "the receipt name is malformed")
    path = ctx.repo_root / "docs" / "receipts" / f"{name}.json"
    if not path.is_file():
        if not ctx.write_receipt:
            return CheckResult(False, "receipt missing, run with --write-receipt")
        # `evaluate` writes it between passes, so the privacy scan sees the same files in every pass.
        state["receipt_pending"] = (path, receipt_body(state, day))
        return CheckResult(False, "receipt missing, written after this pass")
    body = read_json(path)
    if body is None or not receipt_is_counts_only(body):
        return CheckResult(False, "the receipt is not counts only")
    mismatch = receipt_mismatch(body, name, state)
    if mismatch is not None:
        return CheckResult(False, f"the receipt differs from this run in its {mismatch}")
    return CheckResult(True, "receipt present for the current fingerprint")


CHECKS: tuple[tuple[str, Callable[[Context, State], CheckResult]], ...] = (
    ("tools", check_tools),
    ("names", check_names),
    ("registry", check_registry),
    ("archive", check_archive),
    ("feed receipts", check_feed_receipts),
    ("ledger binding", check_ledger_binding),
    ("recurring forms", check_recurring_forms),
    ("privacy", check_privacy),
    ("receipt", check_receipt),
)


def format_line(number: int, name: str, text: str) -> str:
    return f"check {number} {name}: {text}"


def run_pass(ctx: Context) -> tuple[list[str], str | None, State]:
    """One pass over checks 1 to 9. Stops at the first failure; later lines read `not run`."""
    state: State = {}
    lines: list[str] = []
    failed: str | None = None
    if ctx.prepare_failure is not None:
        owner, reason = ctx.prepare_failure
        for number, (name, _function) in enumerate(CHECKS, start=1):
            lines.append(format_line(number, name, f"FAIL {reason}" if name == owner else "not run"))
        return lines, owner, state
    for number, (name, function) in enumerate(CHECKS, start=1):
        if failed is not None:
            lines.append(format_line(number, name, "not run"))
            continue
        try:
            result = function(ctx, state)
        except Unusable:
            raise
        except MalformedRow as problem:
            result = CheckResult(False, str(problem))
        except Exception as problem:
            # Only the type is reported: an exception message can carry a path or a piece of row text.
            result = CheckResult(False, f"internal error in {name} ({type(problem).__name__})")
        lines.append(format_line(number, name, result.render()))
        if not result.ok:
            failed = name
    return lines, failed, state


def write_receipt_file(path: Path, body: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def evaluate(ctx: Context) -> tuple[list[str], int]:
    first_lines, failed, state = run_pass(ctx)
    pending = state.get("receipt_pending")
    if failed == "receipt" and pending is not None:
        try:
            write_receipt_file(*pending)
        except OSError:
            first_lines[-1] = format_line(len(CHECKS), "receipt", "FAIL the receipt cannot be written")
        else:
            first_lines, failed, state = run_pass(ctx)
    if failed is not None:
        return [*first_lines, format_line(10, "determinism", "not run"), f"NOT ALIVE: {failed}"], 1
    second_lines, _failed, _state = run_pass(ctx)
    if second_lines != first_lines:
        return [*first_lines, format_line(10, "determinism", "FAIL two passes differ"), "NOT ALIVE: determinism"], 1
    return [*first_lines, format_line(10, "determinism", "ok"), f"ALIVE {state['prefix']}"], 0


# --------------------------------------------------------------------------- fixture preparation


def prepare_fixture(ctx: Context, work: Path) -> None:
    """Side effects, done once: build the throwaway store, feed, ledger and form index.

    A step that fails stops the build and records which check owns the failure; `run_pass` then reports it.
    """
    exports = work / "exports"
    assert ctx.project_root is not None
    for directory in (ctx.store_root, exports, ctx.feed_dir, ctx.private_root, ctx.ledger_root, ctx.project_root):
        directory.mkdir(parents=True, exist_ok=True)

    def register_store() -> Completed:
        arguments = ["--root", str(ctx.store_root), "--project-root", str(ctx.project_root)]
        return ctx.engine.run(["corpus-store", "register", *arguments])

    def make_exports() -> Completed:
        return ctx.engine.run(["archive", "fixture", "--out", str(exports)], label="fixture")

    def build_archive() -> Completed:
        return ctx.engine.run(["archive", "build", "--export-root", str(exports), *ctx.custody_flags()])

    def project_feed() -> Completed:
        arguments = ["--root", str(ctx.archive_root), "--out", str(ctx.feed_dir)]
        return ctx.engine.run(["archive", "project", "feed", *arguments], label="project feed")

    def ingest_ledger() -> Completed:
        arguments = [
            *("--root", str(ctx.ledger_root)),
            *("--private-root", str(ctx.private_root)),
            *("--public-markdown", str(ctx.public_markdown)),
            *("--public-snapshot", str(ctx.public_snapshot)),
            *("--public-seal", str(ctx.public_seal)),
        ]
        for feed in feed_files(ctx):
            arguments += ["--archive-feed", str(feed)]
        done = ctx.python_tool(ctx.ledger_script, *arguments, "--write")
        if is_usage_error(done):
            raise Unusable("ledger lacks archive feed option")
        return done

    def write_forms() -> Completed:
        return ctx.python_tool(ctx.forms_script, *ctx.forms_arguments("--write"))

    steps: tuple[tuple[str, str, Callable[[], Completed]], ...] = (
        ("tools", "store registration failed", register_store),
        ("tools", "fixture command failed", make_exports),
        ("archive", "archive build failed", build_archive),
        ("feed receipts", "feed projection failed", project_feed),
        ("ledger binding", "ledger ingest failed", ingest_ledger),
        ("recurring forms", "form builder write failed", write_forms),
    )
    for check, reason, step in steps:
        if step().returncode != 0:
            ctx.prepare_failure = (check, reason)
            return


# --------------------------------------------------------------------------- context and entry point


def default_private_root() -> Path:
    configured = os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS")
    if configured:
        return Path(configured).expanduser()
    import corpus_resolve

    return corpus_resolve.live_root() / ".limen-private" / "session-corpus"


def registered_store_root() -> Path:
    import corpus_resolve

    row = ((corpus_resolve.load_registry().get("stores") or {}).get(STORE_IDENTIFIER)) or {}
    if not row.get("root"):
        raise Unusable("store not registered")
    return Path(str(row["root"])).expanduser()


def build_context(args: argparse.Namespace, work: Path | None) -> Context:
    repo_root = Path(args.repo_root).resolve() if args.repo_root else ROOT
    engine = locate_engine()
    ledger_script = tool_script(
        "KNOWLEDGE_ALIVE_LEDGER_SCRIPT", repo_root / "scripts" / "prompt-atom-ledger.py", "ledger script missing"
    )
    forms_script = tool_script(
        "KNOWLEDGE_ALIVE_FORMS_SCRIPT", repo_root / "scripts" / "prompt-recurring-forms.py", "forms script missing"
    )
    homing_script = tool_script(
        "KNOWLEDGE_ALIVE_HOMING_SCRIPT", repo_root / "scripts" / "check-atom-homing.py", "homing script missing"
    )
    corpora_script = Path(
        os.environ.get("KNOWLEDGE_ALIVE_CORPORA_SCRIPT") or repo_root / "scripts" / "check-corpora.py"
    )
    if args.fixture:
        assert work is not None
        store_root = work / "store"
        archive_root = store_root / ARCHIVE_DIRECTORY_NAME
        ledger_root = work / "ledger-root"
        return Context(
            mode="fixture",
            repo_root=repo_root,
            engine=engine,
            ledger_script=ledger_script,
            forms_script=forms_script,
            homing_script=homing_script,
            corpora_script=corpora_script,
            store_root=store_root,
            archive_root=archive_root,
            feed_dir=work / "feeds" / FEED_DIRECTORY_NAME,
            ledger_root=ledger_root,
            private_root=work / "ledger-private",
            project_root=work / "project",
            public_markdown=work / "public" / "prompt-atom-ledger.md",
            public_snapshot=work / "public" / "prompt-atom-ledger.json",
            public_seal=work / "public" / "prompt-authority-seal.json",
            work_dir=work,
        )
    store_root = Path(args.store_root).expanduser() if args.store_root else registered_store_root()
    if not store_root.is_dir():
        raise Unusable("store missing")
    archive_root = store_root / ARCHIVE_DIRECTORY_NAME
    if not archive_root.is_dir():
        raise Unusable("archive missing")
    private_root = Path(args.private_root).expanduser() if args.private_root else default_private_root()
    paths = LedgerPaths.for_root(repo_root, private_root=private_root)
    return Context(
        mode="live",
        repo_root=repo_root,
        engine=engine,
        ledger_script=ledger_script,
        forms_script=forms_script,
        homing_script=homing_script,
        corpora_script=corpora_script,
        store_root=store_root,
        archive_root=archive_root,
        feed_dir=Path(args.feed_dir).expanduser() if args.feed_dir else archive_root / FEED_DIRECTORY_NAME,
        ledger_root=repo_root,
        private_root=private_root,
        project_root=Path(args.project_root).expanduser() if args.project_root else None,
        public_markdown=paths.public_markdown,
        public_snapshot=paths.public_snapshot,
        public_seal=paths.public_seal,
        write_receipt=args.write_receipt,
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Is the private knowledge archive loop alive, end to end?")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true", help="hermetic run over synthetic exports")
    mode.add_argument("--live", action="store_true", help="read-only run over the registered store and ledger")
    parser.add_argument("--store-root", help="live: the store root (default: the registered store)")
    parser.add_argument("--feed-dir", help="live: where the prompt feeds and receipts live")
    parser.add_argument("--private-root", help="live: the private ledger root")
    parser.add_argument("--project-root", help="live: the engine project root")
    parser.add_argument("--repo-root", help="the repository whose docs are scanned (default: this checkout)")
    parser.add_argument("--write-receipt", action="store_true", help="live: write the counts-only receipt when absent")
    args = parser.parse_args(argv)
    if args.write_receipt and not args.live:
        parser.error("--write-receipt needs --live")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.fixture:
            with tempfile.TemporaryDirectory(prefix="knowledge-alive-") as directory:
                work = Path(directory).resolve()
                ctx = build_context(args, work)
                prepare_fixture(ctx, work)
                lines, code = evaluate(ctx)
        else:
            ctx = build_context(args, None)
            lines, code = evaluate(ctx)
    except Unusable as problem:
        print(f"UNUSABLE: {problem.reason}")
        return 2
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
