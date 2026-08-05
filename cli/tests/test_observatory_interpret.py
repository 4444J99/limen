"""Tests for OBSERVATORY P2-LLM — evidence-constrained interpretation (interpret.py + brief attach).

Hermetic: ``OBSERVATORY_LLM`` is monkeypatched and the LLM ``invoke`` is injected (no subprocess,
no network). Asserts the ships-dark default (off → no interpretation, invoke never reached) and
fail-open in every direction.
"""

from __future__ import annotations

import json

from limen.observatory import brief, config, interpret


def _brief_core():
    return {
        "schema": "limen.observatory.brief.v1",
        "hero": "o/hero",
        "mechanisms": [{"mechanism": "names_outcome", "priority": 7.5, "winner": "o/win"}],
        "confounders": [],
        "internal_gaps": 1,
        "external_gaps": 0,
        "experiment": {"change": "Add names_outcome to the hero's first screen."},
    }


def _arm(monkeypatch, on=True):
    monkeypatch.setattr(
        interpret.config,
        "get",
        lambda key, default=None, cast=None: (1 if on else 0) if key == "OBSERVATORY_LLM" else default,
    )


def test_interpret_off_is_inert(monkeypatch):
    _arm(monkeypatch, on=False)
    called = []
    r = interpret.interpret(_brief_core(), invoke=lambda p, m, t: (called.append(1), ("x", None))[1])
    assert r["interpretation"] is None
    assert r["reason"] == "off"
    assert not called  # invoke is never reached when the gate is off


def test_interpret_attaches_and_is_evidence_constrained(monkeypatch):
    _arm(monkeypatch)
    seen = {}

    def _invoke(prompt, model, timeout):
        seen["prompt"] = prompt
        seen["model"] = model
        return "names_outcome is a legibility win because it promises a concrete result.", None

    r = interpret.interpret(_brief_core(), invoke=_invoke)
    assert r["interpretation"].startswith("names_outcome is a legibility win")
    assert "names_outcome" in seen["prompt"] and "o/hero" in seen["prompt"]  # only observed evidence
    assert seen["model"]  # a model was resolved via model_selection


def test_interpret_fail_open_on_error_and_empty(monkeypatch):
    _arm(monkeypatch)
    for inv in (
        lambda p, m, t: (None, "boom"),
        lambda p, m, t: ("", None),
        lambda p, m, t: ("   ", None),
    ):
        assert interpret.interpret(_brief_core(), invoke=inv)["interpretation"] is None


def test_brief_run_attaches_interpretation_when_armed(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    (tmp_path / "logs" / "observatory").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(interpret, "interpret", lambda b, **k: {"interpretation": "INSIGHT", "model": "opus"})
    brief.run(apply=False)
    doc = json.loads((tmp_path / "logs" / "observatory" / "brief-latest.json").read_text())
    assert doc.get("interpretation") == "INSIGHT"
    assert doc.get("interpretation_model") == "opus"


def test_brief_run_has_no_interpretation_when_off(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "repo_root", lambda: tmp_path)
    (tmp_path / "logs" / "observatory").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        interpret.config,
        "get",
        lambda key, default=None, cast=None: 0 if key == "OBSERVATORY_LLM" else default,
    )
    brief.run(apply=False)
    doc = json.loads((tmp_path / "logs" / "observatory" / "brief-latest.json").read_text())
    assert "interpretation" not in doc
