"""Fixed canary oracle is outside the Chat canary's permitted mutation paths."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("canary", Path(__file__).parents[1] / "chat-github-canary.py")
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)


class CanaryTest(unittest.TestCase):
    def test_label_binds_repository_and_twelve_character_head(self):
        self.assertEqual(canary.receipt_label("4444J99/limen", "abcdef0123456789"), "4444J99/limen@abcdef012345")


if __name__ == "__main__":
    unittest.main()
