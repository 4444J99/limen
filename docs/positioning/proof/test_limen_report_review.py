"""Counterexamples to treating changed reports or fabricated review records as accepted."""

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("report_review", Path(__file__).with_name("verify_limen_report.py"))
REVIEW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEW)


class ReportReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in REVIEW.DOCUMENTS:
            relative = Path("docs/positioning/proof") / name
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REVIEW.ROOT / relative, self.root / relative)
        (self.root / REVIEW.OBSERVATION).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REVIEW.ROOT / REVIEW.OBSERVATION, self.root / REVIEW.OBSERVATION)

    def edit_observation(self, mutate):
        path = self.root / REVIEW.OBSERVATION
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value))

    def test_actual_reviewed_package_passes_with_bounded_claim(self):
        result = REVIEW.verify(self.root)
        self.assertEqual(result["status"], "pass")
        self.assertIn("no live revalidation", result["boundary"])
        self.assertIn("task completion", result["boundary"])

    def test_changed_report_requires_review_even_if_evidence_ids_remain(self):
        path = self.root / "docs/positioning/proof/limen-engineering-report.md"
        path.write_text(path.read_text() + "\nThe system guarantees every outcome. E01.\n")
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_missing_deliverable_rejects(self):
        (self.root / "docs/positioning/proof/limen-limitations.md").unlink()
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_missing_claim_row_rejects(self):
        path = self.root / "docs/positioning/proof/limen-evidence-appendix.md"
        path.write_text("\n".join(line for line in path.read_text().splitlines() if not line.startswith("| E09 |")))
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_lite_or_rewritten_verdict_cannot_replace_independent_review(self):
        self.edit_observation(lambda value: value["comments"][1].update(body="Approval recommended; Lite review"))
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_wrong_report_head_cannot_inherit_old_verdict(self):
        self.edit_observation(lambda value: value.update(report_head="a" * 40))
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_missing_independent_verdict_rejects(self):
        self.edit_observation(lambda value: value["comments"].pop())
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_observation_cannot_predate_review(self):
        self.edit_observation(lambda value: value.update(observed_at="2026-09-08T00:00:00Z"))
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_future_capture_cannot_impersonate_fresh_observation(self):
        self.edit_observation(lambda value: value.update(observed_at="2099-09-09T00:00:00Z"))
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_recorded_boundary_cannot_be_relabelled_live(self):
        self.edit_observation(lambda value: value.update(boundary="Live verification and publication approved"))
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")

    def test_malformed_observation_fails_closed(self):
        self.edit_observation(lambda value: value.update(comments=[None]))
        self.assertEqual(REVIEW.verify(self.root)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
