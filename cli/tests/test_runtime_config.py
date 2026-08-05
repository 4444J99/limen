from __future__ import annotations

import json
from pathlib import Path

from limen.runtime_config import runtime_api_url


def test_runtime_url_precedence_is_worker_then_public_then_deploy(tmp_path: Path) -> None:
    (tmp_path / "runtime.config.json").write_text(json.dumps({"apiUrl": "https://configured.example"}))
    env = {
        "LIMEN_WORKER_URL": "https://worker.example",
        "NEXT_PUBLIC_API_URL": "https://public.example",
        "LIMEN_API_URL": "https://deploy.example",
    }

    assert runtime_api_url(tmp_path, environ=env) == "https://worker.example"
    del env["LIMEN_WORKER_URL"]
    assert runtime_api_url(tmp_path, environ=env) == "https://public.example"
    del env["NEXT_PUBLIC_API_URL"]
    assert runtime_api_url(tmp_path, environ=env) == "https://deploy.example"


def test_runtime_url_falls_back_to_configured_runtime(tmp_path: Path) -> None:
    (tmp_path / "runtime.config.json").write_text(json.dumps({"apiUrl": "https://configured.example"}))

    assert runtime_api_url(tmp_path, environ={}) == "https://configured.example"


def test_runtime_url_invalid_config_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "runtime.config.json").write_text("not-json")

    assert runtime_api_url(tmp_path, environ={}) == ""
