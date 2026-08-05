from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from ianva import backend_exec, creds, mcphub
from ianva.config import GatewayConfig


class BackendEnvironmentTests(unittest.TestCase):
    def test_private_cache_keys_do_not_reach_backend(self) -> None:
        base = {
            "HOME": "/tmp/home",
            "PATH": "/usr/bin",
            "PORT": "7666",
            "MCPHUB_SETTING_PATH": "/tmp/mcp_settings.json",
            "LIMEN_CONDUCT_TOKEN_CODEX": "sentinel-conduct-token",
            "LIMEN_NON_SECRET_FLAG": "1",
            "CLAUDE_CODE_OAUTH_TOKEN": "sentinel-oauth-token",
            "UNRELATED_SETTING": "retained",
        }
        cache = {
            "LIMEN_CONDUCT_TOKEN_CODEX": "sentinel-conduct-token",
            "LIMEN_NON_SECRET_FLAG": "1",
        }

        with mock.patch.object(creds.paths, "load_limen_env", return_value=cache):
            result = creds.sanitize_backend_env(base)

        self.assertNotIn("LIMEN_CONDUCT_TOKEN_CODEX", result)
        self.assertNotIn("LIMEN_NON_SECRET_FLAG", result)
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", result)
        self.assertEqual(result["UNRELATED_SETTING"], "retained")
        self.assertEqual(result["PORT"], "7666")
        self.assertEqual(result["MCPHUB_SETTING_PATH"], "/tmp/mcp_settings.json")

    def test_exec_boundary_uses_sanitized_environment(self) -> None:
        clean = {"PATH": "/usr/bin", "PORT": "7666"}
        with (
            mock.patch.object(backend_exec, "sanitize_backend_env", return_value=clean),
            mock.patch.object(os, "execvpe") as execvpe,
        ):
            backend_exec.main(["backend-bin", "--serve"])

        execvpe.assert_called_once_with("backend-bin", ["backend-bin", "--serve"], clean)

    def test_detached_start_uses_backend_environment(self) -> None:
        clean = {"PATH": "/usr/bin", "UNRELATED_SETTING": "retained"}
        pidfile = mock.Mock()
        process = mock.Mock(pid=42)
        cfg = GatewayConfig(port=7666, backend_cmd="backend-bin --serve")
        settings = Path("/tmp/ianva-test-settings.json")

        with (
            mock.patch.object(mcphub, "_read_pid", return_value=None),
            mock.patch.object(mcphub.creds, "sanitize_backend_env", return_value=clean),
            mock.patch.object(mcphub.paths, "ensure_dirs"),
            mock.patch.object(mcphub, "PIDFILE", pidfile),
            mock.patch("builtins.open", mock.mock_open()),
            mock.patch.object(subprocess, "Popen", return_value=process) as popen,
        ):
            ok, _ = mcphub.start(cfg, settings)

        self.assertTrue(ok)
        child_env = popen.call_args.kwargs["env"]
        self.assertEqual(child_env["UNRELATED_SETTING"], "retained")
        self.assertEqual(child_env["PORT"], "7666")
        self.assertEqual(child_env["MCPHUB_SETTING_PATH"], str(settings))
        pidfile.write_text.assert_called_once_with("42")

    def test_launchd_supervisor_does_not_source_private_cache(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "ianva-serve.sh"
        text = script.read_text()

        self.assertNotIn('. "$HOME/.limen.env"', text)
        self.assertNotIn("set -a && .", text)
        self.assertIn('exec python3 -m ianva.backend_exec "${ARGV[@]}"', text)


if __name__ == "__main__":
    unittest.main()
