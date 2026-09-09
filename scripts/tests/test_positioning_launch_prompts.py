"""Regression tests for copied handoffs losing authority, freshness or identity."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("launch_prompts", ROOT / "scripts/positioning-launch-prompts.py")
assert SPEC and SPEC.loader
LAUNCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCH)


class LaunchContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads((ROOT / LAUNCH.CONTRACT).read_text())
        self.snapshot = json.loads((ROOT / LAUNCH.SNAPSHOT).read_text())
        self.program = yaml.safe_load((ROOT / LAUNCH.PROGRAM).read_text())
        self.issue_map = json.loads((ROOT / LAUNCH.ISSUE_MAP).read_text())

    def render(self):
        return LAUNCH.render(self.contract, self.snapshot, self.program, self.issue_map)

    def assert_drift_rejected(self, mutated):
        """The check must reject a bad copied block without repairing/overwriting it."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (LAUNCH.CONTRACT, LAUNCH.SNAPSHOT, LAUNCH.PROGRAM, LAUNCH.ISSUE_MAP, LAUNCH.PLAN, Path("AGENTS.md")):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            output = root / LAUNCH.OUTPUT
            output.write_text(mutated)
            with self.assertRaisesRegex(LAUNCH.ContractError, "drifted"):
                LAUNCH.check(root)
            self.assertEqual(mutated, output.read_text())

    def test_each_copied_block_carries_authority_freshness_and_reuse(self):
        blocks = re.findall(r"```text\n(.*?)\n```", self.render(), re.S)
        self.assertEqual(len(blocks), 13)
        for block in blocks:
            with self.subTest(block=block.splitlines()[0]):
                self.assertIn("Read current AGENTS.md", block)
                self.assertIn("current repository version of docs/positioning/program/recalibration/2026-09-08-snapshot.json", block)
                self.assertIn("dated planning evidence, not dispatch authority", block)
                self.assertIn("re-query current ownership", block)
                self.assertIn("autonomous dispatch requires its own broker reservation", block)
                self.assertIn("No fake leases", block)
                self.assertIn("ongoing monitoring are authorized by these prompts", block)
                self.assertIn("live capabilities and budget", block)
                self.assertIn("cheapest adequate currently available model", block)
                self.assertIn("exact tested/accepted heads", block)
                self.assertIn("Do not rerun all research, all tests, all receipts or the full estate census", block)
        for block in blocks[:12]:
            self.assertIn("Run-slice ceiling:", block)
            self.assertIn("no child fanout", block)
        self.assertIn("complete current launch block", blocks[-1])
        self.assertIn("remaining run ceiling", blocks[-1])

    def test_one_package_missing_shared_contract_is_rejected(self):
        original = self.render()
        self.assert_drift_rejected(original.replace(self.contract["shared"]["authority"] + "\n", "", 1))

    def test_resume_missing_current_inputs_is_rejected(self):
        original = self.render()
        prefix, resume = original.split("## Resume after usage or provider change", 1)
        mutated = prefix + "## Resume after usage or provider change" + resume.replace(self.contract["shared"]["inputs"], "Read the old plan and that package only.")
        self.assert_drift_rejected(mutated)

    def test_r05_receipts_cannot_replace_predeployment_authority(self):
        original = self.render()
        self.assert_drift_rejected(original.replace(self.contract["package_overrides"]["R05"]["boundary"], "Deploy now and record receipts afterward."))

    def test_r10_fixture_reviews_cannot_complete_real_periods(self):
        original = self.render()
        self.assert_drift_rejected(original.replace(self.contract["package_overrides"]["R10"]["boundary"], "Run four copies of the weekly fixture and two monthly fixtures now."))

    def test_source_omissions_are_rejected_even_before_regeneration(self):
        for key in ("inputs", "authority", "verification"):
            with self.subTest(key=key):
                contract = copy.deepcopy(self.contract)
                del contract["shared"][key]
                with self.assertRaises(LAUNCH.ContractError):
                    LAUNCH.render(contract, self.snapshot, self.program, self.issue_map)

    def test_source_cannot_drop_separate_monitoring_authority(self):
        self.contract["package_overrides"]["R10"]["boundary"] = self.contract["package_overrides"]["R10"]["boundary"].replace("Do not start autonomous monitoring without separate recorded user scheduling authority", "Start autonomous monitoring now")
        with self.assertRaisesRegex(LAUNCH.ContractError, "R10 observation"):
            self.render()

    def test_source_cannot_move_live_receipts_before_deployment(self):
        self.contract["package_overrides"]["R05"]["exit"] = self.contract["package_overrides"]["R05"]["exit"].replace("after authorized deployment", "before deployment")
        with self.assertRaisesRegex(LAUNCH.ContractError, "R05 acceptance"):
            self.render()

    def test_source_cannot_drop_current_policy_while_keeping_a_snapshot(self):
        self.contract["shared"]["inputs"] = self.contract["shared"]["inputs"].replace("current AGENTS.md", "old AGENTS.md")
        with self.assertRaisesRegex(LAUNCH.ContractError, "inputs"):
            self.render()

    def test_same_count_wrong_issue_mapping_is_rejected(self):
        self.snapshot["leaves"][0]["issue"], self.snapshot["leaves"][1]["issue"] = self.snapshot["leaves"][1]["issue"], self.snapshot["leaves"][0]["issue"]
        with self.assertRaisesRegex(LAUNCH.ContractError, "issue identity"):
            self.render()

    def test_missing_and_duplicate_canonical_leaves_are_rejected(self):
        for replacement in (self.snapshot["leaves"][:-1], self.snapshot["leaves"][:-1] + [self.snapshot["leaves"][0]]):
            with self.subTest(count=len(replacement)):
                snapshot = copy.deepcopy(self.snapshot)
                snapshot["leaves"] = replacement
                with self.assertRaisesRegex(LAUNCH.ContractError, "canonical leaf"):
                    LAUNCH.render(self.contract, snapshot, self.program, self.issue_map)

    def test_packet_cannot_silently_lose_a_retained_leaf(self):
        self.snapshot["packets"][1]["leaf_ids"].pop()
        with self.assertRaisesRegex(LAUNCH.ContractError, "leaf scope"):
            self.render()

    def test_historical_planning_cannot_be_promoted_to_dispatch_authority(self):
        self.snapshot["status"] = "live_ready"
        with self.assertRaisesRegex(LAUNCH.ContractError, "planning evidence"):
            self.render()

    def test_scoped_gate_covers_all_source_and_consumer_inputs(self):
        registry = yaml.safe_load((ROOT / "institutio/governance/gates.yaml").read_text())
        gate = registry["gates"]["positioning-launch-prompts-test"]
        expected = {str(path) for path in (LAUNCH.CONTRACT, LAUNCH.SNAPSHOT, LAUNCH.OUTPUT, LAUNCH.PLAN, LAUNCH.PROGRAM, LAUNCH.ISSUE_MAP)}
        expected.update({"AGENTS.md", "scripts/positioning-launch-prompts.py", "scripts/tests/test_positioning_launch_prompts.py", "institutio/governance/gates.yaml"})
        self.assertTrue(expected.issubset(gate["paths"]))
        self.assertIsNot(gate.get("scoped"), False)
        self.assertEqual(gate.get("tier", "cheap"), "cheap")
        self.assertIn("positioning-launch-prompts.py --check", gate["command"])
        self.assertIn("test_positioning_launch_prompts.py", gate["command"])


if __name__ == "__main__":
    unittest.main()
