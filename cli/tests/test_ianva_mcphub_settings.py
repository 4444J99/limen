from __future__ import annotations

import json
import sys
from pathlib import Path


IANVA_SRC = Path(__file__).resolve().parents[2] / "ianva" / "src"
sys.path.insert(0, str(IANVA_SRC))

from ianva.mcphub import materialize_settings  # noqa: E402


def _settings(tmp_path: Path, *, bearer: str | None = None) -> dict:
    target = tmp_path / "mcp_settings.json"
    materialize_settings([], path=target, bearer=bearer)
    return json.loads(target.read_text())


def test_local_settings_disable_bearer_and_oauth_server_advertisement(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)

    assert settings["systemConfig"] == {
        "routing": {"enableBearerAuth": False},
        "oauthServer": {"enabled": False},
    }


def test_cloud_settings_keep_bearer_without_oauth_server_advertisement(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, bearer="sentinel-token")

    assert settings["systemConfig"] == {
        "routing": {
            "enableBearerAuth": True,
            "bearerKeys": ["sentinel-token"],
        },
        "oauthServer": {"enabled": False},
    }
