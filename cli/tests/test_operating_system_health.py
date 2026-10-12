from limen.operating_system_health import packets


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
