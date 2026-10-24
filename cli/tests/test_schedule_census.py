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

import pytest
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
        f"repos/{repo}/actions/workflows?per_page=100&page=1": (
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


def _clean_table(repo: str = "4444J99/example", **kw) -> dict:
    """_table without the auto-disabled old-scale workflow: one healthy active schedule, nothing to find."""
    table = _table(repo, **kw)
    tree_key = f"repos/{repo}/git/trees/main?recursive=1"
    tree = table[tree_key][1]
    table[tree_key] = (C.OK, {**tree, "tree": [e for e in tree["tree"] if e.get("path") != OLD_SCALE]})
    wf_key = f"repos/{repo}/actions/workflows?per_page=100&page=1"
    wf = table[wf_key][1]
    table[wf_key] = (C.OK, {**wf, "workflows": [w for w in wf["workflows"] if w["path"] != OLD_SCALE]})
    del table[f"repos/{repo}/contents/{OLD_SCALE}?ref=main"]
    return table


OLD_SCALE = ".github/workflows/old-scale.yml"


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
    # a schedule may live on a package rule, not the root — the checked-in renovate.json does exactly that
    assert C.parse_renovate('{"packageRules": [{"schedule": ["before 6am on monday"]}, {"groupName": "x"}]}') == [
        "before 6am on monday"
    ]
    assert C.parse_renovate('{"schedule": ["a"], "packageRules": [{"schedule": ["a", "b"]}]}') == ["a", "b"]
    assert C.parse_cloud_routines('{"routines": [{"cron": "0 9 * * *"}, {"name": "x"}]}') == 1
    assert C.parse_manifest("{ name: 'a', maxInvocationsPerDay: 6,\n schedule: '0 1,5 * * *' }")[0] == {
        "name": "a",
        "cron": "0 1,5 * * *",
        "max_per_day": 6,
    }
    assert C.declaration_for("gh-workflow", ".github/workflows/x.yml", WORKFLOW_NO_CRON) is None
    # tri-state: a carrier that cannot be parsed is neither a declaration nor "no schedule"
    assert C.declaration_for("launchd", "a.plist", "not a plist") == {
        "kind": "launchd",
        "path": "a.plist",
        "unparseable": True,
    }
    assert C.parse_wrangler("wrangler.toml", "[triggers\ncrons = [") is None
    assert C.declaration_for("wrangler", "wrangler.toml", "[triggers\ncrons = [")["unparseable"] is True
    assert C.declaration_for("vercel", "vercel.json", "{not json") == {
        "kind": "vercel",
        "path": "vercel.json",
        "unparseable": True,
    }
    assert C.parse_wrangler("wrangler.jsonc", '{"triggers": {"crons": ["1 2 * * *",],},}') == [
        "1 2 * * *"
    ]  # trailing commas
    assert C.parse_wrangler("wrangler.json", '{"triggers": {"crons": "0 * * * *"}}') == ["0 * * * *"]  # scalar cron
    assert C.parse_wrangler("wrangler.json", '{"triggers": ["not", "a", "dict"]}') == []
    # malformed carriers never raise: the shape GitHub hands back is data, not a contract
    assert C.parse_launchd('<plist version="1.0"><array><string>x</string></array></plist>') == {}
    assert C.parse_vercel('{"crons": {"path": "/x"}}') == [] and C.parse_vercel("[1,2]") == []
    assert C.parse_dependabot("updates: notalist\n") == [] and C.parse_renovate('{"schedule": {"x": 1}}') == []
    assert C.parse_cloud_routines('"just a string"') == 0 and C.parse_cloud_routines("{bad") is None
    assert C.parse_workflow("on:\n  schedule:\n    cron: '5 5 * * *'\n") == ["5 5 * * *"]  # schedule as a mapping
    assert C.parse_workflow("on: [push]\n") == [] and C.parse_workflow("on:\n  - [broken\n") is None
    # real-world carriers the strict parsers reject: a wrangler.toml declaring [vars] twice (wrangler tolerates it)
    # has no [triggers] table → no schedule; the same file with a [triggers] table is read by regex
    twice = 'name = "api"\n[vars]\nA = "1"\n[env.staging]\nname = "s"\n[vars]\nA = "2"\n'
    assert C.parse_wrangler("apps/api/wrangler.toml", twice) == []
    assert C.parse_wrangler("wrangler.toml", twice + "crons = [\n") is None  # a cron outside any table: unreadable
    assert C.parse_wrangler("wrangler.toml", twice + '[triggers]\ncrons = ["*/15 * * * *", "0 3 * * 1"]\n') == [
        "*/15 * * * *",
        "0 3 * * 1",
    ]
    assert C.parse_wrangler("wrangler.toml", twice + "[triggers]\ncrons = garbage\n") is None  # table, unreadable
    # a launchd plist whose XML comment holds `--` (expat rejects it) still yields its StartInterval by regex
    commented = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!-- install: organvm heartbeat --install -->\n'
        '<plist version="1.0"><dict><key>Label</key><string>x</string><key>StartInterval</key><integer>900</integer></dict></plist>\n'
    )
    assert C.parse_launchd(commented) == {"interval_seconds": 900, "parse": "regex"}
    assert (
        C.parse_launchd('<!-- a -- b --><plist version="1.0"><dict><key>Label</key><string>x</string></dict></plist>')
        == {}
    )
    assert C.parse_launchd("<!-- a -- b --><plist><dict><key>StartCalendarInterval</key><dict/></dict></plist>") is None
    # cadence comes from fire frequency, never from the routine-parity classes (`*/30` is not "daily")
    assert [
        C.cron_rate(c) for c in ("*/30 * * * *", "0 * * * *", "0 */4 * * *", "0 9 * * *", "0 9 * * 1", "0 9 * * 1-5")
    ] == [
        (48.0, "sub-hourly"),
        (24.0, "hourly"),
        (6.0, "intraday"),
        (1.0, "daily"),
        (0.143, "weekly"),
        (0.714, "weekdays"),
    ]
    assert C.cron_rate("0 0 1 * *") == (0.033, "monthly") and C.cron_rate("not a cron") == (None, "unparsed")
    half_hourly = C.declaration_for("wrangler", "wrangler.toml", '[triggers]\ncrons = ["*/30 * * * *", "0 9 * * 1"]\n')
    assert half_hourly["cadence"] == ["sub-hourly", "weekly"] and half_hourly["fires_per_day"] == 48.143
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
    assert row["fired"]["listing_capped"] is False and row["fired"]["oldest_page_read"] is False
    by_path = {d["path"]: d for d in row["declarations"]}
    assert by_path["wrangler.toml"]["cadence"] == ["sub-hourly"] and by_path["wrangler.toml"]["fires_per_day"] == 48.0
    # a listing at the cap is a floor; without the deepest page, oldest_seen is page one's edge
    capped = C.summarize_scheduled_runs(
        {"total_count": C.RUN_LISTING_CAP, "workflow_runs": [{"name": "w", "created_at": "2026-10-20T00:00:00Z"}]}
    )
    assert (
        capped["listing_capped"] is True
        and capped["oldest_page_read"] is False
        and capped["oldest_seen"] == "2026-10-20T00:00:00Z"
    )
    deep = C.summarize_scheduled_runs(
        {"total_count": 150, "workflow_runs": [{"name": "w", "created_at": "2026-10-20T00:00:00Z"}]},
        {"workflow_runs": [{"name": "w", "created_at": "2026-01-01T00:00:00Z"}]},
    )
    assert (
        deep["listing_capped"] is False
        and deep["oldest_page_read"] is True
        and deep["oldest_seen"] == "2026-01-01T00:00:00Z"
    )
    assert deep["page_oldest_seen"] == "2026-10-20T00:00:00Z" != deep["oldest_seen"]  # the page's own edge
    # the newest run can be queued or running (conclusion null): the page's newest SUCCESS is recorded beside it,
    # so the utilization reader never mistakes a run in flight for a workflow gone dark
    w_path = ".github/workflows/w.yml"
    pending = C.summarize_scheduled_runs(
        {
            "total_count": 3,
            "workflow_runs": [
                {"path": w_path, "name": "w", "created_at": "2026-10-23T09:00:00Z", "conclusion": None},
                {"path": w_path, "name": "w", "created_at": "2026-10-22T09:00:00Z", "conclusion": "failure"},
                {"path": w_path, "name": "w", "created_at": "2026-10-21T09:00:00Z", "conclusion": "success"},
            ],
        }
    )["by_workflow"][w_path]
    assert (pending["last_at"], pending["last_conclusion"]) == ("2026-10-23T09:00:00Z", None)
    assert pending["last_success_at"] == "2026-10-21T09:00:00Z"
    assert (pending["runs_on_page"], pending["failed_on_page"]) == (3, 1)
    assert capped["by_workflow"]["w"]["last_success_at"] is None  # no success on the page: nothing invented
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
    assert row["verdict"] == "active" and row["partial"] is False
    assert row["channels"] == {
        "metadata": C.OK,
        "tree": C.OK,
        "actions-workflows": C.OK,
        "contents": C.OK,
        "scheduled-runs": C.OK,
        "issues-prs": C.OK,
        "history": "api",
    }
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
            "partial": False,
        }
        base.update(over)
        return base

    def wf(state, crons=("0 1 * * *",)):
        return {"kind": "gh-workflow", "path": "w.yml", "state": state, "crons": list(crons), "name": "w"}

    assert C.verdict_for_repo(row(reach=C.UNREACHABLE)) == "unreachable"
    assert C.verdict_for_repo(row(declarations=[wf("disabled_manually")])) == "manually-disabled"
    assert C.verdict_for_repo(row(declarations=[wf("disabled_inactivity")])) == "auto-disabled"
    # GitHub auto-disables only scheduled workflows, so that state stands even when the cron lines are gone
    assert C.verdict_for_repo(row(declarations=[wf("disabled_inactivity", crons=())])) == "auto-disabled"
    # a manual disable can hit any workflow: without crons it is not a schedule verdict
    assert C.verdict_for_repo(row(declarations=[wf("disabled_manually", crons=())])) == "none"
    assert C.verdict_for_repo(row(declarations=[wf("disabled_fork")])) == "disabled-fork"
    assert C.verdict_for_repo(row(declarations=[wf("unknown")])) == "declared-state-unknown"
    assert C.verdict_for_repo(row(declarations=[wf("active")])) == "declared-never-fired"
    # an unread run listing is unmeasured, never "never fired"
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=None)) == "fired-unmeasured"
    assert "fired-unmeasured" not in C.FINDING_VERDICTS and "declared-never-fired" in C.FINDING_VERDICTS
    fired_bad = {"total_scheduled_runs": 5, "by_workflow": {"w": {"last_conclusion": "failure"}}}
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=fired_bad)) == "firing-but-failing"
    fired_ok = {
        "total_scheduled_runs": 5,
        "by_workflow": {"w": {"last_conclusion": "success"}, "v": {"last_conclusion": "failure"}},
    }
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=fired_ok)) == "active"
    # firing-but-failing needs EVERY live schedule failing, not any: one of two live workflows failing is active
    v = {**wf("active"), "path": "v.yml", "name": "v"}
    assert C.verdict_for_repo(row(declarations=[wf("active"), v], fired=fired_ok)) == "active"
    # the run summary is keyed by workflow path (#3196): the join reaches the path half, not only the name
    by_path = {"total_scheduled_runs": 5, "page_runs": 5, "by_workflow": {"w.yml": {"last_conclusion": "failure"}}}
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=by_path)) == "firing-but-failing"
    # failures that belong only to a retired workflow are history, and the live schedule then has no run at all: when
    # the page is the whole retained listing it never fired; when its latest run may sit on an unread page, unmeasured
    retired_bad = {"total_scheduled_runs": 5, "page_runs": 5, "by_workflow": {"old": {"last_conclusion": "failure"}}}
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=retired_bad)) == "declared-never-fired"
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired={**retired_bad, "page_runs": 3})) == (
        "fired-unmeasured"
    )
    both_bad = {
        "total_scheduled_runs": 5,
        "by_workflow": {"old": {"last_conclusion": "failure"}, "w": {"last_conclusion": "failure"}},
    }
    assert C.verdict_for_repo(row(declarations=[wf("active")], fired=both_bad)) == "firing-but-failing"
    # abandoned needs a cron actually removed — a deleted lint workflow is not a schedule attempt
    assert C.verdict_for_repo(row(history={"events": [{"change": "removed", "crons_removed": ["0 2 * * *"]}]})) == (
        "abandoned-in-history"
    )
    assert C.verdict_for_repo(row(history={"events": [{"change": "removed", "crons_removed": []}]})) == "none"
    wrangler = {"kind": "wrangler", "path": "wrangler.toml", "crons": ["0 * * * *"]}
    assert C.verdict_for_repo(row(declarations=[wrangler])) == "declared-outside-actions"
    # dependency-update schedules are hygiene, not an operator scheduler: their own verdict, not a finding
    dependabot = {"kind": "dependabot", "path": ".github/dependabot.yml", "intervals": ["weekly"]}
    renovate = {"kind": "renovate", "path": "renovate.json", "schedule": ["after 10pm"]}
    assert C.verdict_for_repo(row(declarations=[dependabot])) == "hygiene-only"
    assert C.verdict_for_repo(row(declarations=[dependabot, renovate])) == "hygiene-only"
    assert C.verdict_for_repo(row(declarations=[dependabot, wrangler])) == "declared-outside-actions"
    assert "hygiene-only" not in C.FINDING_VERDICTS
    # a live schedule outside Actions outranks a cron removed long ago
    assert (
        C.verdict_for_repo(
            row(declarations=[wrangler], history={"events": [{"change": "removed", "crons_removed": ["0 2 * * *"]}]})
        )
        == "declared-outside-actions"
    )
    assert C.verdict_for_repo(row(partial=True)) == "partial"
    assert C.verdict_for_repo(row()) == "none"
    # a disabled workflow beside an active one does not hide the active one
    assert C.verdict_for_repo(row(declarations=[wf("disabled_manually"), wf("active")], fired=fired_ok)) == "active"


# ── history from a real full clone ───────────────────────────────────────────────────────────


def test_history_from_a_full_git_clone_records_cron_changes_and_removals(tmp_path, monkeypatch):
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
    (wf / "lint.yml").write_text("# lint\non: push\njobs: {}\n")
    (wf / "café.yml").write_text("on:\n  schedule:\n    - cron: '5 4 * * *'\njobs: {}\n")  # non-ASCII name
    git("add", "-A")
    git("commit", "-q", "-m", "add nightly")
    (wf / "nightly.yml").write_text("on:\n  schedule:\n    - cron: '15 2 * * *'\njobs: {}\n")
    (wf / "lint.yml").write_text("# lint (a comment edit in the same commit as the cron move)\non: push\njobs: {}\n")
    git("commit", "-q", "-am", "move nightly")
    (wf / "nightly.yml").unlink()
    git("commit", "-q", "-am", "drop nightly")
    assert C.clone_is_full(repo) and not C.clone_is_full(tmp_path / "nope") and not C.clone_is_full(None)
    hist = C.history_from_git(repo)
    assert hist["source"] == "git" and hist["commits_seen"] == 3 and hist["truncated"] is False
    changes = [
        (e["path"].rsplit("/", 1)[-1], e["change"], e["crons_added"], e["crons_removed"]) for e in hist["events"]
    ]  # newest first; files alphabetical within a commit
    assert [c for c in changes if c[0] == "nightly.yml"] == [
        ("nightly.yml", "removed", [], ["15 2 * * *"]),
        ("nightly.yml", "modified", ["15 2 * * *"], ["0 2 * * *"]),
        ("nightly.yml", "added", ["0 2 * * *"], []),
    ]
    # the sibling edited in the same commits never had a cron: per-path keying hands it none
    assert [c for c in changes if c[0] == "lint.yml"] == [
        ("lint.yml", "modified", [], []),
        ("lint.yml", "added", [], []),
    ]
    # a non-ASCII name keys its crons like any other: git prints it raw in both listings (core.quotePath=false)
    assert [c for c in changes if c[0] == "café.yml"] == [("café.yml", "added", ["5 4 * * *"], [])]
    # a host gitconfig that reshapes diff headers (noprefix, colour) cannot silently un-attribute the crons
    gc = tmp_path / "gitconfig"
    gc.write_text("[diff]\n\tnoprefix = true\n[color]\n\tui = always\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gc))
    pinned = C.history_from_git(repo)
    assert pinned["status"] == C.OK and [
        (e["change"], e["crons_added"], e["crons_removed"])
        for e in pinned["events"]
        if e["path"].endswith("nightly.yml")
    ] == [("removed", [], ["15 2 * * *"]), ("modified", ["15 2 * * *"], ["0 2 * * *"]), ("added", ["0 2 * * *"], [])]
    monkeypatch.setattr(C, "_diff_header_path", lambda line: None)
    loud = C.history_from_git(repo)
    assert loud["status"] == "partial" and loud["truncated"] is True and "diff header(s) unparsed" in loud["note"]
    monkeypatch.undo()  # the parser stub above must not reach the unit checks below
    assert C._diff_header_path('diff --git "a/w s.yml" "b/w s.yml"') == "w s.yml"
    assert (
        C._diff_header_path("diff --git a/old.yml b/new.yml") == "new.yml" and C._diff_header_path("index 1..2") is None
    )
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
    assert gaps[0]["unverified"] == []
    rows.append(
        {
            "repo": "4444J99/unlisted",
            "reach": C.OK,
            "declarations": [{"kind": "gh-workflow", "path": "d.yml", "state": "unknown", "crons": ["1 1 * * *"]}],
        }
    )
    gaps = C.registry_gaps(rows, covered)
    assert gaps[1]["repo"] == "4444J99/unlisted" and gaps[1]["unverified"] == ["d.yml"]  # declared, state unread


def test_budget_cut_lists_the_unscanned_and_receipt_states_denominators(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "gh_api", FakeGH(_table("4444J99/one")))
    universe = [{"repo": "4444J99/one"}, {"repo": "4444J99/two"}, {"repo": "4444J99/three", "archived": True}]
    clock = {"t": 0.0}
    monkeypatch.setattr(C.time, "monotonic", lambda: clock["t"])
    real_scan = C.scan_repo

    def scan_then_spend_the_budget(repo, **kw):
        row = real_scan(repo, **kw)
        clock["t"] = 10.0
        return row

    monkeypatch.setattr(C, "scan_repo", scan_then_spend_the_budget)
    report = C.run_census(universe, "explicit", budget_seconds=5, root=ROOT, skip_archived=True)
    d = report["denominators"]
    assert (
        d["universe_count"] == 3
        and d["scanned"] == 1
        and d["scanned_partial"] == 0
        and d["unscanned_by_budget"] == 1
        and d["skipped_archived"] == 1
        and d["internal_errors"] == 0
        and report["unscanned_by_budget"] == ["4444J99/two"]
        and report["skipped_archived"] == ["4444J99/three"]
    )
    assert report["schema"] == C.SCHEMA and set(report["channels_read"]) >= {"gh-workflow", "launchd", "wrangler"}
    assert "jules-native-scheduled-tasks" in report["channels_not_read"]
    receipt = tmp_path / "logs" / "schedule-census.json"
    C.write_receipt(receipt, report)
    assert json.loads(receipt.read_text())["denominators"]["scanned"] == 1
    assert not list(receipt.parent.glob("*.tmp"))
    md = C.render_markdown(report)
    assert md.startswith("# Schedule census") and "universe 3 (explicit) · scanned 1 (partial 0) · unreachable 0" in md
    assert "unscanned by budget 1 · skipped archived 1" in md
    assert "Left unscanned by the time budget" in md and "4444J99/two" in md
    assert "Skipped (archived" in md and "4444J99/three" in md
    assert "Historical attempts" in md and "nightly.yml -[0 2 * * *]" in md
    # a receipt that left a third of its universe unread is incomplete: it earns the retry horizon, not the interval
    assert not C.receipt_is_complete(report)
    assert C.receipt_is_fresh(receipt, 168) and not C.receipt_is_fresh(receipt, 0)
    later = C.datetime.now(C.timezone.utc) + C.timedelta(hours=30)
    assert not C.receipt_is_fresh(receipt, 168, now=later, retry_hours=24)
    assert C.receipt_is_fresh(receipt, 168, now=later, retry_hours=48)
    complete = {**report, "denominators": {**d, "unscanned_by_budget": 0, "skipped_archived": 0}}
    assert C.receipt_is_complete(complete)
    # every row partially read is as incomplete as every row unread: the retry horizon, not the interval
    all_partial = {**complete, "denominators": {**complete["denominators"], "universe_count": 1, "scanned_partial": 1}}
    assert not C.receipt_is_complete(all_partial)
    unlisted = {**complete, "denominators": {**complete["denominators"], "universe_unlisted_owners": 1}}
    assert not C.receipt_is_complete(unlisted)
    C.write_receipt(receipt, complete)
    assert C.receipt_is_fresh(receipt, 168, now=later, retry_hours=24)
    assert not C.receipt_is_fresh(tmp_path / "missing.json", 168)


def test_universe_resolution_prefers_explicit_then_file_then_estate_cache(tmp_path, monkeypatch):
    assert C.resolve_universe(["a/b"], None, tmp_path / "none.json") == ([{"repo": "a/b"}], "explicit", [])
    f = tmp_path / "repos.txt"
    f.write_text("# comment\na/b\n\nc/d\n")
    f.write_text("# comment\na/b\n\nc/d\na/b\n")  # listed twice: one repository
    rows, src, unlisted = C.resolve_universe([], f, tmp_path / "none.json")
    assert [r["repo"] for r in rows] == ["a/b", "c/d"] and src.startswith("repos-file:") and unlisted == []
    assert "workflow files only" in C.CHANNELS["gh-workflow-history"]
    cache = tmp_path / "estate-repos.json"
    cache.write_text(
        json.dumps(
            {
                "schema": C.ESTATE_CACHE_SCHEMA,
                "fetched_at": C.datetime.now(C.timezone.utc).isoformat(timespec="seconds"),
                "owners": ["4444J99"],
                "repos": {
                    "4444J99/z": {"archived": True, "fork": False},
                    "4444J99/a": {"archived": False, "fork": False},
                },
            }
        )
    )

    def never_live(owners=None):
        raise AssertionError("a fresh cache must not list live")

    monkeypatch.setattr(C, "universe_from_gh_repo_list", never_live)
    rows, src, unlisted = C.resolve_universe([], None, cache)
    assert (
        [r["repo"] for r in rows] == ["4444J99/a", "4444J99/z"]
        and rows[1]["archived"] is True
        and src.startswith("estate-cache:")
        and unlisted == []
    )
    monkeypatch.undo()
    # a name listed twice is one repository, scanned and counted once
    assert C.resolve_universe(["a/b", "a/b", "c/d"], None, tmp_path / "none.json")[0] == [
        {"repo": "a/b"},
        {"repo": "c/d"},
    ]
    # a roster older than the estate TTL yields to a live listing, and is used — caveated — only when that fails
    monkeypatch.setattr(C, "gh_available", lambda: False)
    old = json.loads(cache.read_text())
    old["fetched_at"] = "2026-01-01T00:00:00+00:00"
    cache.write_text(json.dumps(old))
    rows, src, caveats = C.resolve_universe([], None, cache)
    assert [r["repo"] for r in rows] == ["4444J99/a", "4444J99/z"] and src.startswith("estate-cache:")
    assert caveats == ["stale-cache:2026-01-01T00:00:00+00:00"]
    del old["fetched_at"]
    cache.write_text(json.dumps(old))
    assert C.resolve_universe([], None, cache)[2] == ["stale-cache:unknown-age"]
    live = ([{"repo": "live/x"}], "gh-repo-list:live", [])
    monkeypatch.setattr(C, "universe_from_gh_repo_list", lambda owners=None: live)
    assert C.resolve_universe([], None, cache) == live
    cache.write_text(json.dumps({"schema": "other"}))
    assert C.universe_from_estate_cache(cache) is None


def test_an_owner_whose_listing_failed_is_named_not_dropped_from_the_universe(monkeypatch, tmp_path):
    import types

    monkeypatch.setattr(C, "gh_available", lambda: True)
    listing = [{"nameWithOwner": "good/a", "isArchived": False, "isFork": False, "isPrivate": True, "pushedAt": None}]

    def fake_run(argv, **kw):
        owner = argv[3]
        if owner == "good":
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(listing))
        return types.SimpleNamespace(returncode=1, stdout="")  # gh failed for this owner

    monkeypatch.setattr(C.subprocess, "run", fake_run)
    rows, src, unlisted = C.universe_from_gh_repo_list(["good", "unreadable"])
    assert [r["repo"] for r in rows] == ["good/a"] and src == "gh-repo-list:good" and unlisted == ["unreadable"]
    # the resolver carries it through when no cache is on disk; a listing that failed for every owner is no universe
    monkeypatch.setenv("LIMEN_OWNERS", "good,unreadable")
    assert C.resolve_universe([], None, tmp_path / "none.json") == (rows, src, ["unreadable"])
    monkeypatch.setenv("LIMEN_OWNERS", "unreadable")
    assert C.universe_from_gh_repo_list(["unreadable"]) is None
    # owner discovery: the organizations call failing is named too, one call earlier than the listings
    monkeypatch.setattr(C, "gh_api", lambda p: (C.OK, {"login": "good"}) if p == "user" else (C.ERROR, None))
    assert C.universe_from_gh_repo_list(None) == (rows, "gh-repo-list:good", ["orgs-of:good"])
    assert C.resolve_universe([], None, tmp_path / "none.json") == ([], "none", [])
    # the receipt names the owner, is incomplete (retry horizon) and exits 2 even on a clean scan
    monkeypatch.setattr(C, "gh_api", FakeGH(_clean_table("good/a")))
    report = C.run_census(rows, src, budget_seconds=60, root=ROOT, unlisted_owners=unlisted)
    assert report["denominators"]["universe_unlisted_owners"] == 1 and report["unlisted_owners"] == ["unreadable"]
    assert report["totals"]["verdicts"] == {"active": 1} and C.exit_code_for(report) == 2
    assert not C.receipt_is_complete(report)
    md = C.render_markdown(report)
    assert "owners unlisted 1" in md and "Universe incomplete" in md and "- unreadable" in md
    # a listing exactly at `gh repo list --limit` may be longer than it says: named, never trusted whole
    big = [
        {"nameWithOwner": f"good/r{i}", "isArchived": False, "isFork": False, "isPrivate": True, "pushedAt": None}
        for i in range(C.REPO_LIST_LIMIT)
    ]
    monkeypatch.setattr(
        C.subprocess, "run", lambda argv, **kw: types.SimpleNamespace(returncode=0, stdout=json.dumps(big))
    )
    rows, src, caveats = C.universe_from_gh_repo_list(["good"])
    assert len(rows) == C.REPO_LIST_LIMIT and src == "gh-repo-list:good" and caveats == ["capped:good"]


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
        and report["totals"]["scheduled_runs_listed"] == 3
    )
    assert (tmp_path / "census.md").exists() and "failing: hygiene" in (tmp_path / "census.md").read_text()
    # fresh receipt → nothing to do without --force
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt), "--interval-hours", "168"]) == 0
    # a pass that reads nothing never overwrites a receipt that read something: it lands beside it
    monkeypatch.setattr(C, "gh_api", lambda path: (C.UNREACHABLE, None))
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt), "--force"]) == 3  # read nothing ≠ found nothing
    assert json.loads(receipt.read_text())["denominators"]["scanned"] == 1
    sidecar = tmp_path / "census.last-attempt.json"
    assert json.loads(sidecar.read_text())["denominators"]["scanned"] == 0
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt), "--force", "--replace"]) == 3
    assert json.loads(receipt.read_text())["denominators"]["scanned"] == 0


def test_exit_codes_tell_engine_errors_from_read_nothing_from_findings_from_partial_coverage(monkeypatch):
    clean = _clean_table("4444J99/one")
    clean["repos/4444J99/one/issues?state=all&per_page=100&page=1&sort=created&direction=desc"] = (C.OK, [])
    monkeypatch.setattr(C, "gh_api", FakeGH(clean))
    report = C.run_census([{"repo": "4444J99/one"}], "explicit", budget_seconds=60, root=ROOT)
    assert report["totals"]["verdicts"] == {"active": 1} and C.exit_code_for(report) == 0
    # an auto-disabled schedule beside a healthy one: the repository verdict stays active, the finding does not vanish
    monkeypatch.setattr(C, "gh_api", FakeGH(_table("4444J99/one")))
    mixed = C.run_census([{"repo": "4444J99/one"}], "explicit", budget_seconds=60, root=ROOT)
    assert mixed["totals"]["verdicts"] == {"active": 1} and mixed["totals"]["gh_workflows_disabled_inactivity"] == 1
    assert C.exit_code_for(mixed) == 1
    # a failing scheduled workflow beside a healthy one is a finding too
    failing = {**report, "totals": {**report["totals"], "workflows_failing_last_scheduled_run": 1}}
    assert C.exit_code_for(failing) == 1
    monkeypatch.setattr(C, "gh_api", FakeGH(clean))
    # one unreachable neighbour: no finding, but coverage is incomplete
    report = C.run_census([{"repo": "4444J99/one"}, {"repo": "4444J99/dark"}], "explicit", budget_seconds=60, root=ROOT)
    assert report["denominators"]["unreachable"] == 1 and C.exit_code_for(report) == 2
    # a registry gap is a finding
    report = C.run_census([{"repo": "4444J99/one"}], "explicit", budget_seconds=60, root=ROOT, check_registry=True)
    assert C.exit_code_for(report) == 1
    # everything skipped → read nothing, exit 3, whatever the reason
    report = C.run_census([{"repo": "4444J99/one", "archived": True}], "explicit", root=ROOT, skip_archived=True)
    assert report["denominators"]["scanned"] == 0 and report["denominators"]["skipped_archived"] == 1
    assert C.exit_code_for(report) == 3

    # the engine blowing up on one repository is an internal error, never a verdict about the repository
    def explode(repo, **kw):
        raise AttributeError("'list' object has no attribute 'get'")

    monkeypatch.setattr(C, "scan_repo", explode)
    report = C.run_census([{"repo": "4444J99/one"}, {"repo": "4444J99/two"}], "explicit", budget_seconds=60, root=ROOT)
    d = report["denominators"]
    assert d["internal_errors"] == 2 and d["scanned"] == 0 and d["unreachable"] == 0
    assert report["totals"]["verdicts"] == {"error": 2}
    assert report["internal_errors"][0]["notes"] == [
        "internal error: AttributeError: 'list' object has no attribute 'get'"
    ]
    assert C.exit_code_for(report) == 4
    assert "Internal errors (the engine" in C.render_markdown(report)


def test_failing_runs_of_workflows_no_longer_firing_are_history_not_findings(monkeypatch):
    repo = "4444J99/one"
    table = _clean_table(repo)
    table[f"repos/{repo}/issues?state=all&per_page=100&page=1&sort=created&direction=desc"] = (C.OK, [])
    nightly = ".github/workflows/nightly.yml"
    wf_key = f"repos/{repo}/actions/workflows?per_page=100&page=1"
    wf = table[wf_key][1]
    table[wf_key] = (
        C.OK,
        {
            **wf,
            "workflows": wf["workflows"]
            + [{"path": nightly, "state": "disabled_manually", "name": "nightly", "id": 9}],
        },
    )
    tree_key = f"repos/{repo}/git/trees/main?recursive=1"
    tree = table[tree_key][1]
    table[tree_key] = (C.OK, {**tree, "tree": tree["tree"] + [{"type": "blob", "path": nightly}]})
    table[f"repos/{repo}/contents/{nightly}?ref=main"] = (C.OK, _b64(WORKFLOW_CRON))
    runs_key = f"repos/{repo}/actions/runs?event=schedule&per_page=100"

    def runs(hygiene: str) -> tuple:
        rows = [
            {"name": "nightly", "created_at": "2026-10-24T01:00:00Z", "conclusion": "failure"},  # disabled since
            {"name": "hygiene", "created_at": "2026-10-23T13:36:00Z", "conclusion": hygiene},
        ]
        return C.OK, {"total_count": len(rows), "workflow_runs": rows}

    table[runs_key] = runs("success")
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["verdict"] == "active" and row["partial"] is False
    assert row["failing_workflows"] == [] and row["failing_not_firing"] == ["nightly"]
    report = C.build_report(
        [row], universe=[{"repo": repo}], universe_source="explicit", unscanned=[], gaps=None, started=0.0
    )
    assert report["totals"]["workflows_failing_last_scheduled_run"] == 0 and C.exit_code_for(report) == 0
    # the healthy sibling failing is still a finding beside the active verdict (round-2 fix 3 holds)
    table[runs_key] = runs("failure")
    row = C.scan_repo(repo)
    assert row["failing_workflows"] == ["hygiene"] and row["failing_not_firing"] == ["nightly"]
    report = C.build_report(
        [row], universe=[{"repo": repo}], universe_source="explicit", unscanned=[], gaps=None, started=0.0
    )
    assert report["totals"]["workflows_failing_last_scheduled_run"] == 1 and C.exit_code_for(report) == 1


def test_history_requests_are_counted_and_an_unread_git_history_is_not_an_empty_one(monkeypatch, tmp_path):
    repo = "4444J99/example"
    fake = FakeGH(_table(repo))
    monkeypatch.setattr(C, "gh_api", fake)
    row = C.scan_repo(repo, clone=tmp_path, history_cap=10)
    assert len([c for c in fake.calls if "/commits" in c]) == 3  # the listing and two sampled details
    assert row["api_calls"] == len(fake.calls)  # every request, history included, reaches the rate check
    # a git read that fails or times out is unread, never empty
    monkeypatch.setattr(C, "_git", lambda *a: None)
    hist = C.history_from_git(tmp_path)
    assert hist["status"] == C.ERROR and hist["truncated"] is True and hist["events"] == [] and "unread" in hist["note"]
    monkeypatch.setattr(C, "clone_is_full", lambda clone: True)
    row = C.scan_repo(repo, clone=tmp_path)
    assert row["channels"]["history"] == "git:error" and row["partial"] is True


def test_an_unread_history_is_coverage_incomplete_but_a_read_one_is_not(monkeypatch):
    repo = "4444J99/one"
    table = _clean_table(repo)
    listing = f"repos/{repo}/commits?path=.github/workflows&per_page=100"
    table[listing] = (C.UNREACHABLE, None)
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["channels"]["history"] == "api:unreachable" and row["partial"] is True
    report = C.build_report(
        [row], universe=[{"repo": repo}], universe_source="explicit", unscanned=[], gaps=None, started=0.0
    )
    assert report["denominators"]["scanned_partial"] == 1 and C.exit_code_for(report) == 2
    # no commits touched the workflow dir: the Commits API answers 200 [] — read, not partial
    table[listing] = (C.OK, [])
    row = C.scan_repo(repo)
    assert row["channels"]["history"] == "api" and row["partial"] is False
    # a 404 there is not an observation about commits (the repository or the token's view of it is gone): partial
    del table[listing]
    row = C.scan_repo(repo)
    assert row["channels"]["history"] == "api:absent" and row["partial"] is True


def test_runs_are_grouped_by_workflow_path_and_failing_joins_on_it(monkeypatch):
    repo = "4444J99/one"
    table = _clean_table(repo)
    a, b = ".github/workflows/a.yml", ".github/workflows/b.yml"
    wf_key = f"repos/{repo}/actions/workflows?per_page=100&page=1"
    wf = table[wf_key][1]
    twins = [
        {"path": a, "state": "active", "name": "Nightly", "id": 11},
        {"path": b, "state": "active", "name": "Nightly", "id": 12},
    ]
    table[wf_key] = (C.OK, {**wf, "workflows": wf["workflows"] + twins})
    tree_key = f"repos/{repo}/git/trees/main?recursive=1"
    tree = table[tree_key][1]
    table[tree_key] = (
        C.OK,
        {**tree, "tree": tree["tree"] + [{"type": "blob", "path": a}, {"type": "blob", "path": b}]},
    )
    for path in (a, b):
        table[f"repos/{repo}/contents/{path}?ref=main"] = (C.OK, _b64(WORKFLOW_CRON))
    runs = [
        {"name": "Nightly", "path": a, "created_at": "2026-10-24T02:00:00Z", "conclusion": "success"},
        {"name": "Nightly", "path": b, "created_at": "2026-10-24T01:00:00Z", "conclusion": "failure"},
        {"name": "hygiene", "created_at": "2026-10-23T13:36:00Z", "conclusion": "success"},
    ]
    table[f"repos/{repo}/actions/runs?event=schedule&per_page=100"] = (C.OK, {"total_count": 3, "workflow_runs": runs})
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    by = row["fired"]["by_workflow"]
    assert set(by) == {a, b, "hygiene"} and by[a]["name"] == "Nightly" and by[b]["last_conclusion"] == "failure"
    assert (
        row["failing_workflows"] == ["Nightly"] and row["failing_not_firing"] == []
    )  # b.yml, by path, not hidden by a.yml


def test_an_active_workflow_beyond_the_summarized_page_is_unmeasured_and_the_ledger_shows_every_schedule(monkeypatch):
    repo = "4444J99/one"
    table = _clean_table(repo)
    nightly = ".github/workflows/nightly.yml"
    wf_key = f"repos/{repo}/actions/workflows?per_page=100&page=1"
    wf = table[wf_key][1]
    table[wf_key] = (
        C.OK,
        {**wf, "workflows": wf["workflows"] + [{"path": nightly, "state": "active", "name": "hygiene", "id": 9}]},
    )  # a twin display name: nightly.yml is listed as "hygiene" too, and only its PATH says it has no run
    tree_key = f"repos/{repo}/git/trees/main?recursive=1"
    tree = table[tree_key][1]
    table[tree_key] = (C.OK, {**tree, "tree": tree["tree"] + [{"type": "blob", "path": nightly}]})
    table[f"repos/{repo}/contents/{nightly}?ref=main"] = (C.OK, _b64(WORKFLOW_CRON))
    runs_key = f"repos/{repo}/actions/runs?event=schedule&per_page=100"
    page = [
        {
            "name": "hygiene",
            "path": ".github/workflows/hygiene.yml",
            "created_at": f"2026-10-23T{h:02d}:00:00Z",
            "conclusion": "success",
        }
        for h in range(23, -1, -1)
    ]
    table[runs_key] = (
        C.OK,
        {"total_count": 150, "workflow_runs": page},
    )  # 150 runs, 24 on the page: nightly is beyond it
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["fired"]["page_oldest_seen"] == "2026-10-23T00:00:00Z" and row["fired"]["page_runs"] == 24
    # nightly.yml (shown by its display name) is unmeasured although a run on the page carries that same name
    assert row["runs_unmeasured"] == ["hygiene"] and row["failing_workflows"] == [] and row["verdict"] == "active"
    report = C.build_report(
        [row], universe=[{"repo": repo}], universe_source="explicit", unscanned=[], gaps=None, started=0.0
    )
    assert report["totals"]["workflows_runs_unmeasured"] == 1
    assert C.exit_code_for(report) == 2  # an unmeasured latest run is incomplete coverage, never a clean 0
    md = C.render_markdown(report)
    assert "latest run beyond the summarized page (unmeasured): hygiene" in md
    # when the page holds every retained run, a silent workflow simply never fired: nothing is unmeasured
    table[runs_key] = (C.OK, {"total_count": 24, "workflow_runs": page})
    row = C.scan_repo(repo)
    assert row["runs_unmeasured"] == []
    # the ledger renders dependabot intervals, renovate schedules and cloud routines as the schedules they are: only
    # the workflow without a cron is "without a schedule"
    timed, rest = C._timed_declarations(
        [
            {"kind": "dependabot", "path": ".github/dependabot.yml", "intervals": ["weekly monday"]},
            {"kind": "cloud-routines", "path": "cloud-routines.json", "routines": 13},
            {"kind": "renovate", "path": "renovate.json", "schedule": ["after 10pm"]},
            {"kind": "gh-workflow", "path": ".github/workflows/build.yml", "crons": []},
        ]
    )
    assert [x["kind"] for x in timed] == ["dependabot", "cloud-routines", "renovate"] and [x["kind"] for x in rest] == [
        "gh-workflow"
    ]
    assert "dependabot without a schedule" not in md and "cloud-routines without a schedule" not in md
    assert "1 gh-workflow without a schedule" in md  # build.yml, which has no cron


def test_an_empty_repository_answering_409_is_empty_not_partial(monkeypatch):
    repo = "4444J99/one"
    table = _table(repo)
    table[f"repos/{repo}"] = (C.OK, {**table[f"repos/{repo}"][1], "size": 0})
    empty = (C.ERROR, {"message": "Git Repository is empty.", "status": "409"})
    table[f"repos/{repo}/git/trees/main?recursive=1"] = empty
    table[f"repos/{repo}/commits?path=.github/workflows&per_page=100"] = empty  # the Commits API says it too
    fake = FakeGH(table)
    monkeypatch.setattr(C, "gh_api", fake)
    row = C.scan_repo(repo)
    assert row["channels"]["tree"] == "empty" and row["channels"]["history"] == "empty" and row["partial"] is False
    assert not any("/commits" in c for c in fake.calls)  # nothing to read: the Commits API is never asked
    # size 0 proves nothing on its own (GitHub computes it lazily): a 500 on the tree is an error, never an empty tree
    table[f"repos/{repo}/git/trees/main?recursive=1"] = (C.ERROR, {"message": "Server Error", "status": "500"})
    row = C.scan_repo(repo)
    assert row["channels"]["tree"] == C.ERROR and row["partial"] is True and row["actions_registered_not_in_tree"] == []
    # the guard needs size 0 AND GitHub's own word: a non-empty repository whose tree answers 404 is a partial read,
    # and its history is still asked for
    table[f"repos/{repo}"] = (C.OK, {**table[f"repos/{repo}"][1], "size": 7})
    table[f"repos/{repo}/git/trees/main?recursive=1"] = (C.ABSENT, {"message": "Not Found", "status": "404"})
    table[f"repos/{repo}/commits?path=.github/workflows&per_page=100"] = (C.OK, [])
    fake = FakeGH(table)
    monkeypatch.setattr(C, "gh_api", fake)
    row = C.scan_repo(repo)
    assert row["channels"]["tree"] == C.ABSENT and row["partial"] is True and row["channels"]["history"] != "empty"
    assert any("/commits" in c for c in fake.calls)


def _receipt_file(path, *, generated_at, source, repos, partial=0):
    C.write_receipt(
        path,
        {
            "schema": C.SCHEMA,
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "denominators": {
                "universe_source": source,
                "universe_count": len(repos),
                "scanned": len(repos),
                "scanned_partial": partial,
                "unreachable": 0,
                "unscanned_by_budget": 0,
                "internal_errors": 0,
            },
            "repos": [{"repo": r} for r in repos],
        },
    )


def test_receipt_freshness_respects_scope_and_counts_the_last_attempt(tmp_path):
    now = C.datetime.now(C.timezone.utc)
    receipt, sidecar = tmp_path / "census.json", C.sidecar_path(tmp_path / "census.json")
    assert sidecar.name == "census.last-attempt.json"
    one = ("explicit", frozenset({"a/b"}))
    _receipt_file(receipt, generated_at=now - C.timedelta(hours=1), source="explicit", repos=["a/b"])
    assert C.receipt_is_fresh(receipt, 168, now=now, scope=one)
    assert not C.receipt_is_fresh(receipt, 168, now=now, scope=("explicit", frozenset({"a/b", "c/d"})))
    assert not C.receipt_is_fresh(receipt, 168, now=now, scope=("universe", None))
    # the universe-wide receipt is one scope whichever roster produced it
    _receipt_file(receipt, generated_at=now - C.timedelta(hours=1), source="estate-cache:/x", repos=["a/b"])
    assert C.receipt_is_fresh(receipt, 168, now=now, scope=("universe", None))
    assert C.receipt_scope({"denominators": {"universe_source": "gh-repo-list:o"}}) == ("universe", None)
    assert C.receipt_scope({"denominators": {"universe_source": "repos-file:/r.txt"}}) == ("repos-file", "/r.txt")
    assert C.requested_scope([], C.Path("/r.txt")) == ("repos-file", "/r.txt") and C.requested_scope([], None) == (
        "universe",
        None,
    )
    # an explicit receipt covers every name it was asked for — scanned, unscanned by budget or skipped — and names
    # compare case-insensitively, as GitHub does
    cut = {
        "denominators": {"universe_source": "explicit"},
        "repos": [{"repo": "A/B"}],
        "unscanned_by_budget": ["c/d"],
        "skipped_archived": ["e/f"],
    }
    assert C.receipt_scope(cut) == C.requested_scope(["a/b", "C/D", "e/f"], None)
    assert C._dedupe([{"repo": "a/b"}, {"repo": "A/B"}]) == [{"repo": "a/b"}]
    # an old standing receipt plus a degraded attempt parked beside it: the attempt earns the retry horizon
    _receipt_file(receipt, generated_at=now - C.timedelta(days=10), source="explicit", repos=["a/b"])
    assert not C.receipt_is_fresh(receipt, 168, now=now, scope=one, sidecar=sidecar)
    _receipt_file(sidecar, generated_at=now - C.timedelta(hours=2), source="explicit", repos=["a/b"], partial=1)
    assert C.receipt_is_fresh(receipt, 168, now=now, scope=one, sidecar=sidecar, retry_hours=24)
    assert not C.receipt_is_fresh(receipt, 168, now=now, scope=one, sidecar=sidecar, retry_hours=1)
    _receipt_file(sidecar, generated_at=now - C.timedelta(hours=2), source="explicit", repos=["z/z"], partial=1)
    assert not C.receipt_is_fresh(receipt, 168, now=now, scope=one, sidecar=sidecar)  # another scope's attempt


def test_the_standing_receipt_is_kept_or_replaced_by_rule_and_the_ledger_is_written_first(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "gh_api", FakeGH(_clean_table("4444J99/one")))
    receipt = tmp_path / "census.json"
    both = ["--repos", "4444J99/one", "4444J99/two", "--receipt", str(receipt)]
    assert C.main(both + ["--force"]) == 2  # two is unreachable: half the universe read completely
    d = json.loads(receipt.read_text())["denominators"]
    assert (d["universe_count"], d["scanned"], d["unreachable"]) == (2, 1, 1)
    # a different explicit set is another scope: while the standing receipt is within its horizon it is parked beside it
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt), "--force"]) == 0
    assert json.loads(receipt.read_text())["denominators"]["universe_count"] == 2
    assert json.loads(C.sidecar_path(receipt).read_text())["denominators"]["universe_count"] == 1
    # … and that attempt counts for ITS scope: an immediate rerun is a no-op (not one GitHub call) while the retry
    # horizon holds, and a third scope — neither the receipt's nor the last attempt's — scans
    fake = FakeGH(_clean_table("4444J99/one"))
    monkeypatch.setattr(C, "gh_api", fake)
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt)]) == 0 and fake.calls == []
    assert C.main(["--repos", "4444J99/two", "--receipt", str(receipt)]) == 3 and fake.calls != []
    assert json.loads(receipt.read_text())["denominators"]["universe_count"] == 2  # parked, never over the receipt
    # the same scope with lower complete coverage (nothing readable) is parked; the standing receipt survives
    monkeypatch.setattr(C, "gh_api", lambda path: (C.UNREACHABLE, None))
    assert C.main(both + ["--force"]) == 3
    assert json.loads(receipt.read_text())["denominators"]["scanned"] == 1
    monkeypatch.setattr(C, "gh_api", FakeGH(_clean_table("4444J99/one")))
    # a universe-scope pass displaces a narrower receipt …
    cache = tmp_path / "estate.json"
    cache.write_text(
        json.dumps(
            {
                "schema": C.ESTATE_CACHE_SCHEMA,
                "fetched_at": C.datetime.now(C.timezone.utc).isoformat(timespec="seconds"),
                "repos": {"4444J99/one": {"archived": False, "fork": False}},
            }
        )
    )
    universe = ["--receipt", str(receipt), "--estate-cache", str(cache)]
    assert C.main(universe + ["--force"]) == 0
    assert json.loads(receipt.read_text())["denominators"]["universe_source"].startswith("estate-cache:")
    # … and no explicit pass, however complete, overwrites a universe receipt
    assert C.main(["--repos", "4444J99/one", "--receipt", str(receipt), "--force"]) == 0
    assert json.loads(receipt.read_text())["denominators"]["universe_source"].startswith("estate-cache:")
    # the rule itself: a short universe (an owner unlisted) is incomplete and never replaces a complete receipt …
    standing = json.loads(receipt.read_text())
    short = {**standing, "denominators": {**standing["denominators"], "universe_unlisted_owners": 1}}
    assert C.keeps_standing_receipt(standing, short, ("universe", None), interval_hours=168) is not None
    # … unless the standing receipt is past its own horizon, when the newer pass is the census
    old = {**standing, "generated_at": "2026-01-01T00:00:00+00:00"}
    assert C.keeps_standing_receipt(old, short, ("universe", None), interval_hours=168) is None
    assert (
        C.coverage_share(standing) == 1.0
        and C.keeps_standing_receipt(None, short, ("universe", None), interval_hours=1) is None
    )

    def narrow(source, repos, generated_at="2026-10-24T00:00:00+00:00", **d):
        return {
            "schema": C.SCHEMA,
            "generated_at": generated_at,
            "denominators": {
                "universe_source": source,
                "universe_count": len(repos),
                "scanned": len(repos),
                "scanned_partial": 0,
                "unreachable": 0,
                "unscanned_by_budget": 0,
                "internal_errors": 0,
                **d,
            },
            "repos": [{"repo": r} for r in repos],
        }

    at = C.datetime(2026, 10, 24, 1, tzinfo=C.timezone.utc)
    # a sibling narrow scope is parked only while the standing receipt is within its horizon — and it is "another"
    # scope, not a narrower one; a universe receipt is never overwritten by a narrower pass, at any age
    ab, cd = narrow("explicit", ["a/b"]), narrow("explicit", ["c/d"])
    only_cd = ("explicit", frozenset({"c/d"}))
    parked = C.keeps_standing_receipt(ab, cd, only_cd, interval_hours=168, now=at)
    assert parked is not None and "another explicit scope" in parked and "narrower" not in parked
    parked = C.keeps_standing_receipt(
        ab, narrow("repos-file:f", ["c/d"]), ("repos-file", "f"), interval_hours=168, now=at
    )
    assert parked is not None and "another" in parked
    aged = {**ab, "generated_at": "2026-01-01T00:00:00+00:00"}
    assert C.keeps_standing_receipt(aged, cd, only_cd, interval_hours=168, now=at) is None
    assert C.keeps_standing_receipt(old, cd, only_cd, interval_hours=168, now=at) is not None  # old IS a universe one
    # a complete census outranks an incomplete one whatever the two universes' sizes: the share rule never keeps an
    # incomplete standing receipt over a complete pass
    incomplete = narrow("estate-cache:x", [f"o/r{i}" for i in range(100)], universe_unlisted_owners=1)
    bigger = narrow("estate-cache:x", [f"o/r{i}" for i in range(110)])
    bigger["denominators"].update(universe_count=120, unscanned_by_budget=10)
    assert C.coverage_share(bigger) < C.coverage_share(incomplete) and C.receipt_is_complete(bigger)
    assert C.keeps_standing_receipt(incomplete, bigger, ("universe", None), interval_hours=168, now=at) is None
    # complete coverage subtracts partially read rows: the same repositories read less completely are parked
    half = narrow("explicit", ["a/b", "c/d"], scanned_partial=1)
    none_whole = narrow("explicit", ["a/b", "c/d"], scanned_partial=2)
    ab_cd = ("explicit", frozenset({"a/b", "c/d"}))
    parked = C.keeps_standing_receipt(half, none_whole, ab_cd, interval_hours=168, now=at)
    assert parked is not None and "complete coverage 0% is below the standing receipt's 50%" in parked
    # an incomplete standing receipt stands only for the retry horizon, and one without a date is history
    later = at + C.timedelta(hours=25)
    assert C.keeps_standing_receipt(half, none_whole, ab_cd, interval_hours=168, retry_hours=24, now=later) is None
    assert C.keeps_standing_receipt(half, none_whole, ab_cd, interval_hours=168, retry_hours=48, now=later) is not None
    undated = {k: v for k, v in half.items() if k != "generated_at"}
    assert C.keeps_standing_receipt(undated, none_whole, ab_cd, interval_hours=168, now=at) is None
    # the ledger is written before the receipt: a failure between the two never pairs a fresh receipt with a stale ledger
    fresh = tmp_path / "fresh" / "census.json"

    def boom(path, report):
        raise OSError("disk full")

    monkeypatch.setattr(C, "write_receipt", boom)
    with pytest.raises(OSError):
        C.main(["--repos", "4444J99/one", "--receipt", str(fresh), "--force"])
    assert fresh.with_suffix(".md").exists() and not fresh.exists()


def test_partial_reads_never_conclude_absence(monkeypatch):
    repo = "4444J99/one"
    # the tree could not be listed: nothing about carriers is known, so the verdict is partial, not none
    table = _table(repo)
    table[f"repos/{repo}/git/trees/main?recursive=1"] = (C.UNREACHABLE, {"message": "not enabled"})
    for key in [k for k in table if "/contents/" in k]:
        del table[key]
    table[f"repos/{repo}/commits?path=.github/workflows&per_page=100"] = (C.OK, [])
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["partial"] is True and row["channels"]["tree"] == C.UNREACHABLE
    assert row["actions_registered_not_in_tree"] == []  # an unread tree cannot say a workflow is gone from it
    assert row["verdict"] == "auto-disabled"  # positive evidence (old-scale is disabled_inactivity) still stands
    by_path = {d["path"]: d for d in row["declarations"]}
    assert by_path[".github/workflows/old-scale.yml"]["note"].startswith("state from the Actions API")
    assert ".github/workflows/tmp-diag.yml" not in by_path  # no "absent from tree" claim without a complete tree
    table[f"repos/{repo}/actions/workflows?per_page=100&page=1"] = (C.OK, {"workflows": [], "total_count": 0})
    row = C.scan_repo(repo)
    assert row["verdict"] == "partial" and row["partial"] is True

    # a truncated tree lists what it saw but never claims a registered workflow is absent from it
    table = _table(repo)
    tree = table[f"repos/{repo}/git/trees/main?recursive=1"][1]
    table[f"repos/{repo}/git/trees/main?recursive=1"] = (C.OK, {**tree, "truncated": True})
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["partial"] is True and row["channels"]["tree"] == "truncated"
    assert row["actions_registered_not_in_tree"] == [] and row["verdict"] == "active"

    # a workflow whose contents could not be read is still in the tree — not "registered but absent"
    table = _table(repo)
    table[f"repos/{repo}/contents/.github/workflows/build.yml?ref=main"] = (C.ERROR, {"status": "500"})
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["actions_registered_not_in_tree"] == [".github/workflows/tmp-diag.yml"]
    assert row["channels"]["contents"] == "partial:1 unread,0 skipped" and row["partial"] is True
    assert any("build.yml: contents error" in n for n in row["notes"])

    # the scheduled-run listing unreadable: an active cron is fired-unmeasured, which is not a finding
    table = _table(repo)
    table[f"repos/{repo}/actions/runs?event=schedule&per_page=100"] = (C.UNREACHABLE, None)
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert (
        row["fired"] is None
        and row["verdict"] == "fired-unmeasured"
        and row["channels"]["scheduled-runs"] == (C.UNREACHABLE)
    )
    row["declarations"] = [d for d in row["declarations"] if d["path"] != OLD_SCALE]  # that one is a finding of its own
    report = C.build_report(
        [row], universe=[{"repo": repo}], universe_source="explicit", unscanned=[], gaps=None, started=0.0
    )
    assert report["denominators"]["scanned_partial"] == 1 and C.exit_code_for(report) == 2
    assert "Partially read" in C.render_markdown(report)

    # the workflow listing unreadable: declared crons have unknown state, listed as gaps but flagged unverified
    table = _table(repo)
    table[f"repos/{repo}/actions/workflows?per_page=100&page=1"] = (C.ERROR, {"status": "500"})
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["verdict"] == "declared-state-unknown"
    gaps = C.registry_gaps([row], set())
    assert gaps[0]["unverified"] == [".github/workflows/hygiene.yml", ".github/workflows/old-scale.yml"]

    # a repository with no commits has no tree: that is empty, not partial
    table = _table(repo)
    table[f"repos/{repo}"] = (C.OK, {**table[f"repos/{repo}"][1], "size": 0})
    table[f"repos/{repo}/git/trees/main?recursive=1"] = (C.ABSENT, {"message": "Not Found", "status": "404"})
    monkeypatch.setattr(C, "gh_api", FakeGH(table))
    row = C.scan_repo(repo)
    assert row["channels"]["tree"] == "empty" and row["partial"] is False

    # past the deadline, the remaining channels are skipped and recorded, never silently read as empty
    monkeypatch.setattr(C, "gh_api", FakeGH(_table(repo)))
    row = C.scan_repo(repo, deadline=0.0)
    assert row["channels"]["contents"].endswith("skipped") and row["channels"]["scheduled-runs"] == "skipped:budget"
    assert row["channels"]["issues-prs"] == "skipped:budget" and row["channels"]["history"] == "skipped:budget"
    assert row["partial"] is True and row["actions_registered_not_in_tree"] == [".github/workflows/tmp-diag.yml"]
    by_path = {d["path"]: d for d in row["declarations"]}
    assert (
        by_path[".github/workflows/old-scale.yml"]["state"] == "disabled_inactivity"
    )  # API evidence survives the skip
    assert "not read" in by_path[".github/workflows/old-scale.yml"]["note"]


def test_history_sampling_and_the_attempts_pager_stop_at_the_census_deadline(monkeypatch):
    repo = "4444J99/one"
    clock = {"t": 0.0}
    monkeypatch.setattr(C.time, "monotonic", lambda: clock["t"])
    fake = FakeGH(_table(repo))

    def ticking(path):  # every GitHub call costs 10 s of budget
        clock["t"] += 10.0
        return fake(path)

    monkeypatch.setattr(C, "gh_api", ticking)
    hist = C.history_from_api(repo, 10, deadline=15.0)  # listing → 10 s; one detail → 20 s; the second is not asked
    assert len([c for c in fake.calls if "/commits/" in c]) == 1
    assert hist["status"] == "partial" and hist["truncated"] is True and hist["sampled"] == 2
    assert hist["note"] == "1 of 2 sampled commits unread: census budget reached"
    clock["t"] = 0.0
    fake.calls.clear()
    hist = C.history_from_api(repo, 10)  # no deadline: every sampled commit is read
    assert len([c for c in fake.calls if "/commits/" in c]) == 2 and hist["status"] == C.OK and "note" not in hist
    pages: list[str] = []

    def call(path):
        pages.append(path)
        clock["t"] += 10.0
        return C.OK, [{"number": len(pages), "title": "cron job", "state": "open", "labels": []}] * 100

    clock["t"] = 0.0
    att = C.read_attempts(repo, call, pages=3, deadline=5.0)  # page 1 is always read; page 2 is past the deadline
    assert len(pages) == 1 and att["status"] == "partial" and att["truncated"] is True and len(att["items"]) == 100
    assert att["note"] == "issues listing stopped after 1 page(s): census budget reached"
    # scan_repo hands its deadline to both readers, and a stopped history lands on the row as partial
    clock["t"] = 0.0
    fake.calls.clear()
    seen: dict[str, float | None] = {}
    real_history, real_attempts = C.history_from_api, C.read_attempts

    def spy_history(*a, **k):
        seen["history"] = k.get("deadline")
        return {**real_history(*a, **k), "status": "partial", "truncated": True}

    def spy_attempts(*a, **k):
        seen["attempts"] = k.get("deadline")
        return real_attempts(*a, **k)

    monkeypatch.setattr(C, "history_from_api", spy_history)
    monkeypatch.setattr(C, "read_attempts", spy_attempts)
    row = C.scan_repo(repo, deadline=10_000.0)
    assert seen == {"history": 10_000.0, "attempts": 10_000.0}
    assert row["channels"]["history"] == "api:partial" and row["history"]["truncated"] is True


def test_workflow_listing_is_paginated(monkeypatch):
    repo = "4444J99/many"
    table = _table(repo)
    page1 = [{"path": f".github/workflows/w{i}.yml", "state": "active", "name": f"w{i}", "id": i} for i in range(100)]
    page2 = [{"path": ".github/workflows/hygiene.yml", "state": "disabled_manually", "name": "hygiene", "id": 999}]
    table[f"repos/{repo}/actions/workflows?per_page=100&page=1"] = (C.OK, {"workflows": page1, "total_count": 101})
    table[f"repos/{repo}/actions/workflows?per_page=100&page=2"] = (C.OK, {"workflows": page2, "total_count": 101})
    fake = FakeGH(table)
    monkeypatch.setattr(C, "gh_api", fake)
    row = C.scan_repo(repo)
    by_path = {d["path"]: d for d in row["declarations"]}
    assert by_path[".github/workflows/hygiene.yml"]["state"] == "disabled_manually"  # found on page 2
    assert (
        sum(1 for c in fake.calls if "/actions/workflows?" in c) == 2 and row["channels"]["actions-workflows"] == C.OK
    )


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
    report = C.run_census([{"repo": "4444J99/one"}, {"repo": "4444J99/two"}], "explicit", budget_seconds=5, root=ROOT)
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
    # a word that only names the repository is not scheduling intent: "automation" inside universal-mail--automation
    rows = [
        {"number": 1, "title": "Activate release automation", "state": "closed", "labels": []},
        {"number": 2, "title": "Fix scheduler repo paths", "state": "closed", "labels": []},
        {"number": 3, "title": "Automation: add nightly cron", "state": "open", "labels": []},
    ]
    att = C.read_attempts("4444J99/universal-mail--automation", lambda path: (C.OK, rows), pages=1)
    assert [i["number"] for i in att["items"]] == [2, 3] and att["seen"] == 3
    assert (
        C.ATTEMPT_RX.search("Scheduled tasks for the digest")
        and C.ATTEMPT_RX.search("keepalive")
        and not C.ATTEMPT_RX.search("Rotate keys")
    )
