from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path


RUNTIME_URL_ENV_ORDER = (
    "LIMEN_WORKER_URL",
    "NEXT_PUBLIC_API_URL",
    "LIMEN_API_URL",
)


def configured_runtime_url(root: Path, *, filename: str = "runtime.config.json") -> str:
    try:
        value = json.loads((root / filename).read_text(encoding="utf-8")).get("apiUrl", "")
    except (OSError, ValueError, AttributeError):
        return ""
    return value.strip() if isinstance(value, str) else ""


def runtime_api_url(
    root: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the one runtime URL used by local control-plane sensors.

    The live worker override wins, followed by the browser build-time URL, the deployment
    repository variable, and finally the committed non-secret runtime configuration.
    """

    env = environ if environ is not None else os.environ
    for name in RUNTIME_URL_ENV_ORDER:
        value = env.get(name, "").strip()
        if value:
            return value
    resolved_root = root or Path(env.get("LIMEN_ROOT") or Path(__file__).resolve().parents[3])
    return configured_runtime_url(Path(resolved_root))
