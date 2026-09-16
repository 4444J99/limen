"""Execute the publication adapter with isolated Git/GitHub command fixtures."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PublicationTests(unittest.TestCase):
    def exercise(self, exit_code):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "caller.txt").write_text("preserve")
            (root / "git").write_text(
                '#!/bin/sh\ncase "$*" in\n *rev-list*) echo 2;;\n *diff*--quiet*) exit 1;;\n *diff*--shortstat*) echo changed;;\nesac\n'
            )
            (root / "gh").write_text("""#!/bin/sh
if [ "$2" = list ]; then exit 0; fi
while [ "$#" -gt 0 ]; do
 if [ "$1" = --body-file ]; then
  shift
  cat "$1" >"$FIXTURE_ROOT/body.txt"
  printf '%s' "$1" >"$FIXTURE_ROOT/body-path.txt"
 fi
 shift
done
if [ "$FIXTURE_EXIT" != 0 ]; then exit "$FIXTURE_EXIT"; fi
echo https://example.invalid/pr/1
""")
            for name in ("git", "gh"):
                (root / name).chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/publish-board-pr.sh")],
                env={
                    **os.environ,
                    "PATH": str(root) + ":" + os.environ["PATH"],
                    "LIMEN_ROOT": str(root),
                    "FIXTURE_ROOT": str(root),
                    "FIXTURE_EXIT": str(exit_code),
                },
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, exit_code, result.stderr)
            self.assertEqual((root / "caller.txt").read_text(), "preserve")
            self.assertIn("`tasks.yaml`", (root / "body.txt").read_text())
            self.assertFalse(Path((root / "body-path.txt").read_text()).exists())
            return result

    def test_publication_preserves_markdown(self):
        self.assertIn("opened https://example.invalid/pr/1", self.exercise(0).stdout)

    def test_creation_failure_is_not_success(self):
        self.assertNotIn("opened", self.exercise(7).stdout)


if __name__ == "__main__":
    unittest.main()
