"""Focused transport contracts for the authenticated conduct client."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path

import pytest

from limen.conduct.broker import ConductConflict, ConductError
from limen.conduct.client import BrokerQuotaExhausted, HttpConductClient

ROOT = Path(__file__).resolve().parents[2]


def test_http_client_sends_stable_user_agent(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"schema_version":"limen.conduct_capabilities.v1"}'

    def fake_urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("limen.conduct.client.urllib.request.urlopen", fake_urlopen)
    client = HttpConductClient(
        "https://limen-runtime.example",
        "fixture-token",
        timeout=17,
    )

    assert client.capabilities()["schema_version"] == ("limen.conduct_capabilities.v1")
    assert captured["request"].get_header("User-agent") == ("limen-conduct-client/1")
    assert captured["timeout"] == 17


# --------------------------------------------------------------------------------------------
# A spent keeper storage plan is its own condition — not a bug, not a transient fault.
#
# Measured 2026-08-07: POST /api/conduct/sessions began answering
#   500 {"detail": "Exceeded allowed rows written in Durable Objects free tier."}
# ``_register_relay_session`` is on EVERY relay write path, so this single wall blocked the
# canonical-heal rung, dispatch receipts, and board publication at once. No retry helps: the
# resolution is a spend decision, homed as lever L-CLOUDFLARE-DO-QUOTA.
#
# These pin BOTH directions, and the negative cases matter more than the positive one: the
# detection reads keeper PROSE — a narrow, documented exemption from the estate's
# classify-on-status rule, taken because a Cloudflare storage refusal carries no other signal —
# so it must never swallow an ordinary 500 and relabel a real defect as "waiting on the owner".
# --------------------------------------------------------------------------------------------

QUOTA_DETAIL = '{\n  "detail": "Exceeded allowed rows written in Durable Objects free tier."\n}'


def _client_raising(monkeypatch, code: int, detail: str) -> HttpConductClient:
    def fake_urlopen(request, *, timeout):
        raise urllib.error.HTTPError(request.full_url, code, "err", {}, io.BytesIO(detail.encode("utf-8")))

    monkeypatch.setattr("limen.conduct.client.urllib.request.urlopen", fake_urlopen)
    return HttpConductClient("https://limen-runtime.example", "fixture-token")


def test_storage_quota_refusal_is_its_own_condition(monkeypatch):
    client = _client_raising(monkeypatch, 500, QUOTA_DETAIL)
    with pytest.raises(BrokerQuotaExhausted) as excinfo:
        client.capabilities()
    assert excinfo.value.status == 500
    assert "Durable Objects free tier" in str(excinfo.value)


def test_a_plain_500_stays_a_plain_error(monkeypatch):
    """The load-bearing half: a real keeper defect must not be reported as an owner-gated spend."""
    client = _client_raising(monkeypatch, 500, '{"detail": "TypeError: cannot read property of undefined"}')
    with pytest.raises(ConductError) as excinfo:
        client.capabilities()
    assert not isinstance(excinfo.value, BrokerQuotaExhausted)


def test_a_throttle_without_a_named_ceiling_is_not_a_quota_wall(monkeypatch):
    client = _client_raising(monkeypatch, 429, '{"detail": "Too many requests"}')
    with pytest.raises(ConductError) as excinfo:
        client.capabilities()
    assert not isinstance(excinfo.value, BrokerQuotaExhausted)


def test_a_throttle_that_names_the_ceiling_is_a_quota_wall(monkeypatch):
    """A plan ceiling can surface as a throttle; the body naming it is what decides."""
    client = _client_raising(monkeypatch, 429, '{"detail": "Exceeded allowed rows written, upgrade your plan"}')
    with pytest.raises(BrokerQuotaExhausted):
        client.capabilities()


def test_conflict_precedence_is_unchanged(monkeypatch):
    """409 is classified before the quota sniff runs — status still outranks prose."""
    client = _client_raising(monkeypatch, 409, '{"detail": "Exceeded allowed rows written"}')
    with pytest.raises(ConductConflict) as excinfo:
        client.capabilities()
    assert not isinstance(excinfo.value, BrokerQuotaExhausted)


def test_quota_exhaustion_is_still_a_conduct_error():
    """Every existing `except ConductError` catcher keeps working unchanged."""
    assert issubclass(BrokerQuotaExhausted, ConductError)


def test_the_quota_condition_names_a_live_owner_not_the_retired_lever():
    """The rungs must cite an owner a reader can act on.

    This test used to assert that L-CLOUDFLARE-DO-QUOTA exists in his-hand-levers.json,
    which it still does — as a RETIRED entry. The lever was retired 2026-08-10 once the
    recurrence proved the active defect is Limen's own write amplification (issue #2054),
    and that issue states in terms that no Cloudflare support case, billing change, plan
    change, credential mint or operator action is required. So "the lever exists" stopped
    being the property worth pinning: a rung citing it sends the reader to a human action
    its owner explicitly ruled out. Pin the live citation instead, and pin that the retired
    id is not presented as the owner.
    """
    registry = json.loads((ROOT / "his-hand-levers.json").read_text())
    lever = next((lv for lv in registry["levers"] if lv.get("id") == "L-CLOUDFLARE-DO-QUOTA"), None)
    if lever is not None:
        assert str(lever.get("status", "")).strip().lower() in {"retired", "discharged", "done", "closed"}, (
            "L-CLOUDFLARE-DO-QUOTA is retired; if it is reopened, revisit what the rungs cite"
        )

    for organ in ("scripts/heal-board.py", "scripts/self-heal.py", "scripts/heal-dispatch.py"):
        text = (ROOT / organ).read_text(encoding="utf-8")
        assert 'QUOTA_OWNER = "organvm/limen#2054' in text, f"{organ} must cite the live engineering owner"
        assert "QUOTA_LEVER" not in text, f"{organ} must not resurrect the retired lever constant"
