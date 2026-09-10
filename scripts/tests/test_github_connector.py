"""The pipe bridge must fail closed before any receipt can pass."""

from __future__ import annotations

import io
import json
import os
import pty
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cli" / "src"))
from limen.github_connector import ConnectorError, PREFIX, StdioGitHubConnector, read_url


class ConnectorTests(unittest.TestCase):
    def exchange(self, build):
        read_fd, write_fd = os.pipe()
        output = io.StringIO()
        connector = StdioGitHubConnector(timeout=0.5, input_fd=read_fd, output=output)

        def respond():
            import time

            while not output.getvalue():
                time.sleep(0.001)
            request = json.loads(output.getvalue()[len(PREFIX) :])
            try:
                os.write(write_fd, build(request))
            finally:
                os.close(write_fd)

        thread = threading.Thread(target=respond)
        thread.start()
        try:
            return connector.request(["api", "repos/4444J99/limen/issues/2251/comments?per_page=100&page=1"])
        finally:
            os.close(read_fd)
            thread.join(timeout=1)

    def test_raw_fields_survive_roundtrip(self):
        value = [{"id": 7, "created_at": "2026-08-15T01:51:46Z", "body": "raw receipt", "html_url": "u"}]
        self.assertEqual(
            self.exchange(lambda r: (json.dumps({**r, "ok": True, "value": value}) + "\n").encode()), value
        )

    def test_wrong_request_id_rejected(self):
        with self.assertRaisesRegex(ConnectorError, "correlation"):
            self.exchange(lambda r: (json.dumps({**r, "id": "replayed", "ok": True, "value": []}) + "\n").encode())

    def test_wrong_url_rejected(self):
        with self.assertRaisesRegex(ConnectorError, "correlation"):
            self.exchange(
                lambda r: (json.dumps({**r, "url": "https://example.com", "ok": True, "value": []}) + "\n").encode()
            )

    def test_connector_failure_not_empty_success(self):
        with self.assertRaisesRegex(ConnectorError, "unavailable"):
            self.exchange(lambda r: (json.dumps({**r, "ok": False}) + "\n").encode())

    def test_truncated_json_and_eof_rejected(self):
        for value in (b"{broken\n", b""):
            with self.subTest(value=value), self.assertRaises(ConnectorError):
                self.exchange(lambda r: value)

    def test_unsolicited_response_rejected(self):
        with self.assertRaisesRegex(ConnectorError, "unsolicited"):
            self.exchange(lambda r: (json.dumps({**r, "ok": True, "value": []}) + "\n{}\n").encode())

    def test_deadline_without_response(self):
        read_fd, write_fd = os.pipe()
        try:
            connector = StdioGitHubConnector(timeout=0.01, input_fd=read_fd, output=io.StringIO())
            with self.assertRaisesRegex(ConnectorError, "deadline"):
                connector.request(["api", "repositories/1255213941"])
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_no_mutations_auth_endpoints_or_traversal(self):
        for args in (
            ["api", "repos/a/b/issues", "--method", "POST"],
            ["api", "graphql"],
            ["api", "user"],
            ["api", "repos/a/b/actions/secrets"],
            ["api", "https://evil.test/repos/a/b/issues"],
            ["api", "repos/a/b/contents/../secrets"],
            ["api", "repos/a/b/contents/%2e%2e"],
            ["api", "repos/a/b/issues#fragment"],
        ):
            with self.subTest(args=args), self.assertRaises(ConnectorError):
                read_url(args)
        with self.assertRaises(ConnectorError):
            read_url(["api", "repos/a/b/issues"], {"title": "mutation"})

    def test_pty_large_private_response_is_not_echoed_or_truncated(self):
        import select

        master, slave = pty.openpty()
        output = io.StringIO()
        connector = StdioGitHubConnector(timeout=2, input_fd=slave, output=output)
        value = {"tree": [{"path": "private-source", "sha": "a" * 40}] * 3000}

        def respond():
            import time

            while not output.getvalue():
                time.sleep(0.001)
            request = json.loads(output.getvalue()[len(PREFIX) :])
            data = (json.dumps({**request, "ok": True, "value": value}) + "\n").encode()
            while data:
                data = data[os.write(master, data) :]

        thread = threading.Thread(target=respond)
        thread.start()
        try:
            self.assertEqual(connector.request(["api", "repos/a/b/git/trees/" + "a" * 40]), value)
            self.assertFalse(select.select([master], [], [], 0)[0], "private payload was echoed")
        finally:
            connector.close()
            thread.join(timeout=1)
            os.close(master)
            os.close(slave)


if __name__ == "__main__":
    unittest.main()
