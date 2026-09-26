"""Offline security checks; these do not establish a hosted executor run."""
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("chat_runner", ROOT / "scripts/chat-github-runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def context(self):
        profile = json.loads((ROOT / "institutio/governance/chat-github-profiles.json").read_text())["profiles"]["python-canary"]
        return {"head": "a" * 40, "control_sha": "b" * 40, "control_repository": "4444J99/limen",
                "repository": "4444J99/limen", "deadline": "2099-01-01T00:00:00Z", "profile": "python-canary",
                "profile_digest": runner.hashlib.sha256(runner.canonical(profile)).hexdigest()}

    def test_exact_controller_and_profile(self):
        context = self.context()
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "4444J99/limen", "GITHUB_SHA": "b" * 40}):
            self.assertEqual(runner.validate_context(context)["timeout_seconds"], 30)
            for field, value in [("control_sha", "c" * 40), ("profile_digest", "f" * 64),
                                 ("repository", "someone/else"), ("deadline", "2000-01-01T00:00:00Z")]:
                with self.assertRaises(ValueError):
                    runner.validate_context({**context, field: value})

    def test_unapproved_origin_denied_before_transport(self):
        with patch.dict(os.environ, {"LIMEN_CONDUCT_URL": "https://example.invalid"}):
            with self.assertRaises(ValueError):
                runner.api("/x", {})

    def test_canary_profile_cannot_change_its_oracle(self):
        profile = json.loads((ROOT / "institutio/governance/chat-github-profiles.json").read_text())["profiles"]["python-canary"]
        self.assertEqual(profile["paths"], ["scripts/chat-github-canary.py"])
        self.assertNotIn(profile["argv"][-1], profile["paths"])
        self.assertRegex(profile["image"], r"@sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
