"""schedule-census contract (gates.yaml: schedule-census-test).

Drives scripts/schedule-census.py against a stubbed `gh api` and real temp git repositories — never the
network — and pins the data-grounding rules the receipt must keep: an unreachable repository is never
"nothing scheduled", a claim counts only from evidence, denominators are stated before conclusions, and a
budget cut lists what it left unscanned.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


C = _load("limen_test_schedule_census", "schedule-census.py")


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────


def _b64(text: str) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(text.encode()).decode()}


WORKFLOW_CRON = "on:\n  schedule:\n    - cron: '36 13 * * *'\n  workflow_dispatch:\njobs: {}\n"
WORKFLOW_NO_CRON = "on:\n  push:\njobs: {}\n"
WORKFLOW_DISABLED = "on:\n  schedule:\n    - cron: '0 */4 * * *'\njobs: {}\n"


def _table(repo: str = "4444J99/example", *, total_runs: int = 3, last_conclusion: str = "success") -> dict:
    """A fake GitHub for one repository: tree → carriers → states → runs → commits."""
    runs = [
        {"name": "hygiene", "created_at": f"2026-10-2{i}T13:36:00Z", "conclusion": last_conclusion} for i in (3, 2, 1)
    ][:total_runs]
    commits = [{"sha": "a" * 40}, {"sha": "b" * 40}]
    return {
        f"repos/{repo}": (
            C.OK,
            {"private": True, "archived": False, "default_branch": "main", "pushed_at": "2026-10-23T00:00:00Z"},
        ),
        f"repos/{repo}/git/trees/main?recursive=1": (
            C.OK,
            {
                "truncated": False,
                "tree": [
                    {"type": "blob", "path": ".github/workflows/hygiene.yml"},
                    {"type": "blob", "path": ".github/workflows/build.yml"},
                    {"type": "blob", "path": ".github/workflows/old-scale.yml"},
                    {"type": "blob", "path": "wrangler.toml"},
                    {"type": "blob", "path": "vercel.json"},
                    {"type": "blob", "path": "launchd/com.example.beat.plist"},
                    {"type": "blob", "path": ".github/dependabot.yml"},
                    {"type": "blob", "path": "cloudflare/src/manifest.ts"},
                    {"type": "blob", "path": "README.md"},
                    {"type": "tree", "path": ".github"},
                ],
            },
        ),
        f"repos/{repo}/actions/workflows?per_page=100": (
            C.OK,
            {
                "workflows": [
                    {"path": ".github/workflows/hygiene.yml", "state": "active", "name": "hygiene", "id": 1},
                    {"path": ".github/workflows/build.yml", "state": "active", "name": "build", "id": 2},
                    {
                        "path": ".github/workflows/old-scale.yml",
                        "state": "disabled_inactivity",
                        "name": "old-scale",
                        "id": 3,
                    },
                    {"path": ".github/workflows/tmp-diag.yml", "state": "active", "name": "tmp diag", "id": 4},
                ]
            },
        ),
        f"repos/{repo}/contents/.github/workflows/hygiene.yml?ref=main": (C.OK, _b64(WORKFLOW_CRON)),
        f"repos/{repo}/contents/.github/workflows/build.yml?ref=main": (C.OK, _b64(WORKFLOW_NO_CRON)),
        f"repos/{repo}/contents/.github/workflows/old-scale.yml?ref=main": (C.OK, _b64(WORKFLOW_DISABLED)),
        f"repos/{repo}/contents/wrangler.toml?ref=main": (
            C.OK,
            _b64('name = "w"\n[triggers]\ncrons = ["*/30 * * * *"]\n'),
        ),
        f"repos/{repo}/contents/vercel.json?ref=main": (
            C.OK,
            _b64(json.dumps({"crons": [{"path": "/api/tick", "schedule": "0 5 * * *"}]})),
        ),
        f"repos/{repo}/contents/launchd/com.example.beat.plist?ref=main": (
            C.OK,
            _b64(
                '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0"><dict><key>Label</key><string>com.example.beat</string><key>StartInterval</key><integer>1800</integer></dict></plist>\n'
            ),
        ),
        f"repos/{repo}/contents/.github/dependabot.yml?ref=main": (
            C.OK,
            _b64(
                "version: 2\nupdates:\n  - package-ecosystem: npm\n    directory: /\n    schedule:\n      interval: weekly\n      day: monday\n"
            ),
        ),
        f"repos/{repo}/contents/cloudflare/src/manifest.ts?ref=main": (
            C.OK,
            _b64(
                "export const targets = [\n  { name: 'bountyscope', maxInvocationsPerDay: 48,\n    schedule: '*/30 * * * *' },\n];\n"
            ),
        ),
        f"repos/{repo}/actions/runs?event=schedule&per_page=100": (
            C.OK,
            {"total_count": total_runs, "workflow_runs": runs},
        ),
        f"repos/{repo}/issues?state=all&per_page=100&page=1&sort=created&direction=desc": (
            C.OK,
            [
                {
                    "number": 7,
                    "title": "Add nightly cron for the digest",
                    "state": "closed",
                    "created_at": "2026-05-01T00:00:00Z",
                    "closed_at": "2026-05-03T00:00:00Z",
                    "labels": [{"name": "automation"}],
                },
                {
                    "number": 9,
                    "title": "feat: scheduled task runner",
                    "state": "closed",
                    "created_at": "2026-06-01T00:00:00Z",
                    "closed_at": "2026-06-02T00:00:00Z",
                    "labels": [],
                    "pull_request": {"url": "x", "merged_at": "2026-06-02T00:00:00Z"},
                },
                {
                    "number": 11,
                    "title": "Fix typo in README",
                    "state": "open",
                    "created_at": "2026-07-01T00:00:00Z",
                    "closed_at": None,
                    "labels": [],
                },
                {
                    "number": 12,
                    "title": "Rotate keys",
                    "state": "open",
                    "created_at": "2026-07-02T00:00:00Z",
                    "closed_at": None,
                    "labels": [{"name": "heartbeat"}],
                },
            ],
        ),
        f"repos/{repo}/commits?path=.github/workflows&per_page=100": (C.OK, commits),
        f"repos/{repo}/commits/{'a' * 40}": (
            C.OK,
            {
                "commit": {"committer": {"date": "2026-10-20T00:00:00Z"}},
                "files": [
                    {
                        "filename": ".github/workflows/hygiene.yml",
                        "status": "modified",
                        "patch": "@@\n-    - cron: '0 13 * * *'\n+    - cron: '36 13 * * *'\n",
                    },
                    {"filename": "README.md", "status": "modified", "patch": "+- cron: 'not a workflow'"},
                ],
            },
        ),
        f"repos/{repo}/commits/{'b' * 40}": (
            C.OK,
            {
                "commit": {"committer": {"date": "2026-06-01T00:00:00Z"}},
                "files": [
                    {
                        "filename": ".github/workflows/nightly.yml",
                        "status": "removed",
                        "patch": '-on:\n-  schedule:\n-    - cron: "0 2 * * *"\n',
                    }
                ],
            },
        ),
    }


class FakeGH:
    def __init__(self, table: dict):
        self.table = table
        self.calls: list[str] = []

    def __call__(self, path: str):
        self.calls.append(path)
        if path in self.table:
            return self.table[path]
        return C.ABSENT, {"message": "Not Found", "status": "404"}


# ── carriers ─────────────────────────────────────────────────────────────────────────────────


def test_every_carrier_kind_parses_and_a_carrier_without_a_schedule_is_no_declaration():
    assert C.parse_workflow(WORKFLOW_CRON) == ["36 13 * * *"]  # PyYAML reads `on:` as the key True
    assert C.parse_workflow(WORKFLOW_NO_CRON) == []
    assert C.parse_workflow("on:\n  schedule:\n    - cron: '0 1 * * *'\n  - broken yaml: [\n") == [
        "0 1 * * *"
    ]  # regex fallback
    assert C.parse_wrangler("wrangler.toml", '[triggers]\ncrons = ["0 * * * *", "30 2 * * 1"]\n') == [
        "0 * * * *",
        "30 2 * * 1",
    ]
    assert C.parse_wrangler("wrangler.jsonc", '{ // comment\n "triggers": {"crons": ["15 4 * * *"]} }') == [
        "15 4 * * *"
    ]
    assert C.parse_wrangler("wrangler.toml", 'name = "w"\n') == []
    assert C.parse_vercel('{"crons":[{"path":"/x","schedule":"0 5 * * *"}]}')[0]["schedule"] == "0 5 * * *"
    assert C.parse_crontab("# comment\n0 5 * * * /bin/true\n@daily /bin/x\nnot a line\n") == [
        "0 5 * * * /bin/true",
        "@daily /bin/x",
    ]
    assert C.parse_timer("[Timer]\nOnCalendar=daily\nPersistent=true\n") == ["daily"]
    assert C.parse_dependabot("version: 2\nupdates:\n  - schedule: {interval: daily, time: '04:00'}\n") == [
        "daily 04:00"
    ]
    assert C.parse_renovate('{"schedule": ["after 10pm"]}') == ["after 10pm"]
    assert C.parse_cloud_routines('{"routines": [{"cron": "0 9 * * *"}, {"name": "x"}]}') == 1
    assert C.parse_manifest("{ name: 'a', maxInvocationsPerDay: 6,\n schedule: '0 1,5 * * *' }")[0] == {
        "name": "a",
        "cron": "0 1,5 * * *",
        "max_per_day": 6,
    }
    assert C.declaration_for("gh-workflow", ".github/workflows/x.yml", WORKFLOW_NO_CRON) is None
    assert C.declaration_for("launchd", "a.plist", "not a plist") is None
    d = C.declaration_for("gh-workflow", ".github/workflows/x.yml", WORKFLOW_CRON)
    assert d and d["cadence"] == ["daily"]


# ── gh access classification ─────────────────────────────────────────────────────────────────


def test_gh_api_tells_absent_from_unreachable_from_error(monkeypatch):
    class Run:
        def __init__(self, code, out):
            self.returncode, self.stdout = code, out

    monkeypatch.setattr(C, "gh_available", lambda: True)
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: Run(0, '{"ok": true}'))
    assert C.gh_api("repos/x/y") == (C.OK, {"ok": True})
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: Run(1, '{"message":"Not Found","status":"404"}'))
    assert C.gh_api("repos/x/y")[0] == C.ABSENT
    monkeypatch.setattr(
        C.subprocess,
        "run",
        lambda *a, **k: Run(
            1, '{"message":"GitHub access to this repository is not enabled for this session. Use add_repo"}'
        ),
    )
    assert C.gh_api("repos/x/y")[0] == C.UNREACHABLE
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: Run(1, '{"message":"Bad credentials","status":"401"}'))
    assert C.gh_api("repos/x/y")[0] == C.UNREACHABLE
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: Run(1, '{"message":"boom","status":"500"}'))
    assert C.gh_api("repos/x/y")[0] == C.ERROR
    monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: Run(1, ""))
    assert C.gh_api("repos/x/y")[0] == C.ERROR
    monkeypatch.setattr(C, "gh_available", lambda: False)
    assert C.gh_api("repos/x/y") == (C.UNREACHABLE, None)


# ── one repository end to end ────────────────────────────────────────────────────────────────


def test_scan_repo_reads_carriers_states_runs_and_history(monkeypatch, tmp_path):
    fake = FakeGH(_table())
    monkeypatch.setattr(C, "gh_api", fake)
    row = C.scan_repo("4444J99/example", clone=tmp_path, history_cap=10)  # tmp_path is not a git clone → API history
    assert row["reach"] == C.OK and row["private"] is True and row["default_branch"] == "main"
    kinds = {(d["kind"], d["path"]) for d in row["declarations"]}
    assert (".github/workflows/hygiene.yml" in {p for _, p in kinds}) and (
        "gh-workflow",
        ".github/workflows/build.yml",
    ) not in kinds
    by_path = {d["path"]: d for d in row["declarations"]}
    assert by_path[".github/workflows/hygiene.yml"]["state"] == "active" and by_path[".github/workflows/hygiene.yml"][
        "crons"
    ] == ["36 13 * * *"]
    assert by_path[".github/workflows/old-scale.yml"]["state"] == "disabled_inactivity"
    assert by_path[".github/workflows/tmp-diag.yml"]["note"].startswith("registered with Actions but absent")
    assert by_path["wrangler.toml"]["crons"] == ["*/30 * * * *"]
    assert by_path["vercel.json"]["crons"] == ["0 5 * * *"] and by_path["vercel.json"]["paths"] == ["/api/tick"]
    assert by_path["launchd/com.example.beat.plist"]["interval_seconds"] == 1800
    assert by_path[".github/dependabot.yml"]["intervals"] == ["weekly monday"]
    assert by_path["cloudflare/src/manifest.ts"]["targets"][0]["name"] == "bountyscope"
    assert "README.md" not in by_path  # only carriers are read
    assert (
        row["fired"]["total_scheduled_runs"] == 3
        and row["fired"]["by_workflow"]["hygiene"]["last_conclusion"] == "success"
    )
    assert row["failing_workflows"] == [] and row["actions_registered_not_in_tree"] == [
        ".github/workflows/tmp-diag.yml"
    ]
    hist = row["history"]
    assert hist["source"] == "api" and hist["commits_seen"] == 2 and hist["truncated"] is False
    events = {(e["path"], e["change"]): e for e in hist["events"]}
    assert events[(".github/workflows/hygiene.yml", "modified")]["crons_added"] == ["36 13 * * *"]
    assert events[(".github/workflows/hygiene.yml", "modified")]["crons_removed"] == ["0 13 * * *"]
    assert events[(".github/workflows/nightly.yml", "removed")]["crons_removed"] == ["0 2 * * *"]
    assert ("README.md", "modified") not in events  # only workflow files count as schedule history
    assert row["verdict"] == "active"
    att = row["attempts"]
    assert att["readable"] and att["seen"] == 4 and att["truncated"] is False
    assert [(i["number"], i["kind"], i["merged"]) for i in att["items"]] == [
        (7, "issue", None),
        (9, "pr", True),
        (12, "issue", None),
    ]
    assert any("shallow" in n for n in row["notes"])  # a non-clone path is reported, not silently ignored
    assert not any(c.startswith("repos/4444J99/example/contents/README.md") for c in fake.calls)


def test_unreachable_repository_is_never_nothing_scheduled(monkeypatch):
    monkeypatch.setattr(C, "gh_api", lambda path: (C.UNREACHABLE, {"message": "not enabled for this session"}))
    row = C.scan_repo("4444J99/private-elsewhere")
    assert row["reach"] == C.UNREACHABLE and row["verdict"] == "unreachable" and row["declarations"] == []
    report = C.build_report(
        [row],
        universe=[{"repo": "4444J99/private-elsewhere"}],
        universe_source="explicit",
        unscanned=[],
        gaps=None,
        started=0.0,
    )
    assert report["denominators"]["scanned"] == 0 and report["denominators"]["unreachable"] == 1
    assert report["totals"]["repos_with_any_declaration"] == 0 and report["unreachable"] == [
        "4444J99/private-elsewhere"
    ]
    assert "never counted as unscheduled" in report["denominators"]["note"]


def test_verdict_matrix():
    def row(**over):
        base = {
            "reach": C.OK,
            "declarations": [],
            "fired": {"total_scheduled_runs": 0, "by_workflow": {}},
            "history": {"events": []},
        }
        base.update(over)
        return base

    def wf(state, crons=("0 1 * * *",)):
        return {"kind": "gh-workflow", "path": "w.yml", "state": state, "crons": list(crons)}

    assert C.verdict_for_repo(row(reach=C.UNREACHABLE)) == "unreachable"
    assert C.verdict_for_repo(row(declarations=[wf("disabled_manually")])) == "manually-disabled"
    assert C.verdict_for_repo(row(declarations=[wf("disabled_inactivity")])) == "auto-disabled"
    assert C.verdict_for_repo(row(declarations=[wf("active")])) == "declared-never-fired"
    fired_bad = {"total_scheduled_runs": 5, "by_workflow": {"w": {"last_conclusion": "failure"}}}
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=fired_bad)) == "firing-but-failing"
    fired_ok = {
        "total_scheduled_runs": 5,
        "by_workflow": {"w": {"last_conclusion": "success"}, "v": {"last_conclusion": "failure"}},
    }
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=fired_ok)) == "active"
    assert C.verdict_for_repo(row(history={"events": [{"change": "removed"}]})) == "abandoned-in-history"
    assert (
        C.verdict_for_repo(row(declarations=[{"kind": "wrangler", "path": "wrangler.toml", "crons": ["0 * * * *"]}]))
        == "declared-outside-actions"
    )
    assert C.verdict_for_repo(row()) == "none"
    # a disabled workflow beside an active one does not hide the active one
    assert C.verdict_for_repo(row(declarations=[wf("disabled_manually"), wf("active")], fired=fired_ok)) == "active"


# ── history from a real full clone ───────────────────────────────────────────────────────────


def test_history_from_a_full_git_clone_records_cron_changes_and_removals(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True)

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (wf / "nightly.yml").write_text("on:\n  schedule:\n    - cron: '0 2 * * *'\njobs: {}\n")
    git("add", "-A")
    git("commit", "-q", "-m", "add nightly")
    (wf / "nightly.yml").write_text("on:\n  schedule:\n    - cron: '15 2 * * *'\njobs: {}\n")
    git("commit", "-q", "-am", "move nightly")
    (wf / "nightly.yml").unlink()
    git("commit", "-q", "-am", "drop nightly")
    assert C.clone_is_full(repo) and not C.clone_is_full(tmp_path / "nope") and not C.clone_is_full(None)
    hist = C.history_from_git(repo)
    assert hist["source"] == "git" and hist["commits_seen"] == 3 and hist["truncated"] is False
    changes = [(e["change"], e["crons_added"], e["crons_removed"]) for e in hist["events"]]  # newest first
    assert changes == [
        ("removed", [], ["15 2 * * *"]),
        ("modified", ["15 2 * * *"], ["0 2 * * *"]),
        ("added", ["0 2 * * *"], []),
    ]
    row = {"reach": C.OK, "declarations": [], "fired": {"total_scheduled_runs": 0, "by_workflow": {}}, "history": hist}
    assert C.verdict_for_repo(row) == "abandoned-in-history"


# ── registry parity, denominators, budget, receipt, main ─────────────────────────────────────


def test_registry_gaps_name_active_schedules_outside_every_plane():
    covered = C.registry_covered_repos(ROOT, "4444J99/limen")
    assert {"4444J99/limen", "4444J99/ops", "4444J99/ops-witness"} <= covered
    rows = [
        {
            "repo": "4444J99/ops",
            "reach": C.OK,
            "declarations": [{"kind": "gh-workflow", "path": "a.yml", "state": "active", "crons": ["0 1 * * *"]}],
        },
        {
            "repo": "4444J99/forgotten",
            "reach": C.OK,
            "declarations": [{"kind": "gh-workflow", "path": "b.yml", "state": "active", "crons": ["5 4 * * *"]}],
        },
        {
            "repo": "4444J99/quiet",
            "reach": C.OK,
            "declarations": [
                {"kind": "gh-workflow", "path": "c.yml", "state": "disabled_inactivity", "crons": ["5 4 * * *"]}
            ],
        },
        {"repo": "4444J99/dark", "reach": C.UNREACHABLE, "declarations": []},
    ]
    gaps = C.registry_gaps(rows, covered)
    assert [g["repo"] for g in gaps] == ["4444J99/forgotten"] and gaps[0]["crons"] == ["5 4 * * *"]


def test_budget_cut_lists_the_unscanned_and_receipt_states_denominators(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "gh_api", FakeGH(_table("4444J99/one")))
    universe = [{"repo": "4444J99/one"}, {"repo": "4444J99/two"}, {"repo": "4444J99/three", "archived": True}]
    monotonic = iter([0.0, 0.0, 10.0, 10.0, 10.0, 10.0])
    monkeypatch.setattr(C.time, "monotonic", lambda: next(monotonic, 10.0))
    report = C.run_census(universe, "explicit", budget_seconds=5, root=ROOT, skip_archived=True)
    d = report["denominators"]
    assert (
        d["universe_count"] == 3
        and d["scanned"] == 1
        and d["unscanned_by_budget"] == 1
        and report["unscanned_by_budget"] == ["4444J99/two"]
    )
    assert report["schema"] == C.SCHEMA and set(report["channels_read"]) >= {"gh-workflow", "launchd", "wrangler"}
    assert "jules-native-scheduled-tasks" in report["channels_not_read"]
    receipt = tmp_path / "logs" / "schedule-census.json"
    C.write_receipt(receipt, report)
    assert json.loads(receipt.read_text())["denominators"]["scanned"] == 1
    assert not list(receipt.parent.glob("*.tmp"))
    md = C.render_markdown(report)
    assert (
        md.startswith("# Schedule census")
        and "universe 3 (explicit) · scanned 1 · unreachable 0 · unscanned by budget 1" in md
    )
    assert "Left unscanned by the time budget" in md and "4444J99/two" in md
    assert C.receipt_is_fresh(receipt, 168) and not C.receipt_is_fresh(receipt, 0)
    assert not C.receipt_is_fresh(tmp_path / "missing.json", 168)


def test_universe_resolution_prefers_explicit_then_file_then_estate_cache(tmp_path):
    assert C.resolve_universe(["a/b"], None, tmp_path / "none.json") == ([{"repo": "a/b"}], "explicit")
    f = tmp_path / "repos.txt"
    f.write_text("# comment\na/b\n\nc/d\n")
    rows, src = C.resolve_universe([], f, tmp_path / "none.json")
    assert [r["repo"] for r in rows] == ["a/b", "c/d"] and src.startswith("repos-file:")
    cache = tmp_path / "estate-repos.json"
    cache.write_text(
        json.dumps(
            {
                "schema": C.ESTATE_CACHE_SCHEMA,
                "owners": ["4444J99"],
                "repos": {
                    "4444J99/z": {"archived": True, "fork": False},
                    "4444J99/a": {"archived": False, "fork": False},
                },
            }
        )
    )
    rows, src = C.resolve_universe([], None, cache)
    assert (
        [r["repo"] for r in rows] == ["4444J99/a", "4444J99/z"]
        and rows[1]["archived"] is True
        and src.startswith("estate-cache:")
    )
    cache.write_text(json.dumps({"schema": "other"}))
    assert C.universe_from_estate_cache(cache) is None


def test_main_writes_receipt_and_ledger_and_exits_on_findings(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "gh_api", FakeGH(_table("4444J99/one", last_conclusion="failure")))
    receipt = tmp_path / "census.json"
    rc = C.main(
        ["--repos", "4444J99/one", "--receipt", str(receipt), "--force", "--check-registry", "--interval-hours", "1"]
    )
    assert rc == 1  # firing-but-failing is a finding; 4444J99/one is also outside every registry plane
    report = json.loads(receipt.read_text())
    assert report["registry_gaps"][0]["repo"] == "4444J99/one" and report["totals"]["verdicts"] == {
        "firing-but-failing": 1
    }
    assert (
        report["totals"]["workflows_failing_last_scheduled_run"] == 1
        and report["totals"]["actions_registered_not_in_tree"] == 1
    )
    assert (tmp_path / "census.md").exists() and "failing: hygiene" in (tmp_path / "census.md").read_text()
    # fresh receipt → nothing to do without --force
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt), "--interval-hours", "168"]) == 0
    monkeypatch.setattr(C, "gh_api", lambda path: (C.UNREACHABLE, None))
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt), "--force"]) == 3  # read nothing ≠ found nothing


def test_rate_guard_waits_for_the_reset_inside_the_budget_and_stops_outside_it(monkeypatch):
    clock = {"now": 1000.0}
    slept: list[float] = []
    monkeypatch.setattr(C, "gh_api", lambda path: (C.OK, {"resources": {"core": {"remaining": 3, "reset": 1030}}}))
    assert C.rate_guard(deadline=2000.0, sleep=slept.append, now=lambda: clock["now"]) == "slept:35"
    assert slept == [35.0]
    assert C.rate_guard(deadline=1010.0, sleep=slept.append, now=lambda: clock["now"]) == "exhausted"
    monkeypatch.setattr(C, "gh_api", lambda path: (C.OK, {"resources": {"core": {"remaining": 4000, "reset": 1030}}}))
    assert C.rate_guard(deadline=1010.0, sleep=slept.append, now=lambda: clock["now"]) == "ok"
    monkeypatch.setattr(C, "gh_api", lambda path: (C.UNREACHABLE, None))
    assert (
        C.rate_guard(deadline=1010.0, sleep=slept.append, now=lambda: clock["now"]) == "ok"
    )  # unreadable quota never blocks


def test_run_census_stops_on_exhausted_quota_and_lists_the_rest(monkeypatch):
    table = _table("4444J99/one")
    calls = {"n": 0}

    def fake(path):
        if path == "rate_limit":
            calls["n"] += 1
            return C.OK, {"resources": {"core": {"remaining": 1, "reset": 10**12}}}
        return table.get(path, (C.ABSENT, {"message": "Not Found", "status": "404"}))

    monkeypatch.setattr(C, "gh_api", fake)
    report = C.run_census(
        [{"repo": "4444J99/one"}, {"repo": "4444J99/two"}], "explicit", budget_seconds=5, root=ROOT, rate_check_every=1
    )
    assert report["denominators"]["scanned"] == 0 and report["unscanned_by_budget"] == ["4444J99/one", "4444J99/two"]
    assert calls["n"] == 1  # once exhausted, nothing else is asked of GitHub


def test_attempt_discourse_is_keyword_matched_and_an_unreadable_listing_is_not_zero():
    calls = []

    def call(path):
        calls.append(path)
        page = int(path.split("&page=")[1].split("&")[0])
        rows = (
            [{"number": n, "title": f"cron job {n}", "state": "open", "labels": []} for n in range(100)]
            if page < 3
            else []
        )
        return C.OK, rows

    att = C.read_attempts("4444J99/x", call, pages=2)
    assert len(att["items"]) == 200 and att["seen"] == 200 and att["truncated"] is True and len(calls) == 2
    att = C.read_attempts("4444J99/x", lambda path: (C.UNREACHABLE, None))
    assert att["readable"] is False and att["items"] == [] and att["truncated"] is True
    assert (
        C.ATTEMPT_RX.search("Scheduled tasks for the digest")
        and C.ATTEMPT_RX.search("keepalive")
        and not C.ATTEMPT_RX.search("Rotate keys")
    )
