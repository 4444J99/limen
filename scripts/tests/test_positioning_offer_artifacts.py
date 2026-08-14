"""Pytest discovery shim for the historical hyphenated offer-artifact suite."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("positioning-offer-artifacts.test.py")
SPEC = importlib.util.spec_from_file_location("positioning_offer_artifacts_tests", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

TestOfferArtifacts = MODULE.OfferArtifactTests
