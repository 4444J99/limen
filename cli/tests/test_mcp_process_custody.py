from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mcp_process_custody as custody


def process(alive):
    return SimpleNamespace(pid=90001, poll=lambda: None if alive else 0, wait=lambda **kw: 0)


def test_live_leader_group_is_killed_and_absence_verified(monkeypatch):
    samples = iter(
        [{90001: {"identity": "start:1", "rss_bytes": 100}, 90002: {"identity": "start:2", "rss_bytes": 200}}, {}]
    )
    monkeypatch.setattr(custody, "group_snapshot", lambda pgid: next(samples))
    killed = []
    monkeypatch.setattr(custody.os, "killpg", lambda pid, sig: killed.append(pid))
    owner = custody.Custody(process(True))
    assert owner.close() == "pass"
    assert killed == [90001]
    assert owner.report()["sampled_peak_processes"] == 2
    assert owner.report()["sampled_peak_rss_bytes"] == 300


def test_reused_group_after_leader_exit_is_never_signalled(monkeypatch):
    monkeypatch.setattr(custody, "group_snapshot", lambda pgid: {90002: {"identity": "new-start", "rss_bytes": 1}})
    monkeypatch.setattr(custody.os, "kill", lambda *a: (_ for _ in ()).throw(AssertionError("foreign PID signalled")))
    monkeypatch.setattr(
        custody.os, "killpg", lambda *a: (_ for _ in ()).throw(AssertionError("foreign group signalled"))
    )
    owner = custody.Custody(process(False))
    owner.observed[90002] = "old-start"
    assert owner.close() == "unmeasured"


def test_previously_witnessed_child_cleanup_requires_current_birth_identity(monkeypatch):
    samples = iter([{90002: {"identity": "same-start", "rss_bytes": 1}}, {}])
    monkeypatch.setattr(custody, "group_snapshot", lambda pgid: next(samples))
    monkeypatch.setattr(custody, "identity", lambda pid: "same-start")
    killed = []
    monkeypatch.setattr(custody.os, "kill", lambda pid, sig: killed.append(pid))
    owner = custody.Custody(process(False))
    owner.observed[90002] = "same-start"
    assert owner.close() == "pass"
    assert killed == [90002]


def test_unavailable_snapshot_cannot_certify_cleanup(monkeypatch):
    def unavailable(pgid):
        raise OSError("synthetic observation unavailable")

    monkeypatch.setattr(custody, "group_snapshot", unavailable)
    monkeypatch.setattr(custody.os, "killpg", lambda *a: None)
    owner = custody.Custody(process(True))
    assert owner.close() == "unmeasured"
    assert owner.report()["measurement"] == "unmeasured"
