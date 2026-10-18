"""Tests for scripts/check-knowledge-alive.py, the whole-loop predicate for the private knowledge archive.

Every conversation string here is synthetic. The engine, the ledger, the form builder and the atom-homing
check are stubs the tests write to a temporary directory, because those tools land in other increments.
The stub engine speaks the documented command surface and can be told to break one thing at a time through
the STUB_FAULT environment variable; each break must flip the predicate to NOT ALIVE at exactly one named
check. A real-engine run is available behind KNOWLEDGE_ALIVE_ENGINE.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-knowledge-alive.py"
CLI_SRC = ROOT / "cli" / "src"
SCRIPTS = ROOT / "scripts"
for _path in (str(CLI_SRC), str(SCRIPTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

SHARED_ASK = "Draft the quarterly synthetic summary for the shared fixture now."

STUB_ENGINE = r"""
import hashlib, json, os, sys
from pathlib import Path

FAULTS = {item for item in os.environ.get("STUB_FAULT", "").split(",") if item}
KINDS = ["archive", "conversation", "message", "thread", "family", "pair", "action", "question", "feed",
         "receipt", "corpus", "index", "pattern", "manifest", "report", "vault", "site", "graph", "database",
         "check", "fixture", "provider", "month", "topic", "collection", "home", "coverage", "guide"]
PROVIDERS = ("chatgpt", "claude") + (("notebooklm",) if "zero-row-provider" in FAULTS else ())
SHARED_ASK = "Draft the quarterly synthetic summary for the shared fixture now."
ELIGIBLE = {"chat", "search", "activity"}


def option(name):
    return sys.argv[sys.argv.index(name) + 1]


def source_conversations(provider):
    def message(number, role, channel, text):
        return {"id": f"msg-{provider}-{number:04d}", "role": role, "channel": channel,
                "ts": f"2026-03-01T10:00:{number:02d}Z", "text": text}
    notebook = {"source_id": "notebook-two", "title": f"Synthetic notebook for {provider}", "kind": "notebook",
                "messages": [message(6, "user", "typed", "Notebook note that stays out of every feed.")], "extra": {}}
    if provider == "notebooklm":
        return [notebook]
    return [
        {"source_id": "conv-one", "title": f"Synthetic planning thread for {provider}", "kind": "chat",
         "messages": [
             message(1, "user", "typed", SHARED_ASK),
             message(2, "assistant", "reply", "Synthetic reply text one."),
             message(3, "assistant", "thinking", "Synthetic thinking text."),
             message(4, "user", "typed", f"Outline the synthetic {provider} migration plan with exact steps."),
         ],
         "extra": {"alternate_messages": [
             message(5, "user", "typed", f"Reword the synthetic {provider} outline in plain steps.")]}},
        notebook,
    ]


def lines(rows):
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)


def main():
    args = sys.argv[1:]
    if args[:2] == ["archive", "names"]:
        kinds = list(KINDS)
        if "names-old" in FAULTS:
            version = 0
        else:
            version = 1
        if "names-flaky" in FAULTS:
            counter = Path(os.environ["STUB_COUNTER"])
            calls = int(counter.read_text()) if counter.is_file() else 0
            counter.write_text(str(calls + 1))
            # Call 0 is the engine probe and call 1 is the first pass, so only the second pass differs.
            if calls >= 2:
                kinds.remove("guide")
        print(json.dumps({"naming_version": version, "kinds": kinds, "scopes": [*PROVIDERS, "all"]}))
        return 0
    if args[:2] == ["corpus-store", "register"]:
        project = Path(option("--project-root"))
        project.mkdir(parents=True, exist_ok=True)
        (project / "registered.json").write_text(json.dumps({"root": option("--root")}))
        return 0
    if args[:2] == ["archive", "verify-names"]:
        return 1 if "bad-names" in FAULTS else 0
    if args[:2] == ["archive", "fixture"] and "no-fixture" not in FAULTS:
        out = Path(option("--out"))
        out.mkdir(parents=True, exist_ok=True)
        for provider in PROVIDERS:
            (out / f"{provider}.json").write_text(json.dumps(
                {"provider": provider, "conversations": source_conversations(provider)}))
        print(json.dumps({"providers": list(PROVIDERS)}))
        return 0
    if args[:2] == ["archive", "build"]:
        if "build-fails" in FAULTS:
            return 1
        project = Path(option("--project-root"))
        if not (project / "registered.json").is_file():
            print("archive custody refused", file=sys.stderr)
            return 2
        archive = Path(option("--archive-root"))
        providers, parts = {}, []
        for provider in PROVIDERS:
            if "one-provider" in FAULTS and provider == "claude":
                providers[provider] = {"status": "absent", "conversations": 0, "messages": 0}
                continue
            rows, index = [], []
            for source in source_conversations(provider):
                stamps = [m["ts"] for m in source["messages"]]
                row = {"uid": f"{provider}-{source['source_id']}", "provider": provider,
                       "source_id": source["source_id"], "title": source["title"], "kind": source["kind"],
                       "created": min(stamps), "updated": max(stamps), "messages": source["messages"],
                       "extra": source["extra"]}
                rows.append(row)
                index.append({k: row[k] for k in ("uid", "provider", "title", "kind", "created", "updated")}
                             | {"last_activity": max(stamps)})
            folder = archive / f"provider-{provider}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"collection-{provider}-conversations.jsonl").write_text(lines(rows))
            (folder / f"index-{provider}-conversations.jsonl").write_text(lines(index))
            parts.append(lines(rows))
            providers[provider] = {"status": "ok", "conversations": len(rows),
                                   "messages": sum(len(r["messages"]) for r in rows),
                                   "last_activity_max": max(row["updated"] for row in rows)}
        manifest = {"naming_version": 1, "providers": providers,
                    "source_fingerprint": hashlib.sha256("".join(parts).encode()).hexdigest()}
        (archive / "manifest-all.json").write_text(json.dumps(manifest, sort_keys=True))
        return 0
    if args[:2] == ["archive", "verify"]:
        return 1 if "verify-fails" in FAULTS else 0
    if args[:3] == ["archive", "project", "feed"]:
        archive, out = Path(option("--root")), Path(option("--out"))
        out.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((archive / "manifest-all.json").read_text())
        fingerprint = manifest["source_fingerprint"]
        day = max(info["last_activity_max"] for info in manifest["providers"].values()
                  if info["status"] == "ok")[:10].replace("-", "")
        for provider, info in manifest["providers"].items():
            if info["status"] != "ok" or ("missing-feed" in FAULTS and provider == "claude"):
                continue
            rows = []
            path = archive / f"provider-{provider}" / f"collection-{provider}-conversations.jsonl"
            for line in path.read_text().splitlines():
                conversation = json.loads(line)
                if conversation["kind"] not in ELIGIBLE:
                    continue
                items = [(m, False) for m in conversation["messages"]]
                items += [(m, True) for m in conversation["extra"].get("alternate_messages", [])]
                for message, alternate in items:
                    if message["role"] != "user" or message["channel"] != "typed":
                        continue
                    row = {"source": f"archive-{provider}-messages", "session_ref": conversation["uid"],
                           "event_ref": message["id"], "event_index": len(rows), "text_index": 0,
                           "text": message["text"], "timestamp": message["ts"],
                           "source_locator": f"{conversation['uid']}#{message['id']}",
                           "body_kind": "direct", "provenance": "unknown_user_input"}
                    if alternate:
                        row["branch"] = "alternate"
                    rows.append(row)
            if rows and "provenance" in FAULTS:
                rows[0]["provenance"] = "operator_typed"
            if rows and "source-name" in FAULTS:
                rows[0]["source"] = "claude-code-sessions"
            if rows and "reproject-differs" in FAULTS and "reproject" in out.name:
                rows[0]["text"] += " changed"
            text = lines(rows)
            (out / f"feed-{provider}-prompts.jsonl").write_text(text)
            prefix = "0" * 16 if "stale-receipt" in FAULTS else hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
            named_day = "20250101" if "receipt-day-name" in FAULTS else day
            receipt = {"feed_sha256": hashlib.sha256(text.encode()).hexdigest(),
                       "rows": len(rows) + (1 if "row-count" in FAULTS else 0),
                       "excluded_counts": {"notebook": 1}, "alternate_branch_count": 1,
                       "source_fingerprint": "f" * 64 if "receipt-fingerprint" in FAULTS else fingerprint,
                       "day": "20250102" if "receipt-day-body" in FAULTS else named_day,
                       "naming_version": 1, "reader_versions": {provider: "2"}}
            if not ("missing-receipt" in FAULTS and provider == "claude"):
                (out / f"receipt-{provider}-prompts-{prefix}-{named_day}.json").write_text(json.dumps(receipt))
            if "extra-receipt" in FAULTS and provider == "claude":
                (out / f"receipt-{provider}-prompts-{prefix}-20250103.json").write_text(json.dumps(receipt))
            if "receipt-hash" in FAULTS:
                with (out / f"feed-{provider}-prompts.jsonl").open("a") as handle:
                    handle.write("\n")
                    handle.write(json.dumps({"changed": True}) + "\n")
        if "extra-feed" in FAULTS:
            (out / "feed-ghost-prompts.jsonl").write_text("")
        return 0
    print("usage: stub-engine", file=sys.stderr)
    return 2


sys.exit(main())
"""

STUB_LEDGER = r"""
import json, os, sys
from pathlib import Path

sys.path.insert(0, "__CLI_SRC__")
from limen.prompt_corpus import atoms_from_event, load_policy, occurrence_from_event

FAULTS = {item for item in os.environ.get("STUB_FAULT", "").split(",") if item}
argv = sys.argv[1:]
if "ledger-no-option" in FAULTS and "--archive-feed" in argv:
    print("usage: prompt-atom-ledger.py [options]", file=sys.stderr)
    sys.exit(2)


def option(name):
    return argv[argv.index(name) + 1]


feeds = [argv[i + 1] for i, item in enumerate(argv) if item == "--archive-feed"]
policy = load_policy(Path(option("--root")) / "docs" / "prompt-corpus-policy.json")
rows = []
for feed in feeds:
    for line in Path(feed).read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        occurrence = occurrence_from_event(event)
        atoms = atoms_from_event(occurrence, event, policy)
        occurrence.pop("raw_text", None)
        rows.append({"occurrence": occurrence, "atoms": atoms})
if rows and "ledger-drop" in FAULTS:
    rows.pop()
if rows and "ledger-operator" in FAULTS:
    rows[0]["occurrence"]["authority"] = "operator"
journal = Path(option("--private-root")) / "prompt-atoms" / "prompt-events.jsonl"
journal.parent.mkdir(parents=True, exist_ok=True)
journal.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
markdown = Path(option("--public-markdown"))
markdown.parent.mkdir(parents=True, exist_ok=True)
leaked = rows[0]["occurrence"]["source_locator"].split("#")[0] if rows and "leak" in FAULTS else ""
markdown.write_text(f"# Ledger\n\nCounts only: {len(rows)} occurrences. {leaked}\n")
Path(option("--public-snapshot")).write_text(json.dumps({"occurrences": len(rows)}))
Path(option("--public-seal")).write_text(json.dumps({"ok": True}))
"""

STUB_FORMS = r"""
import hashlib, json, os, sys
from pathlib import Path

FAULTS = {item for item in os.environ.get("STUB_FAULT", "").split(",") if item}
argv = sys.argv[1:]
private = Path(argv[argv.index("--private-root") + 1]) / "prompt-atoms"
occurrences, atoms = {}, []
for line in (private / "prompt-events.jsonl").read_text().splitlines():
    if line.strip():
        row = json.loads(line)
        occurrences[row["occurrence"]["occurrence_id"]] = row["occurrence"]
        atoms += row["atoms"]
groups = {}
for atom in sorted(atoms, key=lambda a: a["atom_id"]):
    key = atom["lineage_id"] + (atom["source"] if "forms-none" in FAULTS else "")
    groups.setdefault(key, []).append(atom)
rows = []
for key, members in groups.items():
    if len(members) < 2:
        continue
    form = "pattern-all-" + hashlib.sha256(key.encode()).hexdigest()[:16]
    for atom in members:
        occurrence = occurrences[atom["occurrence_id"]]
        row = {"form": form, "atom_id": atom["atom_id"], "occurrence_id": atom["occurrence_id"],
               "source": occurrence["source"], "provider": occurrence["source"].split("-")[1],
               "conversation_uid": occurrence["source_locator"].split("#")[0], "authority": atom["authority"]}
        if "forms-text" in FAULTS:
            row["text"] = atom["intent"]
        rows.append(row)
rows.sort(key=lambda r: (r["form"], r["atom_id"]))
forms = {}
for row in rows:
    forms.setdefault(row["form"], []).append(row)
report = {"forms": len(forms), "members": len(rows), "atoms_considered": len(atoms),
          "ungrouped_atoms": len(atoms) - len(rows),
          "forms_spanning_providers": sum(1 for m in forms.values() if len({r["provider"] for r in m}) >= 2),
          "forms_spanning_sources": sum(1 for m in forms.values() if len({r["source"] for r in m}) >= 2),
          "trivial_forms": 0}
index_text = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
report_text = json.dumps(report, sort_keys=True, indent=2) + "\n"
if "--write" in argv:
    (private / "index-all-patterns.jsonl").write_text(index_text)
    (private / "report-all-patterns.json").write_text(report_text)
    sys.exit(0)
same = (private / "index-all-patterns.jsonl").read_text() == index_text
same = same and (private / "report-all-patterns.json").read_text() == report_text
sys.exit(0 if same and "forms-verify-fails" not in FAULTS else 1)
"""

STUB_HOMING = r"""
import os, sys
sys.exit(1 if "homing-fails" in os.environ.get("STUB_FAULT", "").split(",") else 0)
"""

STUB_CORPORA = "import sys\nsys.exit(0)\n"


def _write_tool(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(f"#!{sys.executable}\n" + body.replace("__CLI_SRC__", str(CLI_SRC)), encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.fixture
def stubs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("knowledge-alive-stubs")
    return SimpleNamespace(
        engine=_write_tool(directory, "stub-engine", STUB_ENGINE),
        ledger=_write_tool(directory, "stub-ledger", STUB_LEDGER),
        forms=_write_tool(directory, "stub-forms", STUB_FORMS),
        homing=_write_tool(directory, "stub-homing", STUB_HOMING),
        corpora=_write_tool(directory, "stub-corpora", STUB_CORPORA),
        counter=directory / "counter",
    )


def _environment(stubs, **overrides) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        KNOWLEDGE_ALIVE_ENGINE=str(stubs.engine),
        KNOWLEDGE_ALIVE_LEDGER_SCRIPT=str(stubs.ledger),
        KNOWLEDGE_ALIVE_FORMS_SCRIPT=str(stubs.forms),
        KNOWLEDGE_ALIVE_HOMING_SCRIPT=str(stubs.homing),
        KNOWLEDGE_ALIVE_CORPORA_SCRIPT=str(stubs.corpora),
        STUB_COUNTER=str(stubs.counter),
        STUB_FAULT="",
    )
    env.update(overrides)
    return env


def _run(stubs, *args, **overrides) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=_environment(stubs, **overrides),
        timeout=300,
        check=False,
    )


@pytest.fixture(scope="module")
def module():
    name = "check_knowledge_alive_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


# --------------------------------------------------------------------------- fixture mode, whole loop


def test_fixture_mode_is_alive_end_to_end_with_the_real_homing_check(stubs):
    env = {k: v for k, v in _environment(stubs).items() if k != "KNOWLEDGE_ALIVE_HOMING_SCRIPT"}
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture"], capture_output=True, text=True, env=env, timeout=300, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert len(lines) == 11
    assert re.fullmatch(r"ALIVE [0-9a-f]{16}", lines[-1])
    for number, line in enumerate(lines[:10], start=1):
        assert line.startswith(f"check {number} "), line
    assert lines[2] == "check 3 registry: skipped (live mode only)"
    assert lines[8] == "check 9 receipt: skipped (live mode only)"
    assert lines[9] == "check 10 determinism: ok"
    assert re.fullmatch(
        r"check 7 recurring forms: ok \d+ forms, \d+ members, [1-9]\d* spanning two or more providers", lines[6]
    )


def test_fixture_mode_is_alive_with_the_real_recurring_form_builder(stubs):
    env = {k: v for k, v in _environment(stubs).items() if k != "KNOWLEDGE_ALIVE_FORMS_SCRIPT"}
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture"], capture_output=True, text=True, env=env, timeout=300, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert re.fullmatch(
        r"check 7 recurring forms: ok [1-9]\d* forms, \d+ members, [1-9]\d* spanning two or more providers", lines[6]
    )
    assert lines[9] == "check 10 determinism: ok"
    assert re.fullmatch(r"ALIVE [0-9a-f]{16}", lines[-1])


def test_output_is_deterministic_and_carries_no_text_ids_titles_or_paths(stubs):
    first = _run(stubs, "--fixture")
    second = _run(stubs, "--fixture")
    assert first.returncode == 0 and second.returncode == 0, first.stdout + first.stderr
    assert first.stdout == second.stdout
    # The only path in the output is the engine that won check 1; the work directory never appears.
    first_line, *rest = first.stdout.splitlines()
    assert first_line.endswith(f"engine environment {stubs.engine}")
    for fragment in (SHARED_ASK, "Synthetic", "conv-one", "msg-", "chatgpt-conv", "knowledge-alive-", "/tmp", "/var"):
        assert fragment not in "\n".join(rest)
    assert first.stderr == ""


FAULT_CASES = [
    ("names-old", "tools"),
    ("bad-names", "names"),
    ("one-provider", "archive"),
    ("verify-fails", "archive"),
    ("build-fails", "archive"),
    ("stale-receipt", "feed receipts"),
    ("receipt-fingerprint", "feed receipts"),
    ("receipt-hash", "feed receipts"),
    ("missing-feed", "feed receipts"),
    ("missing-receipt", "feed receipts"),
    ("extra-receipt", "feed receipts"),
    ("extra-feed", "feed receipts"),
    ("receipt-day-body", "feed receipts"),
    ("receipt-day-name", "feed receipts"),
    ("reproject-differs", "ledger binding"),
    ("row-count", "ledger binding"),
    ("provenance", "ledger binding"),
    ("source-name", "ledger binding"),
    ("ledger-drop", "ledger binding"),
    ("ledger-operator", "ledger binding"),
    ("forms-text", "recurring forms"),
    ("forms-none", "recurring forms"),
    ("forms-verify-fails", "recurring forms"),
    ("leak", "privacy"),
    ("homing-fails", "privacy"),
    ("names-flaky", "determinism"),
]


@pytest.mark.parametrize(("fault", "check"), FAULT_CASES)
def test_each_break_names_exactly_one_failing_check(stubs, fault, check):
    done = _run(stubs, "--fixture", STUB_FAULT=fault)
    assert done.returncode == 1, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert lines[-1] == f"NOT ALIVE: {check}"
    failing = [line for line in lines if ": FAIL" in line]
    assert len(failing) == 1 and f" {check}: FAIL" in failing[0]
    assert SHARED_ASK not in done.stdout and "msg-" not in done.stdout and "conv-one" not in done.stdout


@pytest.mark.parametrize(
    ("fault", "check", "reason"),
    [
        ("missing-feed", 5, "claude has no feed"),
        ("missing-receipt", 5, "claude has no receipt"),
        ("extra-receipt", 5, "claude has more than one receipt"),
        ("extra-feed", 5, "ghost has a feed or receipt but is not an ok provider"),
        ("stale-receipt", 5, "chatgpt receipt is for another fingerprint"),
        ("receipt-day-body", 5, "chatgpt receipt day differs from its name"),
        ("receipt-day-name", 5, "chatgpt receipt day differs from the manifest's latest activity"),
        ("reproject-differs", 6, "chatgpt feed differs from its reprojection"),
    ],
)
def test_feed_failures_name_the_provider(stubs, fault, check, reason):
    done = _run(stubs, "--fixture", STUB_FAULT=fault)
    failing = [line for line in done.stdout.splitlines() if ": FAIL" in line]
    assert len(failing) == 1 and f"check {check} " in failing[0] and failing[0].endswith(f"FAIL {reason}"), failing


def test_a_provider_with_an_empty_feed_and_a_zero_row_receipt_is_alive(stubs):
    done = _run(stubs, "--fixture", STUB_FAULT="zero-row-provider")
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert lines[3].startswith("check 4 archive: ok 3 providers")
    assert lines[4] == "check 5 feed receipts: ok 3 feeds bound to the fingerprint"
    assert re.fullmatch(r"ALIVE [0-9a-f]{16}", lines[-1])


def test_cross_provider_unprovable_is_named(stubs):
    done = _run(stubs, "--fixture", STUB_FAULT="one-provider")
    assert "check 4 archive: FAIL cross-provider unprovable" in done.stdout


def test_checks_after_a_failure_are_not_run(stubs):
    done = _run(stubs, "--fixture", STUB_FAULT="bad-names")
    lines = done.stdout.splitlines()
    assert lines[0].startswith("check 1 tools: ok")
    assert lines[1].startswith("check 2 names: FAIL")
    assert all(line.endswith(": not run") for line in lines[2:10])


# --------------------------------------------------------------------------- unusable environment


def test_missing_engine_command_is_exit_two_never_a_skip(stubs, tmp_path):
    done = _run(stubs, "--fixture", KNOWLEDGE_ALIVE_ENGINE=str(tmp_path / "absent"))
    assert done.returncode == 2
    assert done.stdout.splitlines() == ["UNUSABLE: no working engine"]


NAMES_ONLY_MODULE = (
    "import json, sys\n"
    "if sys.argv[1:3] == ['archive', 'names']:\n"
    "    print(json.dumps({'naming_version': 1, 'kinds': ['archive'], 'scopes': []}))\n"
    "    sys.exit(0)\n"
    "sys.exit(2)\n"
)


def _fake_checkout(source: Path) -> Path:
    package = source / "conversation_corpus_engine"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(NAMES_ONLY_MODULE, encoding="utf-8")
    return source


def _fake_cce(directory: Path, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return _write_tool(directory, "cce", body)


def _isolate_engine_search(monkeypatch, *, path: Path, checkouts: list[Path]) -> None:
    import corpus_resolve

    monkeypatch.delenv("KNOWLEDGE_ALIVE_ENGINE", raising=False)
    monkeypatch.setenv("PATH", str(path))
    monkeypatch.setattr(corpus_resolve, "cce_src_roots", lambda: checkouts)


def test_a_crashing_engine_on_path_falls_through_to_the_next_candidate(module, tmp_path, monkeypatch):
    _fake_cce(tmp_path / "bin", "import sys\nsys.exit(3)\n")
    checkout = _fake_checkout(tmp_path / "checkout" / "src")
    _isolate_engine_search(monkeypatch, path=tmp_path / "bin", checkouts=[checkout])
    engine = module.locate_engine()
    assert engine.origin == f"checkout {checkout}"
    assert module.engine_works(engine)


def test_a_working_engine_on_path_wins_over_a_checkout(module, tmp_path, monkeypatch):
    names = "import json\nprint(json.dumps({'naming_version': 2, 'kinds': [{'kind': 'archive'}], 'scopes': []}))\n"
    cce = _fake_cce(tmp_path / "bin", names)
    checkout = _fake_checkout(tmp_path / "checkout" / "src")
    _isolate_engine_search(monkeypatch, path=tmp_path / "bin", checkouts=[checkout])
    assert module.locate_engine().origin == f"PATH {cce}"


@pytest.mark.parametrize(
    "body",
    [
        "print('not json')\n",
        "import json\nprint(json.dumps({'naming_version': 1}))\n",
        "import json\nprint(json.dumps({'kinds': ['archive']}))\n",
        "import json\nprint(json.dumps(['archive']))\n",
    ],
)
def test_an_engine_whose_names_output_does_not_parse_is_not_a_candidate(module, tmp_path, monkeypatch, body):
    _fake_cce(tmp_path / "bin", body)
    _isolate_engine_search(monkeypatch, path=tmp_path / "bin", checkouts=[])
    with pytest.raises(module.Unusable) as raised:
        module.locate_engine()
    assert raised.value.reason == "no working engine"


def test_the_environment_override_is_exclusive(module, tmp_path, monkeypatch):
    checkout = _fake_checkout(tmp_path / "checkout" / "src")
    _isolate_engine_search(monkeypatch, path=tmp_path / "bin", checkouts=[checkout])
    monkeypatch.setenv("KNOWLEDGE_ALIVE_ENGINE", str(tmp_path / "absent"))
    with pytest.raises(module.Unusable) as raised:
        module.locate_engine()
    assert raised.value.reason == "no working engine"


def test_the_environment_override_may_name_an_engine_checkout(module, tmp_path, monkeypatch):
    checkout = _fake_checkout(tmp_path / "checkout" / "src")
    _isolate_engine_search(monkeypatch, path=tmp_path / "bin", checkouts=[])
    monkeypatch.setenv("KNOWLEDGE_ALIVE_ENGINE", str(checkout.parent))
    assert module.locate_engine().origin == f"environment {checkout}"


def test_no_working_engine_anywhere_is_exit_two(module, tmp_path, monkeypatch, capsys):
    _fake_cce(tmp_path / "bin", "import sys\nsys.exit(3)\n")
    _isolate_engine_search(monkeypatch, path=tmp_path / "bin", checkouts=[])
    assert module.main(["--fixture"]) == 2
    assert capsys.readouterr().out.splitlines() == ["UNUSABLE: no working engine"]


def test_an_engine_without_the_fixture_command_is_exit_two(stubs):
    done = _run(stubs, "--fixture", STUB_FAULT="no-fixture")
    assert done.returncode == 2
    assert done.stdout.splitlines() == ["UNUSABLE: engine command lacks fixture"]


def test_a_ledger_without_the_archive_feed_option_is_exit_two(stubs):
    done = _run(stubs, "--fixture", STUB_FAULT="ledger-no-option")
    assert done.returncode == 2
    assert done.stdout.splitlines() == ["UNUSABLE: ledger lacks archive feed option"]


def test_missing_form_builder_is_exit_two(stubs, tmp_path):
    done = _run(stubs, "--fixture", KNOWLEDGE_ALIVE_FORMS_SCRIPT=str(tmp_path / "absent.py"))
    assert done.returncode == 2
    assert done.stdout.splitlines() == ["UNUSABLE: forms script missing"]


def test_live_mode_with_a_missing_store_is_exit_two(stubs, tmp_path):
    done = _run(stubs, "--live", "--store-root", str(tmp_path / "absent"))
    assert done.returncode == 2
    assert done.stdout.splitlines() == ["UNUSABLE: store missing"]


def test_live_mode_with_a_store_but_no_archive_is_exit_two(stubs, tmp_path):
    done = _run(stubs, "--live", "--store-root", str(tmp_path))
    assert done.returncode == 2
    assert done.stdout.splitlines() == ["UNUSABLE: archive missing"]


def test_live_mode_without_a_registered_store_is_exit_two(module, monkeypatch):
    import corpus_resolve

    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: {"stores": {}})
    with pytest.raises(module.Unusable) as raised:
        module.registered_store_root()
    assert raised.value.reason == "store not registered"


def test_a_mode_is_required_and_the_receipt_flag_is_live_only(stubs):
    assert _run(stubs).returncode == 2
    assert _run(stubs, "--fixture", "--write-receipt").returncode == 2


# --------------------------------------------------------------------------- live mode


def _build_loop(module, stubs, tmp_path, monkeypatch):
    """Build a store, feeds, ledger and form index with the stubs, as a stand-in for a live estate."""
    for key, value in _environment(stubs).items():
        if key.startswith(("KNOWLEDGE_ALIVE_", "STUB_")):
            monkeypatch.setenv(key, value)
    work = tmp_path / "estate"
    work.mkdir()
    context = module.build_context(module.parse_args(["--fixture"]), work)
    module.prepare_fixture(context, work)
    assert context.prepare_failure is None
    return context


def _live_arguments(context, repo, *extra):
    return [
        "--live",
        "--store-root", str(context.store_root),
        "--feed-dir", str(context.feed_dir),
        "--private-root", str(context.private_root),
        "--project-root", str(context.project_root),
        "--repo-root", str(repo),
        *extra,
    ]  # fmt: skip


def _patch_registry(monkeypatch, context, tmp_path):
    import corpus_resolve

    registry = {
        "stores": {"limen-private-archive": {"root": str(context.store_root)}},
        "corpora": {"archive-all": {"store": "limen-private-archive"}},
    }
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: registry)
    monkeypatch.setattr(corpus_resolve, "corpus_home", lambda: elsewhere)


def test_live_mode_writes_then_requires_the_counts_only_receipt(module, stubs, tmp_path, monkeypatch, capsys):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path)
    repo = tmp_path / "repo"
    (repo / "docs" / "receipts").mkdir(parents=True)

    assert module.main(_live_arguments(context, repo)) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "NOT ALIVE: receipt"

    assert module.main(_live_arguments(context, repo, "--write-receipt")) == 0
    written = capsys.readouterr().out
    assert re.fullmatch(r"ALIVE [0-9a-f]{16}", written.splitlines()[-1])
    receipts = sorted((repo / "docs" / "receipts").glob("receipt-knowledge-alive-*.json"))
    assert len(receipts) == 1
    assert re.fullmatch(r"receipt-knowledge-alive-[0-9a-f]{16}-20260301\.json", receipts[0].name)
    body = json.loads(receipts[0].read_text())
    assert module.receipt_is_counts_only(body)
    assert body["fingerprint"] == written.splitlines()[-1].split()[1]
    assert SHARED_ASK not in receipts[0].read_text()

    assert module.main(_live_arguments(context, repo)) == 0
    assert capsys.readouterr().out == written

    receipts[0].write_text(json.dumps({**body, "text": SHARED_ASK}))
    assert module.main(_live_arguments(context, repo)) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "NOT ALIVE: receipt"


def test_live_mode_fails_the_registry_check_when_the_store_is_not_declared(
    module, stubs, tmp_path, monkeypatch, capsys
):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    import corpus_resolve

    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: {"stores": {}, "corpora": {}})
    repo = tmp_path / "repo"
    repo.mkdir()
    assert module.main(_live_arguments(context, repo)) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == "NOT ALIVE: registry"
    assert out[0].startswith("check 1 tools: ok") and out[1].startswith("check 2 names: ok")


# --------------------------------------------------------------------------- pure pieces


def test_registry_problems(module, tmp_path):
    store = tmp_path / "store"
    (store / "archive-all").mkdir(parents=True)
    home = tmp_path / "home"
    good = {
        "stores": {"limen-private-archive": {"root": str(store)}},
        "corpora": {"archive-all": {"store": "limen-private-archive"}, "other": {"store": "another-store"}},
    }
    assert module.registry_problems(good, store, home) == []
    assert "store is not declared" in module.registry_problems({**good, "stores": {}}, store, home)
    renamed = {**good, "corpora": {"archive": {"store": "limen-private-archive"}}}
    assert "a row key is not a directory name" in module.registry_problems(renamed, store, home)
    (store / "corpus-chatgpt-archive").mkdir()
    assert "a directory has no row" in module.registry_problems(good, store, home)
    assert "store is the corpus home" in module.registry_problems(good, store, store)


def test_index_problems(module):
    row = {
        "form": "pattern-all-" + "a" * 16,
        "atom_id": "pa-1",
        "provider": "chatgpt",
        "source": "archive-chatgpt-messages",
    }
    assert module.index_problems([row, {**row, "atom_id": "pa-2"}]) == []
    assert "index carries a text field" in module.index_problems([{**row, "text": "x"}])
    assert "index holds a value over the length limit" in module.index_problems([{**row, "note": "x" * 201}])
    assert "a member is in two forms" in module.index_problems([row, {**row, "form": "pattern-all-" + "b" * 16}])
    assert "a form name is malformed" in module.index_problems([{**row, "form": "pattern-all-short"}])
    assert "a member has no atom id" in module.index_problems([{**row, "atom_id": ""}])


def test_value_scan_is_exact_and_ignores_short_values(module):
    values = {"chatgpt-conv-alpha", "Synthetic planning thread", "short", "f" * 64}
    index = module.build_leak_index(values)
    assert module.leaked_values("see chatgpt-conv-alpha here", index) == {"chatgpt-conv-alpha"}
    assert module.leaked_values("see chatgpt-conv-alphb here", index) == set()
    assert module.leaked_values("a Synthetic planning thread, again", index) == {"Synthetic planning thread"}
    assert module.leaked_values("a synthetic planning thread, again", index) == set()
    assert module.leaked_values("short short short", index) == set()
    assert module.leaked_values("hash " + "f" * 64 + " end", index) == {"f" * 64}
    assert module.leaked_values("hash " + "f" * 63 + "e end", index) == set()


def test_root_is_private_means_outside_a_work_tree_or_git_ignored(module, tmp_path):
    assert module.root_is_private(tmp_path)
    work = tmp_path / "work"
    (work / "hidden").mkdir(parents=True)
    (work / "visible").mkdir()
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    (work / ".gitignore").write_text("hidden/\n")
    assert module.root_is_private(work / "hidden")
    assert not module.root_is_private(work / "visible")


def test_name_shape_and_activity_day(module, tmp_path):
    kinds = {"receipt", "feed"}
    assert module.name_shape_problem("receipt-knowledge-alive-" + "a" * 16 + "-20260301", kinds) is None
    assert module.name_shape_problem("Receipt-x", kinds) is not None
    assert module.name_shape_problem("report-x", kinds) is not None
    assert module.name_shape_problem("feed-" + "x" * 80, kinds) is not None
    folder = tmp_path / "provider-chatgpt"
    folder.mkdir(parents=True)
    (folder / "index-chatgpt-conversations.jsonl").write_text(
        json.dumps({"last_activity": "2026-02-30T00:00:00Z"}) + "\n"
        + json.dumps({"last_activity": "2026-03-02T09:00:00Z"}) + "\n"
        + json.dumps({"last_activity": ""}) + "\n"
    )  # fmt: skip
    context = SimpleNamespace(archive_root=tmp_path)
    assert module.latest_activity_day(context, ["chatgpt", "absent"]) == "20260302"


def test_receipt_shape_is_counts_only(module):
    body = {"counts": {"forms": 1}, "date": "20260301", "fingerprint": "a" * 16, "kind": "receipt", "naming_version": 1}
    assert module.receipt_is_counts_only(body)
    assert not module.receipt_is_counts_only({**body, "counts": {"forms": "one"}})
    assert not module.receipt_is_counts_only({**body, "text": "x"})
    assert not module.receipt_is_counts_only({**body, "fingerprint": "a" * 33})


def test_the_receipt_name_is_a_listed_kind_in_lowercase_hyphenated_words(module):
    name = module.receipt_name({"prefix": "0123456789abcdef"}, "20260301")
    assert name == "receipt-knowledge-alive-0123456789abcdef-20260301"
    assert module.name_shape_problem(name, {"receipt"}) is None


# --------------------------------------------------------------------------- real engine, opt in


@pytest.mark.skipif(
    not os.environ.get("KNOWLEDGE_ALIVE_ENGINE"),
    reason="set KNOWLEDGE_ALIVE_ENGINE to an engine checkout to run the loop against the real engine",
)
def test_real_engine_fixture_loop_is_alive():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("KNOWLEDGE_ALIVE_LEDGER", "KNOWLEDGE_ALIVE_FORMS"))}
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture"], capture_output=True, text=True, env=env, timeout=900, check=False
    )
    assert done.returncode == 0, done.stdout
    assert re.fullmatch(r"ALIVE [0-9a-f]{16}", done.stdout.splitlines()[-1])
