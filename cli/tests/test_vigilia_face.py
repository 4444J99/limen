"""Tests for the VIGILIA face (build #4) — renders the C-suite from the seat."""

from __future__ import annotations

from limen.vigilia import face, params


def test_load_seat_real_has_ciso_fold():
    # build #2: identity·authority·integrity gathered under the CISO office.
    # R4 (2026-07-18): host-hygiene joined the fold — the "stop asking" mandate is
    # literally dialog-silencing (the agent-curable macOS dialog estate self-heals).
    seat = face.load_seat()
    assert "CISO" in seat["officers"]
    assert set(seat["officers"]["CISO"]["organs"]) == {"identity", "authority", "integrity", "host-hygiene"}


def test_render_derives_officers_from_seat(monkeypatch):
    monkeypatch.setattr(
        face,
        "load_seat",
        lambda: {
            "organs": [
                {"name": "vitals", "status": "built"},
                {"name": "face", "status": "built"},
                {"name": "ghost", "status": "missing"},
            ],
            "officers": {
                "CFO": {"mandate": "don't crash", "organs": ["vitals"]},
                "CCO": {"mandate": "one pane", "organs": ["face"]},
            },
        },
    )
    monkeypatch.setattr(face, "_live_overlay", lambda: {"vitals": "L1/ok"})
    out = face.render()
    assert "CFO" in out and "CCO" in out
    assert "vitals" in out and "L1/ok" in out
    assert "2/2 organs built" in out
    assert "ghost" in out  # an organ under no officer is surfaced, not hidden


def test_render_handles_empty_seat(monkeypatch):
    monkeypatch.setattr(face, "load_seat", lambda: {"organs": [], "officers": {}})
    assert "no officers" in face.render()


def test_live_overlay_parses_status(tmp_path, monkeypatch):
    d = tmp_path / "logs" / "vigilia"
    d.mkdir(parents=True)
    (d / "status.json").write_text('{"vitals":{"level":2,"action":"shed"},"integrity":{"status":"ok","drift":false}}')
    monkeypatch.setattr(params, "_repo_root", lambda: tmp_path)
    overlay = face._live_overlay()
    assert overlay["vitals"] == "L2/shed"
    assert overlay["integrity"] == "ok"
