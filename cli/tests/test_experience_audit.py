"""Tests for scripts/experience-audit.py — the visitor-experience predicate organ.

Hermetic and NETWORK-FREE: the surface list is derived from a tmp links-registry fixture and a tmp
overlay; the probe tier is exercised via build_artifact() on injected probe results (no requests, no
playwright). The script resolves artifacts from its own tree, so artifact-writing tests monkeypatch
AUDIT/HISTORY/SHOTS onto tmp paths.

Covers: registry derivation (kind filter, funding drop), URL dedupe, id slugging + collision
disambiguation, budget-breach exit codes (a tiny ttfb budget -> --surface check exit 1 naming the
surface), --doctor failures (unresolvable overlay key, bad verdict, secret/URL in overlay), history
append, and the http-tier artifact shape.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "experience-audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("experience_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


def _registry(links: list[dict]) -> dict:
    return {"version": 1, "links": links}


def _write_registry(path: Path, links: list[dict]) -> None:
    path.write_text(json.dumps(_registry(links)), encoding="utf-8")


def _write_overlay(path: Path, overlay: dict) -> None:
    path.write_text(json.dumps(overlay), encoding="utf-8")


# --------------------------------------------------------------------------- derivation


def test_derive_keeps_only_kept_kinds_and_drops_funding():
    links = [
        {"kind": "deployment", "label": "Portfolio", "url": "https://a.example/"},
        {"kind": "page", "label": "Docs", "url": "https://b.example/docs"},
        {"kind": "custom-domain", "label": "Home", "url": "https://c.example"},
        {"kind": "funding", "label": "Sponsors", "url": "https://d.example/sponsors"},
    ]
    surfaces = mod.derive_surfaces_from_links(links, {})
    kinds = {s["kind"] for s in surfaces}
    assert kinds == {"deployment", "page", "custom-domain"}
    assert all("sponsors" not in s["url"] for s in surfaces)
    assert len(surfaces) == 3


def test_derive_dedupes_by_normalized_url(tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(
        reg,
        [
            {"kind": "deployment", "label": "One", "url": "https://a.example/path/"},
            {"kind": "page", "label": "Two", "url": "https://A.EXAMPLE/path"},  # same after normalize
            {"kind": "page", "label": "Three", "url": "https://a.example/other"},
        ],
    )
    surfaces = mod.derive_surfaces(reg, {})
    urls = sorted(s["url"] for s in surfaces)
    # first-seen wins; the second (dup) is dropped -> 2 surfaces
    assert len(surfaces) == 2
    assert "https://a.example/path/" in urls
    assert "https://a.example/other" in urls


def test_id_slugging_and_collision_disambiguation():
    links = [
        {"kind": "deployment", "label": "My Cool Site!", "url": "https://x.example/1"},
        {"kind": "page", "label": "My Cool Site!", "url": "https://x.example/2"},  # same slug, diff url
    ]
    surfaces = mod.derive_surfaces_from_links(links, {})
    ids = [s["id"] for s in surfaces]
    assert ids[0] == "my-cool-site"
    assert ids[1] == "my-cool-site-1"  # deterministic disambiguation


def test_id_falls_back_to_hostname_when_label_empty():
    links = [{"kind": "deployment", "label": "", "url": "https://fallback.example/x"}]
    surfaces = mod.derive_surfaces_from_links(links, {})
    assert surfaces[0]["id"] == "fallback-example"


def test_overlay_skip_and_budget_override():
    links = [
        {"kind": "deployment", "label": "Keep", "url": "https://k.example/"},
        {"kind": "page", "label": "Drop", "url": "https://d.example/"},
    ]
    overlay = {
        "defaults": {"ttfb_ms": 1500, "max_kb": 1500, "max_requests": 75},
        "surfaces": {"keep": {"ttfb_ms": 200}},
        "skip": {"drop": {}},
    }
    surfaces = mod.derive_surfaces_from_links(links, overlay)
    assert len(surfaces) == 1
    assert surfaces[0]["id"] == "keep"
    assert surfaces[0]["ttfb_ms"] == 200
    assert surfaces[0]["max_kb"] == 1500


# --------------------------------------------------------------------------- scoring / artifact


def _http_result(sid, url, *, status=200, ttfb=100, kb=10.0, title="Hi"):
    return {
        "tier": "http",
        "id": sid,
        "url": url,
        "status": status,
        "ttfb_ms": ttfb,
        "transfer_kb": kb,
        "title": title,
        "largest_asset": {"path": url, "kb": kb},
    }


def test_http_tier_artifact_shape_and_pass():
    surfaces = [
        {
            "id": "ok",
            "url": "https://ok.example/",
            "kind": "deployment",
            "ttfb_ms": 1500,
            "max_kb": 1500,
            "max_requests": 75,
            "expected_title": None,
        },
    ]
    results = [_http_result("ok", "https://ok.example/")]
    body = mod.build_artifact(surfaces, "http", results)
    assert body["schema"] == "limen.experience_audit.v1"
    assert body["tier"] == "http"
    assert body["audited"] == 1
    assert body["passing"] == 1
    assert body["failing"] == []
    entry = body["surfaces"]["ok"]
    assert entry["pass"] is True
    # http tier leaves X4/X5/X6 unknown (None), never fails on them
    assert entry["rungs"]["X4"] is None
    assert entry["rungs"]["X5"] is None
    assert entry["rungs"]["X6"] is None
    assert entry["rungs"]["X1"] is True
    assert "url" in entry and "largest_asset" in entry
    assert body["p50_ttfb_ms"] == 100


def test_tiny_ttfb_budget_breaches_x2_and_fails():
    surfaces = [
        {
            "id": "slow",
            "url": "https://slow.example/",
            "kind": "deployment",
            "ttfb_ms": 1,
            "max_kb": 1500,
            "max_requests": 75,
            "expected_title": None,
        },
    ]
    results = [_http_result("slow", "https://slow.example/", ttfb=999)]
    body = mod.build_artifact(surfaces, "http", results)
    assert body["failing"] == ["slow"]
    assert body["surfaces"]["slow"]["rungs"]["X2"] is False


def test_expected_title_mismatch_fails_x7():
    surfaces = [
        {
            "id": "titled",
            "url": "https://t.example/",
            "kind": "page",
            "ttfb_ms": 1500,
            "max_kb": 1500,
            "max_requests": 75,
            "expected_title": "Correct Title",
        },
    ]
    results = [_http_result("titled", "https://t.example/", title="Wrong Title")]
    body = mod.build_artifact(surfaces, "http", results)
    assert body["failing"] == ["titled"]
    assert body["surfaces"]["titled"]["rungs"]["X7"] is False


def test_playwright_tier_over_budget_requests_fails_x4():
    surfaces = [
        {
            "id": "heavy",
            "url": "https://h.example/",
            "kind": "deployment",
            "ttfb_ms": 1500,
            "max_kb": 1500,
            "max_requests": 5,
            "expected_title": None,
        },
    ]
    results = [
        {
            "tier": "playwright",
            "id": "heavy",
            "url": "https://h.example/",
            "status": 200,
            "ttfb_ms": 100,
            "transfer_kb": 10.0,
            "requests": 40,
            "broken_images": 0,
            "console_errors": 0,
            "title": "Hi",
        }
    ]
    body = mod.build_artifact(surfaces, "playwright", results)
    assert body["surfaces"]["heavy"]["rungs"]["X4"] is False
    assert body["failing"] == ["heavy"]


# --------------------------------------------------------------------------- sweep + check + history


def _patch_artifact_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "AUDIT", tmp_path / "experience-audit.json")
    monkeypatch.setattr(mod, "HISTORY", tmp_path / "experience" / "history.jsonl")
    monkeypatch.setattr(mod, "SHOTS_DIR", tmp_path / "experience" / "shots")
    monkeypatch.setattr(mod, "ROOT", tmp_path)


def test_sweep_writes_artifact_and_appends_history(monkeypatch, tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(
        reg,
        [
            {"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"},
            {"kind": "page", "label": "Beta", "url": "https://beta.example/b"},
        ],
    )
    overlay_file = tmp_path / "overlay.json"
    _write_overlay(overlay_file, {"defaults": {"ttfb_ms": 1500, "max_kb": 1500, "max_requests": 75}})

    # force http tier (no playwright) and inject a canned http probe (no network)
    monkeypatch.setattr(mod, "_probe_playwright", lambda surfaces, timeout: None)
    monkeypatch.setattr(
        mod,
        "_probe_http",
        lambda surface, timeout: _http_result(surface["id"], surface["url"]),
    )
    _patch_artifact_paths(monkeypatch, tmp_path)

    rc = mod.cmd_sweep(str(overlay_file), str(reg))
    assert rc == 0
    body = json.loads((tmp_path / "experience-audit.json").read_text())
    assert body["audited"] == 2
    assert body["tier"] == "http"
    hist = (tmp_path / "experience" / "history.jsonl").read_text().strip().splitlines()
    assert len(hist) == 1
    line = json.loads(hist[0])
    assert set(line) == {"ts", "tier", "audited", "passing", "failing_ids", "p50_ttfb_ms", "max_transfer_kb"}
    # a second sweep appends a second counts-only line
    mod.cmd_sweep(str(overlay_file), str(reg))
    hist2 = (tmp_path / "experience" / "history.jsonl").read_text().strip().splitlines()
    assert len(hist2) == 2


def test_surface_check_exit_codes(monkeypatch, tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(
        reg,
        [
            {"kind": "deployment", "label": "Fast", "url": "https://fast.example/"},
            {"kind": "page", "label": "Slow", "url": "https://slow.example/"},
        ],
    )
    overlay_file = tmp_path / "overlay.json"
    _write_overlay(
        overlay_file,
        {
            "defaults": {"ttfb_ms": 1500, "max_kb": 1500, "max_requests": 75},
            "surfaces": {"slow": {"ttfb_ms": 1}},
        },
    )
    monkeypatch.setattr(mod, "_probe_playwright", lambda surfaces, timeout: None)
    monkeypatch.setattr(
        mod,
        "_probe_http",
        lambda surface, timeout: _http_result(surface["id"], surface["url"], ttfb=999),
    )
    _patch_artifact_paths(monkeypatch, tmp_path)
    mod.cmd_sweep(str(overlay_file), str(reg))

    # fast surface (999ms vs 1500 budget) passes -> exit 0
    assert mod.cmd_check_surface("fast") == 0
    # slow surface (999ms vs 1ms budget) fails X2 -> exit 1
    assert mod.cmd_check_surface("slow") == 1
    # a whole-estate check is non-zero when any surface fails
    assert mod.cmd_check() == 1


# --------------------------------------------------------------------------- doctor


def test_doctor_clean_overlay_passes(tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(reg, [{"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"}])
    overlay_file = tmp_path / "overlay.json"
    _write_overlay(
        overlay_file,
        {
            "schema_version": 1,
            "defaults": {"ttfb_ms": 1500, "max_kb": 1500, "max_requests": 75},
            "surfaces": {"alpha": {"ttfb_ms": 500}},
            "skip": {},
        },
    )
    assert mod.cmd_doctor(str(overlay_file), str(reg)) == 0


def test_doctor_fails_on_unresolvable_overlay_key(tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(reg, [{"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"}])
    overlay_file = tmp_path / "overlay.json"
    _write_overlay(
        overlay_file,
        {
            "defaults": {"ttfb_ms": 1500, "max_kb": 1500, "max_requests": 75},
            "surfaces": {"does-not-exist": {"ttfb_ms": 500}},
        },
    )
    assert mod.cmd_doctor(str(overlay_file), str(reg)) == 1


def test_doctor_fails_on_url_in_overlay(tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(reg, [{"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"}])
    overlay_file = tmp_path / "overlay.json"
    # a URL smuggled into the overlay (banned — URLs are owned by the registry)
    overlay_file.write_text(json.dumps({"defaults": {}, "surfaces": {}, "note": "see https://sneaky.example"}))
    assert mod.cmd_doctor(str(overlay_file), str(reg)) == 1


def test_doctor_fails_on_secret_in_overlay(tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(reg, [{"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"}])
    overlay_file = tmp_path / "overlay.json"
    overlay_file.write_text(json.dumps({"defaults": {}, "surfaces": {}, "api_key": "xyz"}))
    assert mod.cmd_doctor(str(overlay_file), str(reg)) == 1


def test_doctor_fails_on_nonpositive_budget(tmp_path):
    reg = tmp_path / "links-registry.json"
    _write_registry(reg, [{"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"}])
    overlay_file = tmp_path / "overlay.json"
    _write_overlay(overlay_file, {"defaults": {"ttfb_ms": 0, "max_kb": 1500, "max_requests": 75}})
    assert mod.cmd_doctor(str(overlay_file), str(reg)) == 1


def test_doctor_fails_on_bad_verdict(tmp_path, monkeypatch):
    reg = tmp_path / "links-registry.json"
    _write_registry(reg, [{"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"}])
    overlay_file = tmp_path / "overlay.json"
    _write_overlay(overlay_file, {"defaults": {"ttfb_ms": 1500, "max_kb": 1500, "max_requests": 75}})
    judgments = tmp_path / "experience-judgments.yaml"
    judgments.write_text(
        "schema_version: 1\n"
        "judgments:\n"
        "  alpha:\n"
        "    - verdict: maybe\n"  # invalid verdict
        "      scores: {layout: 3}\n"
    )
    monkeypatch.setattr(mod, "JUDGMENTS", judgments)
    assert mod.cmd_doctor(str(overlay_file), str(reg)) == 1


def test_doctor_fails_on_out_of_range_score(tmp_path, monkeypatch):
    reg = tmp_path / "links-registry.json"
    _write_registry(reg, [{"kind": "deployment", "label": "Alpha", "url": "https://alpha.example/"}])
    overlay_file = tmp_path / "overlay.json"
    _write_overlay(overlay_file, {"defaults": {"ttfb_ms": 1500, "max_kb": 1500, "max_requests": 75}})
    judgments = tmp_path / "experience-judgments.yaml"
    judgments.write_text(
        "schema_version: 1\njudgments:\n  alpha:\n    - verdict: pass\n      scores: {layout: 9}\n"  # out of 0-5 range
    )
    monkeypatch.setattr(mod, "JUDGMENTS", judgments)
    assert mod.cmd_doctor(str(overlay_file), str(reg)) == 1
