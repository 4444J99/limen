"""census is the single vendor register; the historical lists are derived views of it.

These tests do two jobs:
  1. REGRESSION-LOCK the derived `capacity` structures to their frozen historical values, so the
     convergence provably changed no behavior (and can never silently drift from the census).
  2. DRIFT-GUARD the copies that census does not yet own outright (`dispatch._LANE_CASCADE`) against
     the census projection, so the two cannot diverge again while the rewire is incremental.
"""

from __future__ import annotations

from limen import capacity, census

# ── Frozen historical values (what these structures were BEFORE census owned them). ────────────
_PAID_AGENT_ORDER = (
    "codex",
    "claude",
    "opencode",
    "agy",
    "gemini",
    "ollama",
    "jules",
    "copilot",
    "warp",
    "oz",
    "github_actions",
)
_AGENT_ALIASES = {
    "actions": "github_actions",
    "gha": "github_actions",
    "github-actions": "github_actions",
    "antigravity": "agy",
}
_LOCAL_CHECKOUT_AGENTS = frozenset({"codex", "claude", "opencode", "agy", "gemini", "ollama"})
_ISSUE_ASSIGNMENT_AGENTS = frozenset({"copilot"})
_DEFAULT_BINARIES = {
    "codex": "codex",
    "claude": "claude",
    "opencode": "opencode",
    "agy": "agy",
    "gemini": "gemini",
    "ollama": "ollama",
    "jules": "jules",
    "copilot": "gh",
    "warp": "warp",
    "oz": "oz",
    "github_actions": "gh",
}
_KINDS = {
    "codex": "local-cli",
    "claude": "local-cli",
    "opencode": "local-cli",
    "agy": "local-cli",
    "gemini": "local-cli",
    "ollama": "local-cli",
    "jules": "cloud-cli",
    "copilot": "github-issue",
    "warp": "paid-service",
    "oz": "paid-service",
    "github_actions": "github-actions",
}


def test_capacity_structures_derive_from_census_unchanged():
    """The convergence preserved every value AND type of the six derived structures."""
    assert capacity.PAID_AGENT_ORDER == _PAID_AGENT_ORDER
    assert isinstance(capacity.PAID_AGENT_ORDER, tuple)
    assert capacity.AGENT_ALIASES == _AGENT_ALIASES
    assert capacity.LOCAL_CHECKOUT_AGENTS == _LOCAL_CHECKOUT_AGENTS
    assert isinstance(capacity.LOCAL_CHECKOUT_AGENTS, frozenset)
    assert capacity.ISSUE_ASSIGNMENT_AGENTS == _ISSUE_ASSIGNMENT_AGENTS
    assert capacity._DEFAULT_BINARIES == _DEFAULT_BINARIES
    assert capacity._KINDS == _KINDS


def test_census_projections_match_the_historical_values():
    """The census accessors are the single source; assert each projection directly too."""
    assert census.paid_agent_order() == _PAID_AGENT_ORDER
    assert census.agent_aliases() == _AGENT_ALIASES
    assert census.local_checkout_agents() == _LOCAL_CHECKOUT_AGENTS
    assert census.issue_assignment_agents() == _ISSUE_ASSIGNMENT_AGENTS
    assert census.default_binaries() == _DEFAULT_BINARIES
    assert census.kinds() == _KINDS


def test_vendor_tiering_is_derived():
    """Per-vendor model-choice ownership is a projection of Vendor.tiering (Increment-1).

    Claude routes through its tier authority; OpenCode uses live capability selection; Warp/Oz
    delegate underlying model choice to provider Auto. The closed set catches unowned strategies.
    """
    t = census.tiering()
    assert t["claude"] == "model_selection"
    assert t["codex"] == "dispatch_adhoc"
    assert t["opencode"] == "provider_selection"
    assert t["warp"] == "provider_auto"
    assert t["oz"] == "provider_auto"
    for name in ("agy", "gemini", "ollama", "jules", "copilot", "github_actions"):
        assert t[name] == "none", f"{name} should not own a model-choice layer"
    # every vendor is projected, exactly once.
    assert set(t) == set(census.paid_agent_order())
    # closed sentinel set — no unmodeled tier value may leak in.
    assert set(t.values()) == {
        "model_selection",
        "dispatch_adhoc",
        "provider_selection",
        "provider_auto",
        "none",
    }


def test_capacity_canonical_agent_still_resolves_aliases():
    """capacity.canonical_agent reads AGENT_ALIASES; the derivation must keep it working."""
    assert capacity.canonical_agent("antigravity") == "agy"
    assert capacity.canonical_agent("gha") == "github_actions"
    assert capacity.canonical_agent("codex") == "codex"
    assert capacity.canonical_agent("") == ""
    assert census.canonical("antigravity") == "agy"


def test_lane_cascade_drift_guard_against_dispatch():
    """dispatch._LANE_CASCADE now DERIVES from census.lane_cascade(); assert they stay equal."""
    from limen import dispatch

    assert census.lane_cascade() == list(dispatch._LANE_CASCADE)
    # Every lane in the cascade is a known, canonical vendor.
    known = set(census.paid_agent_order())
    assert set(census.lane_cascade()) <= known


def test_every_vendor_record_is_well_formed():
    """Structural invariants over the register itself."""
    names = [v.name for v in census.VENDORS]
    assert len(names) == len(set(names)), "duplicate vendor names"
    assert tuple(names) == _PAID_AGENT_ORDER, "register order is load-bearing"
    for v in census.VENDORS:
        assert census.by_name(v.name) is v
        # aliases resolve back to this vendor
        for alias in v.aliases:
            assert census.canonical(alias) == v.name
        # budget/status are always present (never a bare None record)
        assert v.budget is not None and v.status is not None


def test_gemini_status_is_homed_in_the_register():
    """The umbrella's whole point: Gemini's two breakages are DATA, not tribal knowledge."""
    gem = census.by_name("gemini")
    assert gem is not None
    assert gem.status.available is False
    # (1) the sunset free OAuth client is recorded as a dead path — nothing may route into it.
    assert "oauth_code_assist" in gem.status.deprecated_paths
    assert "gemini" in census.deprecated_paths()
    # (2) the suspended API-key project is recorded, with the lever that owns the human atom.
    assert "CONSUMER_SUSPENDED" in gem.status.note
    assert gem.status.lever == "L-FLEET-CAPACITY"
    # live auth is the API key (not the dead OAuth path), and creds-hydrate's op:// source is homed.
    assert gem.auth_mode == "api_key"
    assert gem.cred_ref == "op://Personal/Gemini API Key/credential"
    # gemini surfaces in the unavailable roll-up.
    assert "gemini" in census.unavailable()


def test_healthy_fleet_has_no_other_dead_paths():
    """Only gemini is currently dark; guard against an accidental deprecation slipping in."""
    assert set(census.deprecated_paths()) == {"gemini"}
    assert set(census.unavailable()) == {"gemini"}


def _load_usage_telemetry_module():
    """Import scripts/usage-telemetry.py (hyphenated filename -> load by path) so its census
    wiring can be inspected. Module-level code is side-effect-free at import (no file writes)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "usage-telemetry.py"
    spec = importlib.util.spec_from_file_location("usage_telemetry_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_usage_telemetry_limits_derive_from_census():
    """Convergence roadmap item: usage-telemetry._DEFAULT_LIMITS DERIVES from census.budgets().

    The vendor rows are a projection of the census register (filter: a real metering window,
    Budget.window != "none" == the dispatchable metered lanes). The drift-guarded fallback literal
    must equal that projection byte-for-byte, so it can never silently diverge from the umbrella.
    """
    ut = _load_usage_telemetry_module()
    expected = {name: ut._budget_row(b) for name, b in census.budgets().items() if b.window != "none"}
    # exactly the metered lanes — no non-metered (window == "none") lane leaks in.
    assert set(expected) == {"codex", "claude", "opencode", "agy", "gemini", "jules"}
    # the hand-typed fallback IS the census projection (drift guard).
    assert ut._FALLBACK_VENDOR_LIMITS == expected
    # the live derivation (limen importable) equals the fallback.
    assert ut._census_vendor_limits() == expected
    # _DEFAULT_LIMITS = derived vendor rows + the two app-plane rows (which have no Vendor record).
    assert set(ut._DEFAULT_LIMITS) == set(expected) | {"chatgpt-app", "claude-app"}
    # values preserved through the refactor (the swap changed nothing the consumers read).
    for name, row in expected.items():
        assert ut._DEFAULT_LIMITS[name] == row


def test_route_vendor_health_derives_lane_set_from_census():
    """scripts/route.py _vendor_health (the capacity_census fallback) derives its lane set from
    census.lane_cascade(), so the fallback can never list a different vendor set than the main path."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "route.py"
    spec = importlib.util.spec_from_file_location("route_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # pragma: no cover - script-only deps absent in a minimal env
        import pytest

        pytest.skip(f"route.py not importable in this environment: {exc}")
    health = mod._vendor_health()
    assert set(health) == set(census.lane_cascade())


def test_ianva_agent_keys_reconcile_with_census():
    """Every dispatchable ianva MCP target is a canonical census vendor (guards naming drift, e.g.
    'antigravity' vs 'agy'). 'cline' is the one MCP-only client that is not a dispatch lane."""
    import pytest

    agents_mod = pytest.importorskip("ianva.agents")
    census_names = set(census.paid_agent_order())
    non_census_mcp_targets = {"cline"}  # a valid MCP client, not a limen dispatch lane
    for agent in agents_mod.AGENTS:
        if agent.key in non_census_mcp_targets:
            continue
        assert agent.key in census_names, f"ianva agent {agent.key!r} is not a canonical census vendor"


def test_agy_meter_is_honest_no_readable_source():
    """agy (Antigravity) persists NO local usage — /usage is live-fetched from Google OAuth only —
    so its census meter must NOT fake a measured number. It stays a calibrated dispatch-count board
    cap, the same honest posture as gemini (also no readable vendor meter). Guards against a future
    'graduate agy to a measured meter' edit that invents a number agy never actually exposes."""
    agy = census.by_name("agy")
    gem = census.by_name("gemini")
    assert agy is not None and gem is not None
    # no readable meter → dispatch_count, the same honest marker gemini carries (NOT a real meter).
    assert agy.meter == "dispatch_count" == gem.meter
    assert agy.meter != "vendor_ratelimit"  # must not falsely claim codex-style real rate-limit data
    # trust is calibrated (an operator board cap), never "measured" (which would fake a real number).
    assert agy.budget.trust == "calibrated"
    assert agy.budget.trust != "measured"
    # it still carries a concrete board cap (not None) so the pacing controller has a number to use.
    assert agy.budget.limit == 100
