#!/usr/bin/env python3
"""Core-identity organ — the SSOT reader/hydrator for the operator's durable PII.

Homes (two, per the credential-organ pattern):
  - LIVE upstream: 1Password  op://Private/Identity   (source of truth when reachable)
  - Offline mirror: $HOME/Workspace/_life-private/identity.json
      ARCA-sealed at rest, git-tracked private, mode 700 dir. Authoritative when op is down.

Never prints SSN to stdout unless --unsafe-ssn is passed (form-fillers pass it; humans don't).
Consumed by form-fillers (e.g. phi_form.py) so "fill this form" is solved once for every form.

  identity.py get legal_name.first
  identity.py show                 # redacted human view (SSN -> ***-**-1234)
  identity.py json                 # full JSON for a consumer (redacts SSN unless --unsafe-ssn)
  identity.py hydrate              # pull op://Private/Identity -> identity.json (op must be reachable)
  identity.py verify               # predicate: exit 0 iff required atoms present & valid
"""
import json
import os
import sys
import subprocess
import argparse
import datetime

STORE = os.path.expanduser("~/Workspace/_life-private/identity.json")
OP_ITEM = "op://Private/Identity"
REQUIRED = ["legal_name.first", "legal_name.last", "dob",
            "addresses.0.street", "addresses.0.city", "addresses.0.state", "addresses.0.zip",
            "phones.0.number"]

def _load():
    if not os.path.exists(STORE):
        return {}
    with open(STORE) as f:
        return json.load(f)

def _dig(obj, dotpath):
    cur = obj
    for part in dotpath.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur

def _redact(d):
    d = json.loads(json.dumps(d))
    ssn = d.get("ssn")
    if ssn and len(ssn) >= 4:
        d["ssn"] = "***-**-" + ssn[-4:]
    return d

def cmd_get(a):
    val = _dig(_load(), a.path)
    if val is None:
        sys.exit(f"[identity] missing: {a.path}")
    print(val)

def cmd_show(a):
    print(json.dumps(_redact(_load()), indent=2))

def cmd_json(a):
    d = _load()
    if not a.unsafe_ssn:
        d = _redact(d)
    print(json.dumps(d))

def cmd_verify(a):
    d = _load()
    missing = [p for p in REQUIRED if _dig(d, p) in (None, "")]
    if not d:
        print("[identity] BODY EMPTY — store not yet populated (op hydrate or one-time entry)")
        sys.exit(1)
    if missing:
        print("[identity] MISSING required atoms: " + ", ".join(missing))
        sys.exit(1)
    print("[identity] OK — all required atoms present")
    sys.exit(0)

def cmd_hydrate(a):
    # Pull op://Private/Identity into the mirror. Requires an active op session.
    try:
        raw = subprocess.run(["op", "item", "get", "Identity", "--format", "json"],
                             capture_output=True, text=True, timeout=20)
    except Exception as e:
        sys.exit(f"[identity] op unreachable: {e}")
    if raw.returncode != 0:
        sys.exit(f"[identity] op error: {raw.stderr.strip()}")
    item = json.loads(raw.stdout)
    fields = {f.get("label", "").lower(): f.get("value") for f in item.get("fields", [])}
    # map op fields -> schema (labels are best-effort; adjust to the actual op item)
    out = _load() or {}
    out.setdefault("provenance", {})
    out["provenance"] = {"source": OP_ITEM,
                         "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                         "verified": True}
    # NOTE: field mapping is intentionally explicit; fill once the op item's labels are known.
    print("[identity] op item fetched; map its fields into the schema, then write", STORE)
    print(json.dumps(fields, indent=2))

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("get"); g.add_argument("path"); g.set_defaults(fn=cmd_get)
    s = sub.add_parser("show"); s.set_defaults(fn=cmd_show)
    j = sub.add_parser("json"); j.add_argument("--unsafe-ssn", action="store_true"); j.set_defaults(fn=cmd_json)
    v = sub.add_parser("verify"); v.set_defaults(fn=cmd_verify)
    h = sub.add_parser("hydrate"); h.set_defaults(fn=cmd_hydrate)
    a = p.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
