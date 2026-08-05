"""A global halt needs a named human authority and an expiry.

The defect these pin (2026-07-27): `scripts/pause.py` could impose a fleet-wide halt with no
identity check, no provenance, and no TTL, into a gitignored file — so no artifact recorded who
armed it. An agent armed one from a plan document authored by a *previous* agent, framed to it as
"the source of user intent". The operator had said no such thing. It stood four days.

It also shipped `arm` with no counterpart: the tool could impose a halt and had no way to lift one,
so release happened only by hand-rm or by the governor's autoclear.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stamp(delta_hours: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def pause(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs").mkdir()
    return _load("pause_mod", "scripts/pause.py")


@pytest.fixture
def governor(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "logs").mkdir(exist_ok=True)
    return _load("gov_mod", "scripts/autonomy-governor.py")


ARM = ["arm", "--class", "fence", "--reason", "evacuation", "--owner", "some-branch"]


def test_agent_citing_a_plan_is_refused(pause, capsys):
    """The exact 2026-07-27 shape: an agent armed a halt on a plan document's say-so."""
    rc = pause.main([*ARM, "--source-of-intent", "agent", "--authorised-by", "the plan says to pause"])
    assert rc == 2, "a plan is not authority — this must REFUSE, not warn"
    assert not (Path(pause.MARKER)).exists()


@pytest.mark.parametrize("cited", ["docs/foo.md", "a previous agent decided", "the session context", "continuation"])
def test_agent_citing_any_document_shape_is_refused(pause, cited):
    assert pause.main([*ARM, "--source-of-intent", "agent", "--authorised-by", cited]) == 2


def test_agent_naming_a_quoted_human_is_allowed(pause):
    rc = pause.main([*ARM, "--source-of-intent", "agent", "--authorised-by", "operator: 'pause the fleet'"])
    assert rc == 0
    text = Path(pause.MARKER).read_text()
    assert "source_of_intent: agent" in text
    assert "expires_at:" in text, "every marker expires — an unbounded halt is how four days happen"


def test_provenance_is_required_with_no_default(pause):
    """argparse must reject the call outright — a default would be a decision nobody made."""
    with pytest.raises(SystemExit):
        pause.main(ARM)


def test_ttl_is_capped(pause):
    pause.main([*ARM, "--source-of-intent", "human", "--authorised-by", "operator", "--ttl-hours", "100000"])
    expiry = datetime.strptime(
        next(l.split(": ", 1)[1] for l in Path(pause.MARKER).read_text().splitlines() if l.startswith("expires_at:")),
        "%Y-%m-%dT%H:%M:%SZ",
    ).replace(tzinfo=timezone.utc)
    assert expiry <= datetime.now(timezone.utc) + timedelta(hours=pause._MAX_TTL_HOURS + 1)


def test_release_lifts_the_marker_and_leaves_a_receipt(pause):
    pause.main([*ARM, "--source-of-intent", "human", "--authorised-by", "operator"])
    assert Path(pause.MARKER).exists()
    assert pause.main(["release", "--released-by", "operator", "--reason", "never authorised"]) == 0
    assert not Path(pause.MARKER).exists()
    receipts = sorted((Path(pause.ROOT) / "logs" / "pause-receipts").glob("release-*.json"))
    assert receipts, "a release with no receipt is the untraceable hand-rm this verb replaces"
    payload = json.loads(receipts[-1].read_text())
    assert payload["released_by"] == "operator"
    assert payload["marker_was"]["class"] == "fence"
    assert "marker_raw" in payload, "the receipt must preserve what was lifted, verbatim"


def test_release_on_no_marker_is_a_clean_noop(pause):
    assert pause.main(["release", "--released-by", "x", "--reason", "y"]) == 0


# ── the governor half: an expired marker is an ABSENT marker ─────────────────────────────────


def _write(governor, body: str) -> Path:
    marker = Path(governor.PAUSE_MARKER)
    marker.write_text("class: fence\nreason: t\nowner_surface: prose\nowner: b\n" + body)
    return marker


def test_expired_marker_does_not_bind(governor):
    _write(governor, f"expires_at: {_stamp(-1)}\n")
    assert governor._marker_expired(Path(governor.PAUSE_MARKER)) is True
    assert governor.current_mode() != "paused"


def test_live_marker_still_binds(governor):
    _write(governor, f"expires_at: {_stamp(+1)}\n")
    assert governor.current_mode() == "paused"


@pytest.mark.parametrize("body", ["", "expires_at: soon\n"])
def test_missing_or_unparseable_expiry_fails_toward_caution(governor, body):
    """Absence of a valid expiry must never READ as expired — that would make deleting a field
    silently disable the halt, converting a safety control into a foot-gun."""
    _write(governor, body)
    assert governor._marker_expired(Path(governor.PAUSE_MARKER)) is False
    assert governor.current_mode() == "paused"


def test_expired_marker_is_left_on_disk_for_the_audit_trail(governor):
    marker = _write(governor, f"expires_at: {_stamp(-1)}\n")
    governor.current_mode()
    assert marker.exists(), "expiry stops a marker BINDING; removing it is release's job (with a receipt)"


def test_owner_surface_is_still_not_read_as_owner(governor):
    """Widening _marker_fields must not break the strict-prefix parse a 2026-07-15 pause relies on."""
    marker = _write(governor, "")
    assert governor._marker_fields(marker)["owner"] == "b"
