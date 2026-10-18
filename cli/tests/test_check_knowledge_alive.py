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
        elif "names-three" in FAULTS:
            version = 3
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
        # Like the engine, walk every entry under the root: each must be a kind word plus more, never a bare kind.
        for entry in Path(option("--root")).iterdir():
            stem = entry.name.split(".")[0]
            if "-" not in stem or stem.split("-")[0] not in KINDS:
                return 1
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
            rows, seen, excluded = [], 0, {}
            path = archive / f"provider-{provider}" / f"collection-{provider}-conversations.jsonl"
            for line in path.read_text().splitlines():
                conversation = json.loads(line)
                items = [(m, False) for m in conversation["messages"]]
                items += [(m, True) for m in conversation["extra"].get("alternate_messages", [])]
                for message, alternate in items:
                    seen += 1
                    if conversation["kind"] not in ELIGIBLE:
                        reason = "kind-" + conversation["kind"]
                    elif message["role"] != "user":
                        reason = "role-" + message["role"]
                    elif message["channel"] != "typed":
                        reason = "channel-" + message["channel"]
                    else:
                        reason = None
                    if reason:
                        excluded[reason] = excluded.get(reason, 0) + 1
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
            declared = len(rows)
            if rows and "feed-extra-row" in FAULTS:
                rows.append({**rows[0], "event_index": len(rows), "event_ref": "msg-extra-row"})
            text = lines(rows)
            (out / f"feed-{provider}-prompts.jsonl").write_text(text)
            prefix = "0" * 16 if "stale-receipt" in FAULTS else hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
            named_day = "20250101" if "receipt-day-name" in FAULTS else day
            if excluded and "receipt-excluded-off" in FAULTS:
                excluded[sorted(excluded)[0]] += 1
            receipt = {"feed_sha256": hashlib.sha256(text.encode()).hexdigest(),
                       "rows": declared + (1 if "row-count" in FAULTS else 0),
                       "alternate_rows": sum(1 for row in rows if "branch" in row) + (
                           1 if "receipt-alternate-off" in FAULTS else 0),
                       "messages_seen": seen, "excluded": excluded,
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
texts = []
for feed in feeds:
    for line in Path(feed).read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        texts.append(event.get("text", ""))
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
checkpoint_rows = rows[:-1] if rows and "snapshot-drop" in FAULTS else rows
sources = {}
for row in checkpoint_rows:
    sources[row["occurrence"]["source"]] = sources.get(row["occurrence"]["source"], 0) + 1
(journal.parent / "prompt-atom-ledger.json").write_text(json.dumps(
    {"coverage": {"occurrences": len(checkpoint_rows)}, "counts": {"sources": sources}}))
markdown =Path(option("--public-markdown"))
markdown.parent.mkdir(parents=True, exist_ok=True)
leaked = rows[0]["occurrence"]["source_locator"].split("#")[0] if rows and "leak" in FAULTS else ""
if texts and "leak-text" in FAULTS:
    leaked = texts[0]
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
        # Check 3 imports check-corpora's own checks, so the real script is used, never a stub.
        corpora=SCRIPTS / "check-corpora.py",
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


def test_output_is_deterministic_and_carries_only_counts_names_and_the_engine_path(stubs):
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
    ("feed-extra-row", "ledger binding"),
    ("receipt-excluded-off", "ledger binding"),
    ("receipt-alternate-off", "ledger binding"),
    ("provenance", "ledger binding"),
    ("source-name", "ledger binding"),
    ("ledger-drop", "ledger binding"),
    ("ledger-operator", "ledger binding"),
    ("snapshot-drop", "ledger binding"),
    ("forms-text", "recurring forms"),
    ("forms-none", "recurring forms"),
    ("forms-verify-fails", "recurring forms"),
    ("leak", "privacy"),
    ("leak-text", "privacy"),
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
        (
            "feed-extra-row",
            6,
            "chatgpt: the feed holds a different number of rows than its receipt declares",
        ),
        (
            "row-count",
            6,
            "chatgpt: the feed holds a different number of rows than its receipt declares",
        ),
        (
            "receipt-alternate-off",
            6,
            "chatgpt: the feed holds a different number of alternate rows than its receipt declares",
        ),
        (
            "receipt-excluded-off",
            6,
            "chatgpt: the receipt does not reconcile: rows plus excluded differ from messages seen",
        ),
    ],
)
def test_feed_failures_name_the_provider(stubs, fault, check, reason):
    done = _run(stubs, "--fixture", STUB_FAULT=fault)
    failing = [line for line in done.stdout.splitlines() if ": FAIL" in line]
    assert len(failing) == 1 and f"check {check} " in failing[0] and failing[0].endswith(f"FAIL {reason}"), failing


def test_a_receipt_with_exclusions_and_alternate_rows_passes_check_six(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    receipts = sorted(context.feed_dir.glob("receipt-*-prompts-*.json"))
    assert receipts
    for path in receipts:
        body = json.loads(path.read_text())
        assert body["excluded"] and body["alternate_rows"] > 0
        assert body["rows"] + sum(body["excluded"].values()) == body["messages_seen"]
    lines, code = module.evaluate(context)
    assert code == 0, lines
    assert lines[5].startswith("check 6 ledger binding: ok")


def test_composition_problem_holds_a_feed_to_its_receipt_only(module):
    rows = [{"event_ref": "a"}, {"event_ref": "b", "branch": "alternate"}]
    receipt = {"rows": 2, "alternate_rows": 1, "messages_seen": 5, "excluded": {"role-assistant": 2, "empty-text": 1}}
    assert module.composition_problem(receipt, rows) is None
    assert module.composition_problem({**receipt, "excluded": {}, "messages_seen": 2}, rows) is None
    assert "reconcile" in module.composition_problem({**receipt, "messages_seen": 6}, rows)
    assert "reconcile" in module.composition_problem({**receipt, "messages_seen": 4}, rows)
    assert "different number of rows" in module.composition_problem({**receipt, "rows": 1}, rows)
    assert "different number of rows" in module.composition_problem(receipt, [*rows, {"event_ref": "c"}])
    assert "alternate rows" in module.composition_problem({**receipt, "alternate_rows": 0}, rows)
    assert "alternate rows" in module.composition_problem({**receipt, "alternate_rows": 3}, rows)
    assert "no excluded counts" in module.composition_problem({**receipt, "excluded": None}, rows)
    for broken in ({"rows": True}, {"messages_seen": "5"}, {"excluded": {"empty-text": -1}}, {"alternate_rows": 1.0}):
        assert "whole number" in module.composition_problem({**receipt, **broken}, rows)


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


def _registry_document(root) -> dict:
    return {
        "stores": {"limen-private-archive": {"root": str(root)}},
        "corpora": {"archive-all": {"store": "limen-private-archive", "kind": "normalized-archive"}},
    }


def _patch_registry(monkeypatch, context, tmp_path, registry=None):
    import corpus_resolve

    registry = registry or _registry_document(context.store_root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: registry)
    monkeypatch.setattr(corpus_resolve, "corpus_home", lambda: elsewhere)


def _write_public_files(repo: Path) -> None:
    """The three tracked public files the privacy check requires, with counts-only synthetic content."""
    (repo / "docs" / "receipts").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "IDEAL-FORMS-LEDGER.md").write_text("# Ideal forms\n\nCounts only.\n", encoding="utf-8")
    (repo / "docs" / "prompt-atom-ledger.md").write_text("# Ledger\n\nCounts only.\n", encoding="utf-8")
    (repo / "docs" / "prompt-authority-seal.json").write_text("{}\n", encoding="utf-8")


def test_live_mode_writes_then_requires_the_counts_only_receipt(module, stubs, tmp_path, monkeypatch, capsys):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path)
    repo = tmp_path / "repo"
    _write_public_files(repo)

    assert module.main(_live_arguments(context, repo)) == 1
    first = capsys.readouterr().out.splitlines()
    assert first[-1] == "NOT ALIVE: receipt"
    # Three tracked files are scanned. The snapshot lives inside the private root and is not public.
    assert re.fullmatch(r"check 8 privacy: ok 3 public files scanned, [1-9]\d* values checked, none found", first[7])

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

    receipts[0].write_text(json.dumps({**body, "note": "an extra key"}))
    assert module.main(_live_arguments(context, repo)) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "NOT ALIVE: receipt"

    # A well-shaped receipt copied from another run still fails: the body must match this run.
    tampered = [
        ({"counts": {**body["counts"], "forms": body["counts"]["forms"] + 1}}, "counts"),
        ({"naming_version": 7}, "naming version"),
        ({"date": "20250101"}, "date"),
        ({"fingerprint": "0" * 16}, "fingerprint"),
    ]
    for change, field in tampered:
        receipts[0].write_text(json.dumps({**body, **change}))
        assert module.main(_live_arguments(context, repo)) == 1
        lines = capsys.readouterr().out.splitlines()
        assert lines[8] == f"check 9 receipt: FAIL the receipt differs from this run in its {field}", lines
        assert lines[-1] == "NOT ALIVE: receipt"
    receipts[0].write_text(json.dumps(body))
    assert module.main(_live_arguments(context, repo)) == 0
    capsys.readouterr()

    # A receipt that carried a typed ask would be caught by the privacy scan before the receipt check.
    receipts[0].write_text(json.dumps({**body, "text": SHARED_ASK}))
    assert module.main(_live_arguments(context, repo)) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "NOT ALIVE: privacy"


def test_the_receipt_carries_the_naming_version_the_engine_reported(module, stubs, tmp_path, monkeypatch, capsys):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path)
    monkeypatch.setenv("STUB_FAULT", "names-three")
    repo = tmp_path / "repo"
    _write_public_files(repo)
    assert module.main(_live_arguments(context, repo, "--write-receipt")) == 0
    (path,) = (repo / "docs" / "receipts").glob("receipt-knowledge-alive-*.json")
    assert json.loads(path.read_text())["naming_version"] == 3
    assert module.main(_live_arguments(context, repo)) == 0
    # The same receipt no longer matches once the engine reports another version.
    monkeypatch.setenv("STUB_FAULT", "")
    assert module.main(_live_arguments(context, repo)) == 1
    capsys.readouterr()


def _record_reprojection_targets(module, monkeypatch) -> list[Path]:
    """Spy on the engine: the --out directory of every feed projection, and whether it existed at the time."""
    targets: list[Path] = []
    original = module.Engine.run

    def spy(self, args, **keywords):
        if args[:3] == ["archive", "project", "feed"]:
            out = Path(args[args.index("--out") + 1])
            targets.append(out)
        return original(self, args, **keywords)

    monkeypatch.setattr(module.Engine, "run", spy)
    return targets


def test_live_reprojection_scratch_is_inside_the_private_root_and_gone_afterwards(
    module, stubs, tmp_path, monkeypatch, capsys
):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path)
    repo = tmp_path / "repo"
    _write_public_files(repo)
    targets = _record_reprojection_targets(module, monkeypatch)
    assert module.main(_live_arguments(context, repo, "--write-receipt")) == 0
    capsys.readouterr()
    assert len(targets) >= 2  # once per pass
    private = context.private_root.resolve()
    for target in targets:
        assert target.resolve().is_relative_to(private / "scratch")
        assert target.name.startswith("knowledge-alive-reproject-")
        assert not target.exists()
    assert list((private / "scratch").iterdir()) == []
    assert (private / "scratch").stat().st_mode & 0o777 == 0o700


def test_live_reprojection_scratch_is_removed_when_the_engine_fails(module, stubs, tmp_path, monkeypatch, capsys):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path)
    repo = tmp_path / "repo"
    _write_public_files(repo)
    targets = _record_reprojection_targets(module, monkeypatch)
    monkeypatch.setenv("STUB_FAULT", "reproject-differs")
    assert module.main(_live_arguments(context, repo)) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "NOT ALIVE: ledger binding"
    assert len(targets) == 1 and not targets[0].exists()
    assert list((context.private_root / "scratch").iterdir()) == []


def test_fixture_reprojection_scratch_stays_in_the_work_directory(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    targets = _record_reprojection_targets(module, monkeypatch)
    lines, code = module.evaluate(context)
    assert code == 0, lines
    assert targets and all(target.resolve().is_relative_to(context.work_dir.resolve()) for target in targets)
    assert not any(target.exists() for target in targets)


def test_feeds_sit_flat_in_the_archive_root_in_both_modes(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    assert context.feed_dir == context.archive_root
    assert sorted(path.name for path in context.archive_root.glob("feed-*-prompts.jsonl")) == [
        "feed-chatgpt-prompts.jsonl",
        "feed-claude-prompts.jsonl",
    ]
    assert not (context.archive_root / "feed").exists()
    live = module.build_context(
        module.parse_args(["--live", "--store-root", str(context.store_root), "--private-root", str(tmp_path / "p")]),
        None,
    )
    assert live.feed_dir == live.archive_root == context.archive_root


def test_the_engine_state_directory_beside_the_archive_is_not_a_name_problem(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    # The engine creates state/ when the store is its own project root, which is how the live store is registered.
    (context.store_root / "state").mkdir(exist_ok=True)
    lines, code = module.evaluate(context)
    assert code == 0, lines
    assert lines[1] == "check 2 names: ok 1 store directories"
    assert re.fullmatch(r"ALIVE [0-9a-f]{16}", lines[-1])


def test_any_other_unknown_store_directory_still_fails_the_names_check(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    (context.store_root / "state").mkdir(exist_ok=True)
    (context.store_root / "scratchpad").mkdir()
    lines, code = module.evaluate(context)
    assert code == 1
    assert lines[1] == "check 2 names: FAIL a store directory name is not a listed kind"
    assert lines[-1] == "NOT ALIVE: names"


def test_the_exempt_directories_are_the_resolvers_list_not_a_copy(module, tmp_path):
    import corpus_resolve

    for name in sorted(corpus_resolve.NON_CORPUS_DIRS):
        (tmp_path / name).mkdir()
    (tmp_path / "archive-all").mkdir()
    assert module.store_directory_names(tmp_path) == ["archive-all"]
    assert "state" in corpus_resolve.NON_CORPUS_DIRS


def test_a_feed_subfolder_in_the_archive_fails_the_names_check(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    (context.archive_root / "feed").mkdir()
    lines, code = module.evaluate(context)
    assert code == 1
    assert lines[1] == "check 2 names: FAIL the engine rejects a name under the archive"


def test_drift_in_an_unrelated_store_is_counted_but_does_not_fail_check_three(
    module, stubs, tmp_path, monkeypatch, capsys
):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    # A git-backed store whose root exists but is not a worktree: check-corpora's check B fails for it.
    unrelated = tmp_path / "unrelated-store"
    unrelated.mkdir()
    registry = {
        "stores": {
            "session-meta": {"root": str(unrelated), "git": True},
            "limen-private-archive": {"root": str(context.store_root)},
        },
        "corpora": {
            "session-transcripts": {"store": "session-meta", "kind": "raw-archive"},
            "archive-all": {"store": "limen-private-archive", "kind": "normalized-archive"},
        },
    }
    _patch_registry(monkeypatch, context, tmp_path, registry)
    repo = tmp_path / "repo"
    _write_public_files(repo)
    assert module.main(_live_arguments(context, repo, "--write-receipt")) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[2] == "check 3 registry: ok store limen-private-archive bound; registry drifts elsewhere: 1"
    assert re.fullmatch(r"ALIVE [0-9a-f]{16}", out[-1])
    assert str(unrelated) not in "\n".join(out)


def test_the_archive_store_drifting_fails_check_three(module, stubs, tmp_path, monkeypatch, capsys):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _write_public_files(repo)
    # A directory beside archive-all that has no row fails; the engine's own state directory does not. The name
    # starts with a listed kind so that check 2 passes and the failure is check 3's.
    (context.store_root / "state").mkdir(exist_ok=True)
    _patch_registry(monkeypatch, context, tmp_path)
    assert module.main(_live_arguments(context, repo, "--write-receipt")) == 0
    capsys.readouterr()
    (context.store_root / "report-notes").mkdir()
    assert module.main(_live_arguments(context, repo)) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[2] == "check 3 registry: FAIL a directory has no row"
    assert out[-1] == "NOT ALIVE: registry"


def test_the_registered_root_missing_fails_check_three(module, stubs, tmp_path, monkeypatch, capsys):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path, _registry_document(tmp_path / "gone"))
    repo = tmp_path / "repo"
    _write_public_files(repo)
    assert module.main(_live_arguments(context, repo)) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[2] == "check 3 registry: FAIL the registered store is not the store under check"
    assert out[-1] == "NOT ALIVE: registry"


def test_check_corpora_checks_b_and_c_run_for_the_archive_store_alone(module, tmp_path):
    corpora = module.load_corpora_checks(SCRIPTS / "check-corpora.py")
    store = tmp_path / "archive-store"
    (store / "archive-all").mkdir(parents=True)
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    registry = {
        "stores": {"other": {"root": str(unrelated), "git": True}, "limen-private-archive": {"root": str(store)}},
        "corpora": {
            "other-row": {"store": "other", "kind": "raw-archive"},
            "archive-all": {"store": "limen-private-archive", "kind": "normalized-archive"},
        },
    }
    assert module.corpora_drifts(corpora, registry) == ([], 1)

    (store / "state").mkdir()  # the engine's own directory is exempt in check C
    assert module.corpora_drifts(corpora, registry) == ([], 1)

    (store / "scratchpad").mkdir()  # any other unknown directory is a drift in this store
    own, elsewhere = module.corpora_drifts(corpora, registry)
    assert [drift.split(":", 1)[0] for drift in own] == ["C"] and elsewhere == 1

    (store / "scratchpad").rmdir()
    registry["corpora"]["archive-gone"] = {"store": "limen-private-archive", "kind": "normalized-archive"}
    own, elsewhere = module.corpora_drifts(corpora, registry)  # a declared row with no directory
    assert [drift.split(":", 1)[0] for drift in own] == ["C"] and elsewhere == 1


def test_a_corpora_script_without_the_single_store_checks_is_unusable(module, tmp_path):
    script = tmp_path / "check-corpora.py"
    script.write_text("FAILURES = []\n", encoding="utf-8")
    with pytest.raises(module.Unusable):
        module.load_corpora_checks(script)
    with pytest.raises(module.Unusable):
        module.load_corpora_checks(tmp_path / "absent.py")


def test_a_file_inside_the_private_root_is_not_public_but_a_leak_in_docs_is(
    module, stubs, tmp_path, monkeypatch, capsys
):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path)
    repo = tmp_path / "repo"
    _write_public_files(repo)
    # The default public snapshot sits inside the private root: it is excluded from the scan, not flagged.
    (context.private_dir / "prompt-atom-index.json").write_text(json.dumps({"note": SHARED_ASK}), encoding="utf-8")
    assert module.main(_live_arguments(context, repo, "--write-receipt")) == 0
    # The three tracked files plus the receipt this run wrote; the snapshot in the private root is not counted.
    assert "check 8 privacy: ok 4 public files scanned" in capsys.readouterr().out
    (repo / "docs" / "receipts" / "note.md").write_text(f"see {SHARED_ASK} here", encoding="utf-8")
    assert module.main(_live_arguments(context, repo)) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "NOT ALIVE: privacy"


def test_a_missing_required_public_file_is_named(module, stubs, tmp_path, monkeypatch, capsys):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    _patch_registry(monkeypatch, context, tmp_path)
    repo = tmp_path / "repo"
    _write_public_files(repo)
    (repo / "docs" / "prompt-authority-seal.json").unlink()
    assert module.main(_live_arguments(context, repo)) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[7] == "check 8 privacy: FAIL required public file prompt-authority-seal.json is missing"
    assert out[-1] == "NOT ALIVE: privacy"


def test_a_privacy_check_that_scanned_no_file_fails(module, tmp_path):
    repo = tmp_path / "repo"
    _write_public_files(repo)
    context = SimpleNamespace(
        store_root=tmp_path,
        archive_root=tmp_path,
        repo_root=repo,
        public_markdown=repo / "docs" / "prompt-atom-ledger.md",
        public_seal=repo / "docs" / "prompt-authority-seal.json",
        public_snapshot=repo / "docs" / "prompt-atom-index.json",
        private_root=repo,  # every candidate resolves inside the private root, so none is public
    )
    result = module.check_privacy(context, {})
    assert not result.ok and result.detail == "no public file was scanned"


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


@pytest.mark.parametrize(
    ("which", "reason"),
    [
        ("store", "the registered store is not the store under check"),
        ("archive", "the registered archive is not the archive under check"),
    ],
)
def test_live_mode_requires_the_registry_to_name_the_store_under_check(
    module, stubs, tmp_path, monkeypatch, capsys, which, reason
):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    import corpus_resolve

    root = tmp_path / "another-store" if which == "store" else context.store_root
    registry = _registry_document(root)
    if which == "archive":
        registry["corpora"]["archive-all"]["path"] = "somewhere-else"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: registry)
    monkeypatch.setattr(corpus_resolve, "corpus_home", lambda: elsewhere)
    repo = tmp_path / "repo"
    repo.mkdir()
    assert module.main(_live_arguments(context, repo)) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[2] == f"check 3 registry: FAIL {reason}"
    assert out[-1] == "NOT ALIVE: registry"


# --------------------------------------------------------------------------- robustness


def test_an_unexpected_exception_fails_that_check_with_its_type_only(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)

    def explode(ctx, state):
        raise RuntimeError(f"unexpected {SHARED_ASK} at /private/path")

    checks = tuple((name, explode if name == "recurring forms" else function) for name, function in module.CHECKS)
    monkeypatch.setattr(module, "CHECKS", checks)
    lines, code = module.evaluate(context)
    assert code == 1
    assert lines[5].startswith("check 6 ledger binding: ok")
    assert lines[6] == "check 7 recurring forms: FAIL internal error in recurring forms (RuntimeError)"
    assert all(line.endswith(": not run") for line in lines[7:10])
    assert lines[-1] == "NOT ALIVE: recurring forms"
    assert SHARED_ASK not in "\n".join(lines) and "/private/path" not in "\n".join(lines)


def test_an_unusable_environment_inside_a_check_is_not_swallowed(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)

    def unusable(ctx, state):
        raise module.Unusable("git is unavailable")

    checks = tuple((name, unusable if name == "privacy" else function) for name, function in module.CHECKS)
    monkeypatch.setattr(module, "CHECKS", checks)
    with pytest.raises(module.Unusable):
        module.evaluate(context)


@pytest.mark.parametrize("bad_line", [b"{not json SENTINEL-TEXT\n", b"[1, 2, 3]\n", b"\xff\xfe SENTINEL-TEXT\n"])
def test_a_malformed_row_fails_its_check_with_the_line_number_only(module, stubs, tmp_path, monkeypatch, bad_line):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    # The conversation index is read by the privacy check, after the feed checks have passed.
    index = context.archive_root / "provider-chatgpt" / "index-chatgpt-conversations.jsonl"
    with index.open("ab") as handle:
        handle.write(bad_line)
    lines, code = module.evaluate(context)
    assert code == 1
    assert lines[7] == "check 8 privacy: FAIL line 3 of index-chatgpt-conversations.jsonl is not a JSON object"
    assert lines[-1] == "NOT ALIVE: privacy"
    assert "SENTINEL" not in "\n".join(lines)


def test_read_rows_names_the_line_of_a_malformed_row(module, tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_bytes(b'{"a": 1}\n\n{"b": \n')
    with pytest.raises(module.MalformedRow) as raised:
        list(module.read_rows(path))
    assert str(raised.value) == "line 3 of rows.jsonl is not a JSON object"
    assert isinstance(raised.value, ValueError)


def test_a_missing_private_ledger_snapshot_fails_the_ledger_binding(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    (context.private_dir / "prompt-atom-ledger.json").unlink()
    lines, code = module.evaluate(context)
    assert code == 1
    assert lines[5] == "check 6 ledger binding: FAIL the private ledger snapshot is missing or unreadable"


def test_a_snapshot_short_of_a_journal_archive_occurrence_is_named(module, stubs, tmp_path, monkeypatch):
    context = _build_loop(module, stubs, tmp_path, monkeypatch)
    snapshot = context.private_dir / "prompt-atom-ledger.json"
    body = json.loads(snapshot.read_text())
    body["counts"]["sources"]["archive-chatgpt-messages"] -= 1
    snapshot.write_text(json.dumps(body))
    lines, code = module.evaluate(context)
    assert code == 1
    assert (
        lines[5] == "check 6 ledger binding: FAIL the private ledger snapshot lacks an archive occurrence "
        "that is in the journal"
    )


# --------------------------------------------------------------------------- pure pieces


def test_registry_problems(module, tmp_path):
    store = tmp_path / "store"
    (store / "archive-all").mkdir(parents=True)
    home = tmp_path / "home"
    archive_row = {"store": "limen-private-archive", "kind": "normalized-archive"}
    good = {
        "stores": {"session-store": {"root": "x"}, "limen-private-archive": {"root": str(store)}},
        "corpora": {"archive-all": archive_row, "other": {"store": "session-store", "kind": "session-memory"}},
    }
    assert module.registry_problems(good, store, home) == []
    assert "store is not declared" in module.registry_problems({**good, "stores": {}}, store, home)
    renamed = {**good, "corpora": {"archive": archive_row}}
    assert "a row key is not a directory name" in module.registry_problems(renamed, store, home)
    wrong_kind = {**good, "corpora": {**good["corpora"], "archive-all": {**archive_row, "kind": "session-memory"}}}
    assert "the archive row is not declared as a normalized archive" in module.registry_problems(
        wrong_kind, store, home
    )
    declared_first = {**good, "stores": {"limen-private-archive": {"root": str(store)}, "session-store": {"root": "x"}}}
    assert "the store is declared before a store holding other kinds" in module.registry_problems(
        declared_first, store, home
    )
    (store / "state").mkdir()  # the engine's own directory is not a corpus and needs no row
    assert module.registry_problems(good, store, home) == []
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


def _git_answers(module, monkeypatch, *answers):
    replies = iter(answers)

    def answer(argv, *, env, timeout):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return module.Completed(*reply)

    monkeypatch.setattr(module, "run_process", answer)


def test_root_is_private_treats_only_not_a_git_repository_as_outside_every_work_tree(module, tmp_path, monkeypatch):
    _git_answers(module, monkeypatch, (128, "", "fatal: not a git repository (or any of the parent directories): .git"))
    assert module.root_is_private(tmp_path) is True


@pytest.mark.parametrize(
    "answers",
    [
        [(128, "", "fatal: detected dubious ownership in repository")],
        [(128, "", "fatal: cannot change to a directory")],
        [(124, "", "timed out")],
        [(1, "", "")],
        [FileNotFoundError("git")],
        [PermissionError("git")],
        [(0, "/work\n", ""), (128, "", "fatal: unable to read the index")],
    ],
)
def test_root_is_private_is_unusable_when_git_cannot_answer(module, tmp_path, monkeypatch, answers):
    _git_answers(module, monkeypatch, *answers)
    with pytest.raises(module.Unusable):
        module.root_is_private(tmp_path)


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
