#!/usr/bin/env python3
"""Validate union-merged parameters.yaml and sensors.yaml for the H branch: parse, no markers, no dup keys."""

import re
import sys

import yaml


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


class DupCheckLoader(yaml.SafeLoader):
    pass


def no_dup_mapping(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    hashable = [k for k in keys if isinstance(k, (str, int, float, bool, tuple))]
    dupes = {k for k in hashable if hashable.count(k) > 1}
    if dupes:
        raise ValueError(f"duplicate keys: {sorted(map(str, dupes))[:10]}")
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


DupCheckLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_dup_mapping)

for path, kind in ((".union-params.yaml", "parameters"), (".union-sensors.yaml", "sensors")):
    text = open(path, encoding="utf-8").read()
    if re.search(r"^(<<<<<<<|=======$|>>>>>>>)", text, re.M):
        fail(f"{path}: conflict markers present")
    doc = yaml.load(text, Loader=DupCheckLoader)
    if kind == "parameters":
        params = doc.get("parameters") or {}
        print(f"{path}: OK — {len(params)} parameters")
        for want in ("LIMEN_WORK_LOAN_BACKFILL", "LIMEN_OWNER_ROUTE_DRAIN"):
            if want not in params:
                fail(f"{path}: expected main-side key {want} missing")
    else:
        sensors = doc.get("sensors") or {}
        if isinstance(sensors, list):
            ids = [s.get("id") for s in sensors]
            if len(ids) != len(set(ids)):
                fail(f"{path}: duplicate sensor ids")
            count = len(ids)
        else:
            count = len(sensors)
        print(f"{path}: OK — {count} sensors")
print("UNION-VALID")
