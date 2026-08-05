"""Tests for OBSERVATORY P3-CAPTURE — live-homepage capture (surface.capture_site + collect wiring).

Hermetic: ``fetch`` is injected (no network), and the ``gh`` boundary + the capture flag are
monkeypatched. Asserts determinism, fail-open, and the ships-dark default (off → no site_* keys,
byte-identical snapshots).
"""

from __future__ import annotations

from limen.observatory import collect, gh, surface

HOMEPAGE_HTML = """<!doctype html>
<html><head>
<title>Ship reports in one command</title>
<meta name="description" content="Generate a report instantly, so you can move on.">
</head><body>
<h1>Ship reports in one command</h1>
<img src="/demo.gif" alt="demo">
<a href="/start" class="btn">Get started</a>
</body></html>"""


def _fetch_ok(url, timeout):
    return HOMEPAGE_HTML, 200, None


def _fetch_blocked(url, timeout):
    return None, 403, "http 403"


def _fetch_dead(url, timeout):
    return None, None, "timeout"


# ---------------------------------------------------------------- capture_site (pure given fetch)
def test_capture_extracts_first_impression_features():
    r = surface.capture_site("https://example.com", fetch=_fetch_ok)
    assert r["site_reachable"] is True
    assert r["site_demo_above_fold"] is True  # <img> in the head region
    assert r["site_cta_visible"] is True  # "Get started"
    assert r["site_names_outcome"] is True  # "in one command" / "instantly"
    assert r["site_headline"] == "Ship reports in one command"


def test_capture_is_deterministic():
    a = surface.capture_site("https://example.com", fetch=_fetch_ok)
    b = surface.capture_site("https://example.com", fetch=_fetch_ok)
    assert a == b


def test_capture_fail_open_on_blocked_dead_and_nonhttp():
    for r in (
        surface.capture_site("https://x.com", fetch=_fetch_blocked),
        surface.capture_site("https://x.com", fetch=_fetch_dead),
        surface.capture_site("ftp://x.com", fetch=_fetch_ok),
        surface.capture_site("not-a-url", fetch=_fetch_ok),
    ):
        assert r["site_reachable"] is False
        assert r["site_demo_above_fold"] is False
        assert r["site_cta_visible"] is False
        assert r["site_names_outcome"] is False
        assert r["site_headline"] is None


def test_site_features_are_scoreable_binary_features():
    assert "site_demo_above_fold" in surface.BINARY_FEATURES
    assert "site_cta_visible" in surface.BINARY_FEATURES


def test_extract_stays_pure_and_deterministic():
    md = "# Tool\n\nFor developers, so you can ship in one command.\n\n![demo](x.gif)\n"
    # capture must not have leaked into the pure extractor
    assert surface.extract(md, {}) == surface.extract(md, {})
    assert "site_reachable" not in surface.extract(md, {})


# ---------------------------------------------------------------- collect.snapshot wiring (gated)
def _mock_gh(monkeypatch, homepage="https://ex.com"):
    monkeypatch.setattr(
        gh,
        "repo",
        lambda name, tok: {
            "full_name": name,
            "owner": {"login": "o", "type": "User"},
            "topics": [],
            "language": "Python",
            "homepage": homepage,
            "created_at": "2026-01-01T00:00:00Z",
            "stargazers_count": 100,
        },
    )
    monkeypatch.setattr(gh, "releases", lambda name, tok: [])
    monkeypatch.setattr(gh, "readme_markdown", lambda name, tok: "# X\n\nA tool.")


def test_snapshot_merges_site_features_when_armed(monkeypatch):
    _mock_gh(monkeypatch)
    monkeypatch.setattr(
        collect.config, "get", lambda key, default=None, cast=None: 1 if key == "OBSERVATORY_CAPTURE" else default
    )
    monkeypatch.setattr(
        surface,
        "capture_site",
        lambda url, **kw: {
            "site_reachable": True,
            "site_headline": "H",
            "site_demo_above_fold": True,
            "site_names_outcome": True,
            "site_cta_visible": True,
        },
    )
    snap = collect.snapshot("o/x", None, role="winner")
    assert snap is not None
    assert snap["surface"]["site_demo_above_fold"] is True
    assert snap["surface"]["site_cta_visible"] is True


def test_snapshot_has_no_site_features_when_off(monkeypatch):
    _mock_gh(monkeypatch)
    monkeypatch.setattr(
        collect.config, "get", lambda key, default=None, cast=None: 0 if key == "OBSERVATORY_CAPTURE" else default
    )

    def _boom(*a, **k):
        raise AssertionError("capture_site must not run when OBSERVATORY_CAPTURE is off")

    monkeypatch.setattr(surface, "capture_site", _boom)
    snap = collect.snapshot("o/x", None, role="winner")
    assert snap is not None
    assert "site_demo_above_fold" not in snap["surface"]
    assert "site_reachable" not in snap["surface"]
