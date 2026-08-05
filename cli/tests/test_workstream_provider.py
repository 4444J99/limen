from __future__ import annotations

from dataclasses import replace

import limen.census as census
from limen.workstream_provider import (
    direct_native_workstream,
    workstream_binary_candidates,
    workstream_launchable,
)


def test_registry_renames_and_distinct_binaries_share_one_candidate_contract() -> None:
    source = next(vendor for vendor in census.VENDORS if direct_native_workstream(vendor))
    renamed = replace(
        source,
        name="fixture-provider-renamed-arbitrarily",
        aliases=(),
        binary="fixture-provider-cli",
    )
    override_key = "LIMEN_FIXTURE_PROVIDER_RENAMED_ARBITRARILY_BIN"

    assert workstream_binary_candidates(renamed, {}) == (
        "fixture-provider-cli",
        "fixture-provider-renamed-arbitrarily",
    )
    assert workstream_binary_candidates(renamed, {override_key: "/fixture/provider-override"}) == (
        "/fixture/provider-override",
        "fixture-provider-cli",
        "fixture-provider-renamed-arbitrarily",
    )


def test_launchability_retains_issue_assignment_and_autonomous_adapter_boundaries() -> None:
    native = next(vendor for vendor in census.VENDORS if direct_native_workstream(vendor))
    jules = next(vendor for vendor in census.VENDORS if vendor.execution.workstream_adapter == "jules")
    issue_assignment = next(vendor for vendor in census.VENDORS if vendor.issue_assignment)

    assert workstream_launchable(native, autonomous=False) is True
    assert workstream_launchable(native, autonomous=True) is True
    assert direct_native_workstream(jules) is False
    assert workstream_launchable(jules, autonomous=False) is False
    assert workstream_launchable(jules, autonomous=True) is True
    assert workstream_launchable(issue_assignment, autonomous=False) is False
    assert workstream_launchable(issue_assignment, autonomous=True) is False
