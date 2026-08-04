"""Shared provider predicates for workstream selection and launch."""

from __future__ import annotations

from collections.abc import Mapping

from limen.census import Vendor


def workstream_binary_candidates(
    vendor: Vendor,
    environ: Mapping[str, str],
) -> tuple[str, ...]:
    """Return the registry-derived executable candidates for one provider lane."""

    env_key = f"LIMEN_{vendor.name.upper().replace('-', '_')}_BIN"
    override = environ.get(env_key, "").strip()
    return tuple(dict.fromkeys(value for value in (override, vendor.binary, vendor.name) if value))


def direct_native_workstream(vendor: Vendor) -> bool:
    """Return whether a provider owns a direct native workstream transport."""

    profile = getattr(vendor, "execution", None)
    if profile is None:
        return vendor.local_checkout
    return profile.transport == "native-cli" or profile.transport.startswith("ianva-")


def workstream_launchable(vendor: Vendor, *, autonomous: bool) -> bool:
    """Return whether the lane can execute this interactive/autonomous workstream mode."""

    profile = getattr(vendor, "execution", None)
    adapter = profile.workstream_adapter if profile is not None else "positional"
    return not vendor.issue_assignment and (direct_native_workstream(vendor) or (autonomous and adapter == "jules"))
