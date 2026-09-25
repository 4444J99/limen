"""Offline regressions: no real network calls or administrative effects."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "consolidate-github.py"
SPEC = importlib.util.spec_from_file_location("consolidate_github", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def repository(repo_id=1, owner="organvm", name="example", **changes):
    row = dict(id=repo_id, owner={"login": owner}, name=name, full_name=f"{owner}/{name}",
               private=False, visibility="public", archived=False, topics=["organ-ii", "python"],
               default_branch="main", has_pages=False)
    row.update(changes)
    return row


def state(repo_id=1, owner="organvm", name="example", **changes):
    return mod.snapshot(repository(repo_id, owner, name, **changes))


def preflight(row):
    return {k: row[k] for k in ("id", "full_name", "destination", "visibility", "archived", "default_branch")} | {
        "preservation_checked": True, "evidence_ref": "private://review/fixture-only",
    }


class ConsolidationTests(unittest.TestCase):
    def test_target_is_personal_and_is_not_a_source(self):
        self.assertEqual(mod.TARGET, "4444J99")
        self.assertIn("organvm", mod.OWNERS)
        self.assertNotIn("4444J99", mod.OWNERS)
        self.assertEqual(len(set(mod.OWNERS)), 10)

    def test_nonzero_cli_exit_is_not_empty_inventory(self):
        with patch.object(mod.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "[]", "private")):
            with self.assertRaises(mod.ConsolidationError):
                mod.gh_json(["api", "/user"])

    def test_invalid_json_is_not_empty_inventory(self):
        with patch.object(mod.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "not json", "")):
            with self.assertRaises(mod.ConsolidationError):
                mod.gh_json(["api", "/user"])

    def test_missing_cli_and_timeout_are_explicit_failures(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("gh", 1)):
            with self.subTest(error=type(error).__name__), patch.object(mod.subprocess, "run", side_effect=error):
                with self.assertRaises(mod.ConsolidationError):
                    mod.gh_json(["api", "/user"])

    def test_full_page_requires_next_page(self):
        with patch.object(mod, "gh_json", side_effect=[[{}] * 100, [{}]]) as call:
            self.assertEqual(len(mod.pages("/endpoint?x=y")), 101)
            self.assertIn("&per_page=100&page=2", call.call_args.args[0][1])

    def test_page_error_and_bound_do_not_claim_completion(self):
        with patch.object(mod, "gh_json", side_effect=[[{}] * 100, mod.ConsolidationError("no access")]):
            with self.assertRaises(mod.ConsolidationError):
                mod.pages("/endpoint")
        with patch.object(mod, "MAX_PAGES", 1), patch.object(mod, "gh_json", return_value=[{}] * 100):
            with self.assertRaises(mod.ConsolidationError):
                mod.pages("/endpoint")

    def test_invalid_page_shape_fails(self):
        for page in ({"message": "forbidden"}, [{}] * 101):
            with self.subTest(page_type=type(page).__name__), patch.object(mod, "gh_json", return_value=page):
                with self.assertRaises(mod.ConsolidationError):
                    mod.pages("/endpoint")

    def test_missing_or_contradictory_metadata_fails(self):
        for changes in (dict(id=True), dict(id=0), dict(topics=None), dict(full_name=None),
                        dict(full_name="other/example"), dict(private=True), dict(archived=None),
                        dict(visibility="internal"), dict(default_branch=None), dict(has_pages=None)):
            with self.subTest(changes=changes), self.assertRaises(mod.ConsolidationError):
                mod.snapshot(repository(**changes))

    def test_destination_collision_case_insensitive(self):
        plan = mod.build_plan([state(name="Example")], [state(2, mod.TARGET, "example")])
        self.assertIn("name-collision", plan[0]["holds"])

    def test_source_collisions_block_both_without_renaming(self):
        plan = mod.build_plan([state(), state(2, "meta-organvm")], [])
        self.assertEqual([r["holds"] for r in plan], [["name-collision"], ["name-collision"]])

    def test_profiles_and_pages_are_retained(self):
        for kwargs, hold in ((dict(name=".github"), "organization-profile-and-shared-workflow-retention"),
                             (dict(name="site.github.io"), "pages-migration-required"),
                             (dict(has_pages=True), "pages-migration-required")):
            with self.subTest(kwargs=kwargs):
                self.assertIn(hold, mod.build_plan([state(**kwargs)], [])[0]["holds"])

    def test_topic_union_preserves_logical_organ_and_concurrent_additions(self):
        before = state()
        current = state(owner=mod.TARGET, topics=["organ-ii", "new-topic"])
        topics = mod.desired_topics(before, current)
        self.assertTrue({"organ-ii", "python", "new-topic", "organvm"}.issubset(topics))
        self.assertNotIn("organ-iii", topics)

    def test_topic_capacity_holds_before_transfer(self):
        row = state(topics=[f"topic-{i}" for i in range(20)])
        self.assertIn("topic-capacity", mod.build_plan([row], [])[0]["holds"])

    def test_archived_repos_do_not_require_new_topic_capacity(self):
        row = state(archived=True, topics=[f"topic-{i}" for i in range(20)])
        self.assertNotIn("topic-capacity", mod.build_plan([row], [])[0]["holds"])

    def test_preflight_is_bound_to_each_identity_and_current_state(self):
        row = mod.build_plan([state()], [])[0]
        record = preflight(row)
        self.assertTrue(mod.preflight_matches(row, record))
        for change in (dict(id=2), dict(id=True), dict(full_name="other/example"),
                       dict(visibility="private"), dict(archived=0), dict(default_branch="develop"),
                       dict(destination="organvm/example"), dict(evidence_ref=""),
                       dict(preservation_checked=False)):
            with self.subTest(change=change):
                self.assertFalse(mod.preflight_matches(row, record | change))
        self.assertFalse(mod.preflight_matches(row, None))

    def test_duplicate_preflight_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preflight.json"
            path.write_text(json.dumps({"schema": mod.PREFLIGHT_SCHEMA, "target": mod.TARGET,
                                       "repositories": [{"id": 1}, {"id": 1}]}))
            with self.assertRaises(mod.ConsolidationError):
                mod.load_preflight(path)

    def test_wrong_preflight_target_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preflight.json"
            path.write_text(json.dumps({"schema": mod.PREFLIGHT_SCHEMA, "target": "organvm", "repositories": []}))
            with self.assertRaises(mod.ConsolidationError):
                mod.load_preflight(path)

    def test_receipt_is_private_and_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            mod.write_receipt(path, {"test": True})
            self.assertEqual(json.loads(path.read_text()), {"test": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)

    def test_receipt_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, link = Path(tmp) / "target", Path(tmp) / "link"
            target.write_text("unchanged")
            os.symlink(target, link)
            with self.assertRaises(mod.ConsolidationError):
                mod.write_receipt(link, {})
            self.assertEqual(target.read_text(), "unchanged")

    def test_accepted_transfer_not_counted_as_verified(self):
        row = mod.build_plan([state()], [])[0]
        result = {}
        with patch.object(mod, "read_repository", return_value=state()), patch.object(mod, "gh_json", return_value={}):
            mod.transfer(row, result, lambda: None, attempts=2, delay=0)
        self.assertEqual(result["status"], "accepted_unverified")

    def test_stable_identity_is_revalidated_before_post(self):
        row = mod.build_plan([state()], [])[0]
        with patch.object(mod, "read_repository", return_value=state(repo_id=2)), patch.object(mod, "gh_json") as call:
            with self.assertRaises(mod.ConsolidationError):
                mod.transfer(row, {}, lambda: None)
            call.assert_not_called()

    def test_checkpoint_failure_prevents_post(self):
        row = mod.build_plan([state()], [])[0]
        def bad_checkpoint():
            raise OSError("disk full")
        with patch.object(mod, "read_repository", return_value=state()), patch.object(mod, "gh_json") as call:
            with self.assertRaises(OSError):
                mod.transfer(row, {}, bad_checkpoint)
            call.assert_not_called()

    def test_verified_transfer_preserves_topics_and_uses_personal_destination(self):
        before = state()
        after = state(owner=mod.TARGET, topics=["organ-ii", "new-topic"])
        final = state(owner=mod.TARGET, topics=mod.desired_topics(before, after))
        row, result = mod.build_plan([before], [])[0], {}
        with patch.object(mod, "read_repository", side_effect=[before, after, final]), patch.object(mod, "gh_json", return_value={}) as call:
            mod.transfer(row, result, lambda: None)
        self.assertEqual(result["status"], "transfer_verified")
        self.assertEqual(result["integration_verification"], "pending")
        self.assertIn("new_owner=4444J99", call.call_args_list[0].args[0])
        self.assertIn("names[]=new-topic", call.call_args_list[1].args[0])
        self.assertIn("names[]=python", call.call_args_list[1].args[0])

    def test_archived_transfer_does_not_write_topics_or_unarchive(self):
        before = state(archived=True)
        after = state(owner=mod.TARGET, archived=True)
        row, result = mod.build_plan([before], [])[0], {}
        with patch.object(mod, "read_repository", side_effect=[before, after]), patch.object(mod, "gh_json", return_value={}) as call:
            mod.transfer(row, result, lambda: None)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["status"], "transfer_verified")

    def test_visibility_or_archive_drift_never_verifies(self):
        for change in (dict(private=True, visibility="private"), dict(archived=True), dict(has_pages=True)):
            with self.subTest(change=change):
                row = mod.build_plan([state()], [])[0]
                with patch.object(mod, "read_repository", side_effect=[state(), state(owner=mod.TARGET, **change)]), patch.object(mod, "gh_json", return_value={}):
                    with self.assertRaises(mod.ConsolidationError):
                        mod.transfer(row, {}, lambda: None)

    def test_topic_failure_does_not_report_verified_transfer(self):
        row, result = mod.build_plan([state()], [])[0], {}
        with patch.object(mod, "read_repository", side_effect=[state(), state(owner=mod.TARGET)]), patch.object(mod, "gh_json", side_effect=[{}, mod.ConsolidationError("denied")]):
            with self.assertRaises(mod.ConsolidationError):
                mod.transfer(row, result, lambda: None)
        self.assertEqual(result["status"], "ownership_verified")
        self.assertIn("after", result)

    def test_dry_run_never_writes_and_hides_private_names(self):
        out = io.StringIO()
        with patch.object(mod, "inventory", return_value=([state(name="confidential-project", private=True, visibility="private")], [])), patch.object(mod, "transfer") as transfer, redirect_stdout(out):
            self.assertEqual(mod.main([]), 0)
        transfer.assert_not_called()
        self.assertNotIn("confidential-project", out.getvalue())

    def test_apply_requires_preflight_and_private_receipt(self):
        with patch.object(mod, "inventory") as call, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                mod.main(["--apply"])
        call.assert_not_called()

    def test_unreviewed_rows_cannot_move_even_with_allow_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            pf, receipt = Path(tmp)/"preflight.json", Path(tmp)/"receipt.json"
            pf.write_text(json.dumps({"schema": mod.PREFLIGHT_SCHEMA, "target": mod.TARGET, "repositories": []}))
            with patch.object(mod, "inventory", return_value=([state()], [])), patch.object(mod, "transfer") as effect, redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main(["--apply", "--allow-partial", "--preflight", str(pf), "--receipt", str(receipt)]), 2)
            effect.assert_not_called()
            self.assertEqual(json.loads(receipt.read_text())["results"][0]["status"], "held")

    def test_failed_read_returns_nonzero_and_incomplete_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"receipt.json"
            with patch.object(mod, "inventory", side_effect=mod.ConsolidationError("denied")), redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(["--receipt", str(path)]), 1)
            data = json.loads(path.read_text())
            self.assertFalse(data["inventory_pages_complete"])
            self.assertEqual(data["visibility_coverage"], "credential_visible_only")


if __name__ == "__main__":
    unittest.main()
