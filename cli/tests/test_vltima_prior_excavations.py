from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vltima-prior-excavations.py"


def _load(name: str = "vltima_prior_excavations_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_private_labels_resolve_under_session_corpus(tmp_path: Path) -> None:
    excavations = _load("vltima_prior_path_resolution")
    private_root = tmp_path / ".limen-private" / "session-corpus"

    path = excavations.path_from_label(
        ".limen-private/session-corpus/lifecycle/prior.json",
        root=tmp_path,
        private_root=private_root,
    )

    assert path == private_root / "lifecycle" / "prior.json"


def test_private_json_summary_redacts_values(tmp_path: Path) -> None:
    excavations = _load("vltima_prior_json_redaction")
    private_json = tmp_path / "private.json"
    private_json.write_text(
        json.dumps(
            {
                "generated_at": "2026-07-06T00:00:00+00:00",
                "units": [{"body": "SECRET_PROMPT_BODY"}],
                "coverage": {"sessions": 1},
            }
        ),
        encoding="utf-8",
    )

    summary = excavations.json_summary(private_json)
    rendered = json.dumps(summary, sort_keys=True)

    assert summary["kind"] == "json"
    assert summary["collection_counts"] == {"coverage": 1, "units": 1}
    assert "SECRET_PROMPT_BODY" not in rendered


def test_build_snapshot_classifies_known_surface_and_redacts_markdown(tmp_path: Path) -> None:
    excavations = _load("vltima_prior_snapshot")
    private_root = tmp_path / ".limen-private" / "session-corpus"
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    (private_root / "inventory").mkdir(parents=True)
    (tmp_path / "scripts" / "session-corpus-ledger.py").write_text("# script\n", encoding="utf-8")
    (tmp_path / "docs" / "session-corpus-ledger.md").write_text(
        "# Session Corpus Ledger\n\nGenerated: `2026-07-06T00:00:00+00:00`\n",
        encoding="utf-8",
    )
    (private_root / "inventory" / "session-corpus-ledger.json").write_text(
        json.dumps({"generated_at": "2026-07-06T00:00:00+00:00", "units": [{"body": "SECRET"}]}),
        encoding="utf-8",
    )

    snapshot = excavations.build_snapshot(root=tmp_path, private_root=private_root)
    surface = next(item for item in snapshot["surfaces"] if item["id"] == "session-corpus-ledger")
    markdown = excavations.render_markdown(snapshot)

    assert surface["script_exists"] is True
    assert surface["tracked_present"] == 1
    assert surface["private_present"] == 1
    assert surface["lane"] == "session-corpus"
    assert "SECRET" not in json.dumps(snapshot, sort_keys=True)
    assert "SECRET" not in markdown
    assert "`session-corpus-ledger`" in markdown


def test_refresh_order_keeps_lifecycle_dependencies() -> None:
    excavations = _load("vltima_prior_refresh_order")
    surfaces = [{"id": spec.id, "depends_on": list(spec.depends_on)} for spec in excavations.SURFACES]

    order = excavations.refresh_order(surfaces)

    assert order.index("session-corpus-ledger") < order.index("prompt-lifecycle-ledger")
    assert order.index("prompt-lifecycle-ledger") < order.index("session-lifecycle-blockers")
    assert order.index("session-lifecycle-blockers") < order.index("session-attack-paths")
    assert order.index("session-attack-paths") < order.index("prompt-priority-map")


def test_discovered_artifacts_do_not_descend_private_object_store(tmp_path: Path) -> None:
    excavations = _load("vltima_prior_discovery_bounds")
    private_root = tmp_path / ".limen-private" / "session-corpus"
    object_dir = private_root / "corpus-command-center" / "objects" / "aa"
    lifecycle_dir = private_root / "lifecycle"
    object_dir.mkdir(parents=True)
    lifecycle_dir.mkdir(parents=True)
    (object_dir / "prompt-body-ledger.json").write_text('{"body":"SECRET"}\n', encoding="utf-8")
    (lifecycle_dir / "surface-ledger.json").write_text('{"generated_at":"now","items":[1]}\n', encoding="utf-8")

    rows = excavations.discover_artifacts(
        root=tmp_path,
        private_root=private_root,
        known_labels=set(),
    )
    labels = {row["label"] for row in rows}

    assert ".limen-private/session-corpus/lifecycle/surface-ledger.json" in labels
    assert all("objects" not in label for label in labels)
