"""Migration privacy overrides legacy publication intent without blind effects."""
import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from estate_posture import visibility_intent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PostureTests(unittest.TestCase):
    def setUp(self):
        self.estate = {
            "classes": {"public": {"match": ["**"], "visibility": "public"}},
            "repo_overrides": {"source/project": {"class": "public", "publish_candidate": True}},
            "personal_consolidation": {"enabled": True, "target": "personal", "sources": ["source"],
                "default_visibility": "private", "public_exceptions": [{"repository_id": 7,
                    "coordinates": ["personal/controller"]}]},
        }

    def test_legacy_candidate_does_not_publish(self):
        self.assertEqual(visibility_intent(self.estate, "source/project", "public", {"id": 8}),
                         ("private", False, True))

    def test_exception_survives_transfer_by_id(self):
        self.assertEqual(visibility_intent(self.estate, "personal/renamed", "private", {"id": 7}),
                         ("public", False, True))
        self.assertEqual(visibility_intent(self.estate, "personal/controller", "public", {"id": 8})[0], "private")

    def test_outside_scope_preserves_existing_behavior(self):
        self.assertEqual(visibility_intent(self.estate, "other/project", "public"), ("public", False, False))

    def test_effector_holds_privacy_change_for_preservation(self):
        gitvs = load("gitvs", "gitvs.py")
        apply = load("apply_visibility", "apply-visibility.py")
        row = {"full_name": "source/project", "id": 8, "private": False}
        plan = apply._plan(self.estate, [row], gitvs, lambda _: (True, "green"))
        self.assertEqual(plan[0]["action"], "review")
        failures, _ = gitvs.visibility_drift([row], self.estate)
        self.assertEqual(len(failures), 1)

    def test_personal_custody_does_not_require_reverse_transfer(self):
        gitvs = load("gitvs", "gitvs.py")
        self.assertEqual(gitvs.shelf_drift({"source": ["project"]},
            [{"full_name": "personal/project"}], "personal"), [])

    def test_audience_uses_new_intent(self):
        audience = load("check_audience", "check-audience.py")
        row = audience.derive(self.estate, {}, {})["rows"][0]
        self.assertEqual(row["visibility"], "private")
        self.assertFalse(row["publish_candidate"])


if __name__ == "__main__":
    unittest.main()
