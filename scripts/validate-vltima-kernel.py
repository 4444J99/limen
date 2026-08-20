#!/usr/bin/env python3
"""Validate the VLTIMA universal kernel and each organ's institutional projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_UNIVERSAL_TERMS = (
    "Object",
    "Subject",
    "Agent",
    "Actor",
    "System",
    "Event",
    "Record",
    "Covenant",
    "Member",
    "Mandate",
    "Standing",
    "Standard",
    "Governance",
    "Exchange",
    "Entitlement",
    "Obligation",
)

REQUIRED_ORGAN_TERMS = ("Member", "Mandate", "Standing", "Standard", "Governance")
PROJECTION_KIND = "vltima.kernel-projection"
PROJECTION_SCHEMA_VERSION = 1
DEFAULT_PROJECTION_PATH = Path("organs/vltima/projection.json")


def _missing_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term.lower() not in text.lower()]


def _load_kernel_registry(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    path = root / "organs" / "vltima" / "kernel.yaml"
    if not path.exists():
        return None, ["organs/vltima/kernel.yaml is missing"]
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:  # noqa: BLE001
        return None, [f"organs/vltima/kernel.yaml is unreadable: {exc}"]
    if not isinstance(data, dict):
        return None, ["organs/vltima/kernel.yaml must contain a mapping"]
    return data, []


def _registry_terms(registry: dict[str, object]) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    errors: list[str] = []
    labels_by_id: dict[str, str] = {}
    layer_ids: dict[str, list[str]] = {}
    layers = registry.get("layers")
    if not isinstance(layers, dict):
        return labels_by_id, layer_ids, ["organs/vltima/kernel.yaml missing layers mapping"]
    for layer_name, raw_items in layers.items():
        if not isinstance(raw_items, list):
            errors.append(f"organs/vltima/kernel.yaml layer {layer_name} must be a list")
            continue
        ids: list[str] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                errors.append(f"organs/vltima/kernel.yaml layer {layer_name}[{index}] must be a mapping")
                continue
            primitive_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
            meaning = str(item.get("meaning") or "").strip()
            if not primitive_id or not label or not meaning:
                errors.append(f"organs/vltima/kernel.yaml layer {layer_name}[{index}] needs id, label, and meaning")
                continue
            if primitive_id in labels_by_id:
                errors.append(f"organs/vltima/kernel.yaml duplicate primitive id: {primitive_id}")
                continue
            labels_by_id[primitive_id] = label
            ids.append(primitive_id)
        layer_ids[str(layer_name)] = ids

    missing = [term for term in REQUIRED_UNIVERSAL_TERMS if term not in labels_by_id.values()]
    if missing:
        errors.append(f"organs/vltima/kernel.yaml missing required primitive(s): {', '.join(missing)}")

    for required_layer in ("lower", "institutional", "value"):
        if required_layer not in layer_ids:
            errors.append(f"organs/vltima/kernel.yaml missing layer: {required_layer}")

    known_ids = set(labels_by_id)
    for layer_name, raw_items in layers.items():
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            primitive_id = str(item.get("id") or "").strip()
            sources = item.get("sources") or []
            if sources and (not isinstance(sources, list) or any(not isinstance(source, str) for source in sources)):
                errors.append(f"organs/vltima/kernel.yaml primitive {primitive_id} sources must be a string list")
                continue
            unknown = [source for source in sources if source not in known_ids]
            if unknown:
                errors.append(
                    f"organs/vltima/kernel.yaml primitive {primitive_id} references unknown source(s): "
                    f"{', '.join(unknown)}"
                )

    projection = registry.get("projection")
    if not isinstance(projection, dict):
        errors.append("organs/vltima/kernel.yaml missing projection mapping")
    else:
        for projection_name, raw_projection in projection.items():
            if not isinstance(raw_projection, list) or any(not isinstance(item, str) for item in raw_projection):
                errors.append(f"organs/vltima/kernel.yaml projection.{projection_name} must be a string list")
                continue
            unknown = [item for item in raw_projection if item not in known_ids]
            if unknown:
                errors.append(
                    f"organs/vltima/kernel.yaml projection.{projection_name} references unknown primitive(s): "
                    + ", ".join(unknown)
                )

        organ_projection = projection.get("organ_kernel")
        if not isinstance(organ_projection, list) or any(not isinstance(item, str) for item in organ_projection):
            errors.append("organs/vltima/kernel.yaml projection.organ_kernel must be a string list")
        else:
            projected_labels = [labels_by_id.get(item, "") for item in organ_projection]
            missing_projected = [term for term in REQUIRED_ORGAN_TERMS if term not in projected_labels]
            if missing_projected:
                errors.append(
                    "organs/vltima/kernel.yaml projection.organ_kernel missing primitive(s): "
                    + ", ".join(missing_projected)
                )

    return labels_by_id, layer_ids, errors


def _load_ladder(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    ladder_path = root / "organ-ladder.json"
    try:
        ladder = json.loads(ladder_path.read_text())
    except Exception as exc:  # noqa: BLE001
        return None, [f"organ-ladder.json is unreadable: {exc}"]
    if not isinstance(ladder, dict):
        return None, ["organ-ladder.json must contain a mapping"]
    return ladder, []


def _primitive_ref(labels_by_id: dict[str, str], primitive_id: str) -> dict[str, str]:
    return {"id": primitive_id, "label": labels_by_id.get(primitive_id, "")}


def _primitive_records(registry: dict[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    layers = registry.get("layers") or {}
    if not isinstance(layers, dict):
        return records
    for layer_name, raw_items in layers.items():
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            primitive_id = str(item.get("id") or "").strip()
            label = str(item.get("label") or "").strip()
            if not primitive_id or not label:
                continue
            sources = item.get("sources") or []
            records.append(
                {
                    "id": primitive_id,
                    "label": label,
                    "layer": str(layer_name),
                    "meaning": str(item.get("meaning") or "").strip(),
                    "sources": list(sources) if isinstance(sources, list) else [],
                }
            )
    return records


def _primitive_edges(primitives: list[dict[str, object]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for primitive in primitives:
        target = str(primitive.get("id") or "")
        for source in primitive.get("sources") or []:
            edges.append({"from": f"primitive:{source}", "to": f"primitive:{target}", "type": "source"})
    return edges


def _graph_payload(
    primitives: list[dict[str, object]],
    projection_map: dict[str, list[dict[str, str]]],
    organs: list[dict[str, object]],
) -> dict[str, object]:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, str]] = []

    layer_ids = sorted({str(primitive.get("layer") or "") for primitive in primitives if primitive.get("layer")})
    for layer_id in layer_ids:
        nodes.append({"id": f"layer:{layer_id}", "kind": "layer", "label": layer_id, "ref": layer_id})

    for primitive in primitives:
        layer_id = str(primitive["layer"])
        nodes.append(
            {
                "id": f"primitive:{primitive['id']}",
                "kind": "primitive",
                "label": primitive["label"],
                "ref": primitive["id"],
                "layer": layer_id,
            }
        )
        edges.append({"from": f"layer:{layer_id}", "to": f"primitive:{primitive['id']}", "type": "contains"})
    edges.extend(_primitive_edges(primitives))

    for projection_name, primitive_refs in projection_map.items():
        projection_id = f"projection:{projection_name}"
        nodes.append({"id": projection_id, "kind": "projection", "label": projection_name, "ref": projection_name})
        for primitive in primitive_refs:
            edges.append({"from": projection_id, "to": f"primitive:{primitive['id']}", "type": "projects"})

    for organ in organs:
        pillar = str(organ.get("pillar") or "")
        organ_id = f"organ:{pillar}"
        nodes.append(
            {
                "id": organ_id,
                "kind": "organ",
                "label": pillar,
                "ref": str(organ.get("home") or ""),
            }
        )
        edges.append({"from": organ_id, "to": "projection:organ_kernel", "type": "implements"})

    return {"nodes": nodes, "edges": edges}


def _organ_kernel_map(organ: dict[str, object], pillar: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    raw = organ.get("kernel_map")
    if not isinstance(raw, dict):
        return {}, [f"{pillar}: organ-ladder.json missing kernel_map"]
    kernel_map: dict[str, str] = {}
    for term in REQUIRED_ORGAN_TERMS:
        value = raw.get(term)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{pillar}: organ-ladder.json kernel_map missing {term}")
        else:
            kernel_map[term] = value.strip()
    extra = sorted(str(key) for key in raw if key not in REQUIRED_ORGAN_TERMS)
    if extra:
        errors.append(f"{pillar}: organ-ladder.json kernel_map unknown primitive(s): {', '.join(extra)}")
    return kernel_map, errors


def _validate_graph(graph: dict[str, object]) -> list[str]:
    errors: list[str] = []
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["vltima graph must contain nodes and edges lists"]
    node_ids: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"vltima graph node[{index}] must be a mapping")
            continue
        node_id = str(node.get("id") or "").strip()
        kind = str(node.get("kind") or "").strip()
        if not node_id or not kind:
            errors.append(f"vltima graph node[{index}] needs id and kind")
            continue
        if node_id in node_ids:
            errors.append(f"vltima graph duplicate node id: {node_id}")
        node_ids.add(node_id)
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"vltima graph edge[{index}] must be a mapping")
            continue
        source = str(edge.get("from") or "").strip()
        target = str(edge.get("to") or "").strip()
        edge_type = str(edge.get("type") or "").strip()
        if not source or not target or not edge_type:
            errors.append(f"vltima graph edge[{index}] needs from, to, and type")
            continue
        if source not in node_ids:
            errors.append(f"vltima graph edge[{index}] references missing source node: {source}")
        if target not in node_ids:
            errors.append(f"vltima graph edge[{index}] references missing target node: {target}")
    return errors


def _validate_projection_contract(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if payload.get("kind") != PROJECTION_KIND:
        errors.append(f"vltima projection kind must be {PROJECTION_KIND!r}")
    if payload.get("schema_version") != PROJECTION_SCHEMA_VERSION:
        errors.append(f"vltima projection schema_version must be {PROJECTION_SCHEMA_VERSION}")
    for key in ("primitives", "edges", "layers", "projections", "organs"):
        if key not in payload:
            errors.append(f"vltima projection missing key: {key}")
    primitives = payload.get("primitives")
    if not isinstance(primitives, list) or not primitives:
        errors.append("vltima projection primitives must be a non-empty list")
    organs = payload.get("organs")
    if not isinstance(organs, list) or not organs:
        errors.append("vltima projection organs must be a non-empty list")
    graph = payload.get("graph")
    if not isinstance(graph, dict):
        errors.append("vltima projection graph must be a mapping")
    else:
        errors.extend(_validate_graph(graph))
    return errors


def build_projection(root: Path) -> tuple[dict[str, object] | None, list[str]]:
    registry, errors = _load_kernel_registry(root)
    if registry is None:
        return None, errors
    labels_by_id, layer_ids, term_errors = _registry_terms(registry)
    errors.extend(term_errors)
    ladder, ladder_errors = _load_ladder(root)
    errors.extend(ladder_errors)
    if errors or ladder is None:
        return None, errors

    projection = registry.get("projection") or {}
    projection_map = {
        name: [_primitive_ref(labels_by_id, primitive_id) for primitive_id in ids]
        for name, ids in projection.items()
        if isinstance(ids, list)
    }
    primitives = _primitive_records(registry)

    organs: list[dict[str, object]] = []
    seen_homes: set[str] = set()
    for organ in ladder.get("organs") or []:
        if not isinstance(organ, dict):
            continue
        pillar = str(organ.get("pillar") or "")
        home = str(organ.get("home") or "")
        if not home or home in seen_homes:
            continue
        seen_homes.add(home)
        kernel_map, map_errors = _organ_kernel_map(organ, pillar or "<missing-pillar>")
        errors.extend(map_errors)
        organs.append(
            {
                "pillar": pillar,
                "home": home,
                "domain_map": str(organ.get("domain_map") or ""),
                "kernel_map": kernel_map,
                "macro": str(organ.get("macro") or ""),
                "micro": str(organ.get("micro") or ""),
                "first_artifact": str(organ.get("first_artifact") or ""),
                "organ_kernel": projection_map.get("organ_kernel", []),
            }
        )
    if errors:
        return None, errors

    primitive_edges = [
        {"from": edge["from"].removeprefix("primitive:"), "to": edge["to"].removeprefix("primitive:"), "type": edge["type"]}
        for edge in _primitive_edges(primitives)
    ]
    graph = _graph_payload(primitives, projection_map, organs)
    graph_errors = _validate_graph(graph)
    if graph_errors:
        return None, graph_errors

    payload = {
        "kind": PROJECTION_KIND,
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "version": registry.get("version"),
        "primitives": primitives,
        "edges": primitive_edges,
        "layers": {
            layer_name: [_primitive_ref(labels_by_id, primitive_id) for primitive_id in ids]
            for layer_name, ids in layer_ids.items()
        },
        "projections": projection_map,
        "organs": organs,
        "graph": graph,
    }
    contract_errors = _validate_projection_contract(payload)
    if contract_errors:
        return None, contract_errors
    return payload, []


def projection_json_text(projection: dict[str, object]) -> str:
    return json.dumps(projection, indent=2, sort_keys=True) + "\n"


def _projection_path(root: Path, raw_path: Path | None) -> Path:
    path = raw_path or DEFAULT_PROJECTION_PATH
    return path if path.is_absolute() else root / path


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    registry, registry_errors = _load_kernel_registry(root)
    errors.extend(registry_errors)
    labels_by_id: dict[str, str] = {}
    layer_ids: dict[str, list[str]] = {}
    if registry:
        labels_by_id, layer_ids, registry_term_errors = _registry_terms(registry)
        errors.extend(registry_term_errors)
    universal_terms = tuple(labels_by_id.values()) if labels_by_id else REQUIRED_UNIVERSAL_TERMS
    organ_terms = tuple(labels_by_id[item] for item in layer_ids.get("institutional", []) if item in labels_by_id)
    if not organ_terms:
        organ_terms = REQUIRED_ORGAN_TERMS

    kernel = root / "organs" / "vltima" / "KERNEL.md"
    if not kernel.exists():
        errors.append("organs/vltima/KERNEL.md is missing")
    else:
        missing = _missing_terms(kernel.read_text(), universal_terms)
        if missing:
            errors.append(f"organs/vltima/KERNEL.md is missing term(s): {', '.join(missing)}")

    ladder, ladder_errors = _load_ladder(root)
    if ladder_errors:
        return errors + ladder_errors
    assert ladder is not None

    seen_homes: set[str] = set()
    for organ in ladder.get("organs") or []:
        if not isinstance(organ, dict):
            continue
        pillar = str(organ.get("pillar") or "<missing-pillar>")
        home = str(organ.get("home") or "")
        if not home or home in seen_homes:
            continue
        seen_homes.add(home)

        for field in ("domain_map", "macro", "micro", "first_artifact"):
            if not str(organ.get(field) or "").strip():
                errors.append(f"{pillar}: organ-ladder.json missing {field}")
        _, map_errors = _organ_kernel_map(organ, pillar)
        errors.extend(map_errors)

        organ_kernel = root / home / "KERNEL.md"
        if not organ_kernel.exists():
            errors.append(f"{pillar}: {home}KERNEL.md is missing")
            continue
        text = organ_kernel.read_text()
        missing = _missing_terms(text, organ_terms)
        if missing:
            errors.append(f"{pillar}: {home}KERNEL.md missing primitive(s): {', '.join(missing)}")
        if "macro" not in text.lower():
            errors.append(f"{pillar}: {home}KERNEL.md missing MACRO deployment")
        if "micro" not in text.lower():
            errors.append(f"{pillar}: {home}KERNEL.md missing MICRO deployment")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json-output", action="store_true", help="Emit the derived kernel projection as JSON.")
    parser.add_argument(
        "--write-projection",
        action="store_true",
        help="Write the canonical derived projection to organs/vltima/projection.json.",
    )
    parser.add_argument(
        "--check-projection",
        action="store_true",
        help="Fail if the canonical derived projection file is missing or stale.",
    )
    parser.add_argument(
        "--projection-path",
        type=Path,
        default=None,
        help="Override the projection path for --write-projection/--check-projection.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    errors = validate(root)
    if errors:
        print(f"vltima-kernel: blocked with {len(errors)} issue(s)", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    projection = None
    if args.json_output or args.write_projection or args.check_projection:
        projection, projection_errors = build_projection(root)
        if projection_errors:
            print(f"vltima-kernel: blocked with {len(projection_errors)} issue(s)", file=sys.stderr)
            for error in projection_errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        assert projection is not None
        expected = projection_json_text(projection)
        projection_path = _projection_path(root, args.projection_path)

        if args.write_projection:
            projection_path.parent.mkdir(parents=True, exist_ok=True)
            projection_path.write_text(expected)
            if not args.quiet and not args.json_output:
                print(f"vltima-kernel: wrote projection to {_display_path(root, projection_path)}")

        if args.check_projection:
            if not projection_path.exists():
                print(
                    f"vltima-kernel: projection missing: {_display_path(root, projection_path)} "
                    "(run --write-projection)",
                    file=sys.stderr,
                )
                return 1
            actual = projection_path.read_text()
            if actual != expected:
                print(
                    f"vltima-kernel: projection stale: {_display_path(root, projection_path)} "
                    "(run --write-projection)",
                    file=sys.stderr,
                )
                return 1
            if not args.quiet and not args.json_output:
                print(f"vltima-kernel: projection current at {_display_path(root, projection_path)}")

        if args.json_output:
            sys.stdout.write(expected)
        return 0

    if not args.quiet:
        print("vltima-kernel: universal kernel and organ projections valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
