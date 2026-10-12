from limen.operating_system_health import packets


def test_outside_host_probe_uses_supported_route_and_installed_visual_receipt(tmp_path, monkeypatch):
    import json
    from datetime import UTC, datetime
    from types import SimpleNamespace
    from limen import operating_system_health as health

    home = tmp_path / "home"
    root = tmp_path / "divergent-checkout"
    receipt = home / ".local/share/limen/current/source/docs/reviews/native-visual-20261012.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "observed_at": datetime.now(UTC).isoformat(),
                "native_capture": True,
                "external_gates": ["platform_policy"],
            }
        )
    )
    monkeypatch.setattr(health.RuntimePool, "observe", lambda *args: {"allowed": True})
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        # The actual native predicate rejects calls outside its lifetime context.
        okay = argv[0] == "chezmoi" or argv[1:3] == ["ensure", "--"]
        return SimpleNamespace(returncode=0 if okay else 1, stdout=b"")

    monkeypatch.setattr(health.subprocess, "run", run)
    findings = health.observations(root, home)
    assert findings == [("native_visual_platform_policy", "4444J99/domus-genoma", False, "platform_policy")]
    assert calls[-1] == [
        str(home / ".local/bin/domus-agent-host"),
        "ensure",
        "--",
        str(home / "Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost"),
        "verify-lifetime",
    ]


def test_owner_routing_dedup_bounded_retries_and_resolution():
    findings = [("shared_pool_pressure", "4444J99/limen", True, "stale")] * 2
    previous = {}
    for _ in range(4):
        grouped, previous = packets(findings, previous, "2026-10-12T19:00:00Z")
    signals = grouped["4444J99/limen"]["friction_signals"]
    assert len(signals) == 1
    assert signals[0]["healable"] is False
    findings[0] = ("shared_pool_pressure", "4444J99/limen", True, "changed")
    grouped, _ = packets(findings[:1], previous, "2026-10-12T19:00:00Z")
    assert grouped["4444J99/limen"]["friction_signals"][0]["healable"]
    grouped, previous = packets([], previous, "2026-10-12T19:00:00Z")
    assert previous == {}
    assert all(not packet["friction_signals"] for packet in grouped.values())


def test_external_visual_guard_is_never_automatic_repair():
    grouped, _ = packets(
        [("native_visual_platform_policy", "4444J99/domus-genoma", False, "platform_policy")], {}, "now"
    )
    assert not grouped["4444J99/domus-genoma"]["friction_signals"][0]["healable"]
