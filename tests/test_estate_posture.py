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

    # --- P1/P2 follow-ups (Codex review 5372004958 on #2783) -------------------

    def test_red_receipt_demotes_scoped_legacy_candidate(self):
        """A confirmed red sweep on a live-public legacy candidate keeps the protective
        demotion even though the migration returns private intent + preservation review."""
        gitvs = load("gitvs", "gitvs.py")
        apply = load("apply_visibility", "apply-visibility.py")
        row = {"full_name": "source/project", "id": 8, "private": False}
        plan = apply._plan(self.estate, [row], gitvs, lambda _: (False, "receipt red"))
        self.assertEqual(plan[0]["action"], "demote")

    def test_stale_receipt_keeps_preservation_review(self):
        """Unknown/stale receipts keep the review hold — only a confirmed red demotes."""
        gitvs = load("gitvs", "gitvs.py")
        apply = load("apply_visibility", "apply-visibility.py")
        row = {"full_name": "source/project", "id": 8, "private": False}
        for why in ("no receipt", "stale receipt"):
            plan = apply._plan(self.estate, [row], gitvs, lambda _w=why: (False, _w))
            self.assertEqual(plan[0]["action"], "review")

    def test_exception_id_beats_stale_coordinates(self):
        """A present but mismatched REST id wins over stale coordinates — the repo moved and
        this id no longer belongs to the exception."""
        self.assertEqual(visibility_intent(self.estate, "personal/controller", "public", {"id": 9})[0], "private")

    def test_exception_coordinates_survive_missing_id(self):
        """Without a census id (old facts), coordinates are still the fallback."""
        self.assertEqual(visibility_intent(self.estate, "personal/controller", "public", {})[0], "public")

    def test_census_projection_carries_stable_id(self):
        """The _owner_repos projection must emit the REST id — the P2's whole premise."""
        gitvs = load("gitvs", "gitvs.py")
        proj = gitvs._CENSUS_JQ
        keys = {p.split(":")[0].strip() for p in proj[proj.index("{") + 1 : proj.index("}")].split(",")}
        self.assertIn("id", keys)
        self.assertIn("full_name", keys)

    def test_shelf_drift_rejects_collision_coincidence(self):
        """target/foo (unrelated) must not satisfy declared source/foo when the recorded
        identity points at the renamed transfer target/foo--source."""
        gitvs = load("gitvs", "gitvs.py")
        identity = {"source/foo": {"repository_id": 2, "coordinates": ["source/foo", "target/foo--source"]}}
        drift = gitvs.shelf_drift({"source": ["foo"]}, [{"full_name": "target/foo", "id": 1}], "target", identity)
        self.assertEqual(len(drift), 1)
        self.assertIn("transfer owed", drift[0])

    def test_shelf_drift_accepts_recorded_rename(self):
        gitvs = load("gitvs", "gitvs.py")
        identity = {"source/foo": {"repository_id": 2, "coordinates": ["source/foo", "target/foo--source"]}}
        rows = [{"full_name": "target/foo", "id": 1}, {"full_name": "target/foo--source", "id": 2}]
        self.assertEqual(gitvs.shelf_drift({"source": ["foo"]}, rows, "target", identity), [])

    def test_shelf_drift_legacy_bare_name_without_record(self):
        """No identity record: the legacy bare-name rule still applies (back-compat)."""
        gitvs = load("gitvs", "gitvs.py")
        self.assertEqual(gitvs.shelf_drift({"source": ["foo"]}, [{"full_name": "target/foo", "id": 1}], "target"), [])

    def test_identity_records_absent_file_is_empty(self):
        """The identity map is advisory — an unreadable registry degrades to {}, never raises."""
        gitvs = load("gitvs", "gitvs.py")
        self.assertEqual(
            gitvs._identity_records({"control_plane": {"repository_identity_registry": "nope/missing.json"}}), {}
        )

    def test_check_audience_file_load_without_path(self):
        """spec_from_file_location must work in a fresh interpreter with no scripts/ on
        sys.path — the established file-based loading contract (P1)."""
        import subprocess

        script = str(SCRIPTS / "check-audience.py")
        code = (
            "import importlib.util, sys\n"
            "assert not any('scripts' in p for p in sys.path), sys.path\n"
            f"spec = importlib.util.spec_from_file_location('ca_nopath', {script!r})\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "print('LOAD_OK', m.observed_audience('public', False))\n"
        )
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        self.assertIn("LOAD_OK world", r.stdout)


if __name__ == "__main__":
    unittest.main()
