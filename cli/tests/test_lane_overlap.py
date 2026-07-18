"""Unit tests for the entry-level classifier in ``scripts/lane-overlap.py``.

The predicate's git/gh fan-out is exercised live against real estate; here we pin the *pure* core — the
registry-shape gate (``_registry_entries``), the diff key-extractor (``_touched_keys_from_patch``), and
the split (``_classify_shared``) — because that is where the fence-vs-wall distinction lives. Two lanes
appending DISTINCT keyed entries to a registry must read as a clean union (SOFT); a shared entry, a
non-registry file, or an unreadable/empty patch must fail CLOSED (HARD).

The classifier reads each lane's OWN diff (vs its merge-base) rather than diffing file contents against
the moving tip — so a stale branch's base drift can't masquerade as a change. These tests feed synthetic
patches directly, so they need no git state. The module is loaded by path (hyphenated filename).
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_lane_overlap():
    spec = importlib.util.spec_from_file_location("lane_overlap", ROOT / "scripts" / "lane-overlap.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lo = _load_lane_overlap()


# A minimal registry in the VIGILIA shape: a ``schema_version:`` scalar + ONE keyed collection.
def _registry(*keys: str) -> str:
    body = "\n".join(f"  {k}:\n    title: entry {k}\n    default: '1'" for k in keys)
    return f"schema_version: 0.2\nsensors:\n{body}\n"


# Synthetic unified-diff hunks (what a lane's own diff of the registry looks like).
def _add_entry_patch(key: str) -> str:
    return (
        "@@ -20,3 +20,6 @@ sensors:\n"
        "   existing:\n"
        "     title: entry existing\n"
        f"+  {key}:\n"
        f"+    title: entry {key}\n"
        "+    default: '1'\n"
    )


def _change_field_patch(key: str) -> str:
    return f"@@ -20,4 +20,4 @@ sensors:\n   {key}:\n     title: entry existing\n-    default: '1'\n+    default: '2'\n"


# ── _registry_entries: the registry-shape gate (recognizes the shape, refuses anything else) ───────


def test_registry_entries_extracts_the_collection_keys():
    entries = lo._registry_entries(_registry("a", "b"))
    assert entries is not None
    assert set(entries) == {"a", "b"}


def test_registry_entries_is_none_for_non_registry_yaml():
    assert lo._registry_entries("just: a scalar\n") is None  # zero mapping-valued top keys
    assert lo._registry_entries("- one\n- two\n") is None  # top-level list, not a mapping
    assert lo._registry_entries("def f():\n    return 1\n") is None  # not YAML-mapping shaped


def test_registry_entries_is_none_for_unparseable_yaml():
    assert lo._registry_entries("key: [unterminated\n") is None


def test_registry_entries_is_none_when_two_collections_present():
    # Ambiguous shape ⇒ we cannot say which is "the" keyed collection ⇒ fail-closed None.
    two = "schema_version: 0.2\nsensors:\n  a: {title: x}\ngates:\n  g: {title: y}\n"
    assert lo._registry_entries(two) is None


# ── _touched_keys_from_patch: which entries a lane's own diff touched ──────────────────────────────


def test_added_entry_key_is_captured():
    assert lo._touched_keys_from_patch(_add_entry_patch("newsensor")) == {"newsensor"}


def test_changed_nested_field_attributes_to_its_parent_entry():
    assert lo._touched_keys_from_patch(_change_field_patch("existing")) == {"existing"}


def test_removed_entry_key_is_captured():
    patch = "@@ -20,4 +20,1 @@ sensors:\n-  gone:\n-    title: entry gone\n-    default: '1'\n"
    assert lo._touched_keys_from_patch(patch) == {"gone"}


def test_unrecognizable_or_empty_patch_yields_no_keys():
    assert lo._touched_keys_from_patch("") == set()
    assert lo._touched_keys_from_patch("@@ -1 +1 @@\n-nonsense\n+garbage\n") == set()


# ── _classify_shared: distinct entries SOFT; shared entry / non-registry / empty HARD (fail-closed) ─


def _classify(base_text, target_patch, other_patch, path="institutio/governance/sensors.yaml"):
    # Pre-seed base_cache so _classify_shared's _base_file_text call stays pure (no git shell-out).
    base_cache = {path: base_text}
    return lo._classify_shared([path], lambda f: target_patch, lambda f: other_patch, base_cache)


def test_distinct_added_entries_are_soft():
    hard, soft = _classify(_registry("existing"), _add_entry_patch("alpha"), _add_entry_patch("beta"))
    assert hard == []
    assert soft == ["institutio/governance/sensors.yaml"]


def test_same_added_entry_is_hard():
    hard, soft = _classify(_registry("existing"), _add_entry_patch("dup"), _add_entry_patch("dup"))
    assert soft == []
    assert hard == ["institutio/governance/sensors.yaml"]


def test_disjoint_add_and_field_change_are_soft():
    hard, soft = _classify(_registry("existing"), _add_entry_patch("alpha"), _change_field_patch("existing"))
    assert soft == ["institutio/governance/sensors.yaml"]
    assert hard == []


def test_non_registry_base_is_hard_regardless_of_patches():
    # A shared *code* file can never be proven a clean union ⇒ HARD even with disjoint-looking patches.
    hard, soft = _classify("x = 1\n", "+a = 2\n", "+b = 3\n", path="scripts/session-orient.py")
    assert hard == ["scripts/session-orient.py"]
    assert soft == []


def test_empty_or_unreadable_patch_side_is_hard():
    assert _classify(_registry("existing"), "", _add_entry_patch("beta"))[0] == [
        "institutio/governance/sensors.yaml"
    ]  # empty target patch
    base_cache = {"institutio/governance/sensors.yaml": _registry("existing")}
    hard, soft = lo._classify_shared(
        ["institutio/governance/sensors.yaml"],
        lambda f: None,  # target patch unfetchable ⇒ HARD, never SOFT
        lambda f: _add_entry_patch("beta"),
        base_cache,
    )
    assert hard == ["institutio/governance/sensors.yaml"]
    assert soft == []
