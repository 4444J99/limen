#!/usr/bin/env python3
"""Core-identity / personal-fact organ — the reader that DERIVES everything from one registry.

The single owner is `institutio/governance/personal-facts.yaml`. This tool reads it; it does not
carry its own copy of what facts exist, where they live, which are required, or how they verify.
That is the whole point: a fact a consumer needs but the registry doesn't home is a RED build
(check-personal-facts.py / fact-wall.py), never a chat ask.

Homes are two, per the credential-organ precedent (credentials rotate, identity doesn't -> separate lane):
  - Sensible atoms (name/DOB/address/phone/emails): ARCA-sealed files under ~/Workspace/_*-private.
  - Crown-jewels (full SSN/bank/passport): op:// ONLY, never at rest; disk keeps a `shadow` digest.
    The beat verifies the shadow (shadow_present) — it NEVER does a silent `op read`, which this
    estate cannot do unattended (no service-account token -> op_can_read_silently() is False).

  identity.py get <class-id|store.dotpath>   # one value (redacts crown-jewels)
  identity.py show                           # human view of the identity store (crown-jewels masked)
  identity.py json [--unsafe-ssn]            # identity store as JSON for a consumer
  identity.py verify                         # PREDICATE: every applicable&required atom present + single-home intact
  identity.py reconcile                      # PREDICATE: every referenced_by citation is a member of the owned set
  identity.py need <class-id>                # resolve, or surface an un-homed class (dry-run; LIMEN_FACTS_APPLY=1 writes)
  identity.py hydrate                        # pull op:// crown-jewels/identity into the mirror (op must be reachable)
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(REPO, "institutio", "governance", "personal-facts.yaml")
WORKSPACE = os.environ.get("LIMEN_WORKSPACE", os.path.expanduser("~/Workspace"))  # override for tests
STORE = os.path.join(WORKSPACE, "_life-private", "identity.json")   # the identity domain store
OP_IDENTITY_ITEM = "op://Private/Identity"

_HOME_CACHE = {}


def _registry():
    with open(REGISTRY) as f:
        return (yaml.safe_load(f) or {}).get("facts", {})


def _home_path(home):
    """Resolve a fact's `home` to an absolute path (op:// homes have no at-rest path)."""
    if home.startswith("op://"):
        return None
    return os.path.join(WORKSPACE, home)


def _load_home(home):
    """Load a home JSON file once (cached). Missing/other-shaped home -> {}."""
    path = _home_path(home)
    if path is None:
        return {}
    if path in _HOME_CACHE:
        return _HOME_CACHE[path]
    data = {}
    if os.path.isfile(path):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    _HOME_CACHE[path] = data
    return data


def _load_store():
    if os.path.isfile(STORE):
        with open(STORE) as f:
            return json.load(f)
    return {}


def _dig(obj, dotpath):
    cur = obj
    for part in dotpath.split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "") or v == [] or v == {}


def _redact(d):
    """Mask any crown-jewel value that somehow sits in the store, plus a defensive literal `ssn` key."""
    d = json.loads(json.dumps(d))

    def mask(val):
        s = str(val)
        return ("***-**-" + s[-4:]) if len(s) >= 4 else "****"

    # defensive: a raw ssn must never survive to output (the store keeps ssn_last4 only)
    if not _is_blank(d.get("ssn")):
        d["ssn"] = mask(d["ssn"])
    return d


# ── single-home reference-integrity (the SINGLE-HOME rule, made executable) ───

def _owned_set(f):
    """The full set of values a class owns at its home (the array parent of its atom), lowercased.
    `emails.0` -> the whole `emails` array. op:// homes have no at-rest set -> None."""
    home = f.get("home", "")
    if home.startswith("op://"):
        return None
    atom = f.get("atom", "")
    tail = atom.rsplit(".", 1)[-1]
    parent = atom.rsplit(".", 1)[0] if (tail.isdigit() and "." in atom) else atom
    val = _dig(_load_home(home), parent)
    if isinstance(val, list):
        return {str(x).strip().lower() for x in val if not _is_blank(x)}
    if not _is_blank(val):
        return {str(val).strip().lower()}
    return set()


def _reference_integrity():
    """SINGLE-HOME membership: every value a `referenced_by` store cites must be in the owned set.
    Returns redacted strings (class + store + COUNT — never the cited value). Skips a class whose
    owned set is empty (that is the populate gap, surfaced by verify) and a store not present on disk
    (CI / a machine without the ARCA store) — so this never false-fails where it cannot see data."""
    out = []
    for cid, f in _registry().items():
        refs = f.get("referenced_by") or []
        if not refs:
            continue
        owned = _owned_set(f)
        if not owned:                         # nothing to reconcile against -> not this check's job
            continue
        for ref in refs:
            store = ref.get("store", "")
            items = _dig(_load_home(store), ref.get("collection", ""))
            if not isinstance(items, list):
                continue
            field = ref.get("field", "")
            strays = sum(
                1 for it in items
                if isinstance(it, dict) and not _is_blank(it.get(field))
                and str(it.get(field)).strip().lower() not in owned
            )
            if strays:
                out.append(f"{cid}: {strays} {field}(s) in {store} not owned by {cid}")
    return out


# ── commands ────────────────────────────────────────────────────────────────

def cmd_get(a):
    facts = _registry()
    if a.path in facts:                       # a class-id -> resolve via its home/atom
        f = facts[a.path]
        home = f["home"]
        if home.startswith("op://"):
            print(f"[identity] {a.path} is crown-jewel (op-only): {home}; shadow={f.get('shadow')}")
            return
        val = _dig(_load_home(home), f["atom"])
        if _is_blank(val):
            sys.exit(f"[identity] blank/missing: {a.path} ({home}:{f['atom']})")
        if f.get("tier") == "crown-jewel":
            val = "***-**-" + str(val)[-4:]
        print(val)
        return
    val = _dig(_load_store(), a.path)          # or a raw store dotpath
    if _is_blank(val):
        sys.exit(f"[identity] missing: {a.path}")
    print(val)


def cmd_show(a):
    print(json.dumps(_redact(_load_store()), indent=2))


def cmd_json(a):
    d = _load_store()
    if not a.unsafe_ssn:
        d = _redact(d)
    print(json.dumps(d))


def cmd_verify(a):
    facts = _registry()
    checked = 0
    missing = []
    for cid, f in facts.items():
        if not (f.get("applicable") is True and f.get("required") is True):
            continue
        checked += 1
        mode = f.get("verify", "non_empty")
        home = f.get("home", "")
        if mode == "non_empty":
            if _is_blank(_dig(_load_home(home), f["atom"])):
                missing.append(f"{cid} ({home}:{f['atom']})")
        elif mode == "shadow_present":
            if _is_blank(_dig(_load_home(home), f.get("shadow", f.get("atom")))):
                missing.append(f"{cid} (shadow {f.get('shadow')})")
        elif mode == "pointer_resolves":
            path = _home_path(home)
            if not (path and os.path.exists(path)):
                missing.append(f"{cid} (pointer {home})")
    strays = _reference_integrity()
    if missing or strays:
        if missing:
            print(f"[identity] MISSING {len(missing)}/{checked} required atoms: " + ", ".join(missing))
            print("[identity]   -> one-time populate (op hydrate or entry); see lever L-IDENTITY-POPULATE")
        if strays:
            print("[identity] REFERENCE-INTEGRITY drift (single-home): " + "; ".join(strays))
            print("[identity]   -> add the cited value to its owner class, or fix the citing store")
        sys.exit(1)
    print(f"[identity] OK — all {checked} applicable&required atoms present; single-home intact")
    sys.exit(0)


def cmd_reconcile(a):
    strays = _reference_integrity()
    if strays:
        print("[identity] REFERENCE-INTEGRITY drift (single-home): " + "; ".join(strays))
        print("[identity]   -> add the cited value to its owner class (owner is incomplete), or fix the citing store")
        sys.exit(1)
    print("[identity] OK — every referenced_by citation is owned (single-home intact)")
    sys.exit(0)


def cmd_need(a):
    """Resolve a class, or surface an un-homed one. Dry-run by default; LIMEN_FACTS_APPLY=1 appends a pending row."""
    facts = _registry()
    if a.klass in facts:
        f = facts[a.klass]
        home = f["home"]
        if home.startswith("op://"):
            print(f"[identity] {a.klass}: crown-jewel, resolve via op_read at fill-time ({home})")
        else:
            val = _dig(_load_home(home), f["atom"])
            state = "present" if not _is_blank(val) else "HOMED-but-empty (populate once)"
            print(f"[identity] {a.klass}: homed at {home}:{f['atom']} — {state}")
        return
    # un-homed: surface it (never a chat ask). Class-NAME only; no value ever written from here.
    pending = {"domain": "UNKNOWN", "home": "TBD", "atom": a.klass.split(".")[-1],
               "tier": "sensitive", "applicable": "unknown", "required": False, "verify": "non_empty",
               "consumers": []}
    print(f"[identity] UN-HOMED class '{a.klass}' — needs one registry row:")
    print(yaml.safe_dump({a.klass: pending}, sort_keys=False, default_flow_style=False))
    if os.environ.get("LIMEN_FACTS_APPLY") == "1":
        reg = yaml.safe_load(open(REGISTRY)) or {"facts": {}}
        reg.setdefault("facts", {})[a.klass] = pending
        with open(REGISTRY, "w") as f:
            yaml.safe_dump(reg, f, sort_keys=False, default_flow_style=False)
        print(f"[identity]   -> appended pending row to {REGISTRY}; file L-FACT lever next beat")
    else:
        print("[identity]   -> dry-run (set LIMEN_FACTS_APPLY=1 to append the pending row)")
    sys.exit(2)


def cmd_hydrate(a):
    """Pull the op://Private/Identity item into the mirror. Requires an active op session (interactive)."""
    try:
        raw = subprocess.run(["op", "item", "get", "Identity", "--format", "json"],
                             capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        sys.exit(f"[identity] op unreachable: {e}")
    if raw.returncode != 0:
        sys.exit(f"[identity] op error: {raw.stderr.strip()}")
    item = json.loads(raw.stdout)
    fields = {f.get("label", "").lower(): f.get("value") for f in item.get("fields", [])}
    print(f"[identity] op item fetched ({len(fields)} fields); map into {STORE} then reseal (ARCA).")
    print("[identity] provenance:", json.dumps(
        {"source": OP_IDENTITY_ITEM, "updated_at": datetime.date.today().isoformat()}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("get"); g.add_argument("path"); g.set_defaults(fn=cmd_get)
    s = sub.add_parser("show"); s.set_defaults(fn=cmd_show)
    j = sub.add_parser("json"); j.add_argument("--unsafe-ssn", action="store_true"); j.set_defaults(fn=cmd_json)
    v = sub.add_parser("verify"); v.set_defaults(fn=cmd_verify)
    r = sub.add_parser("reconcile"); r.set_defaults(fn=cmd_reconcile)
    n = sub.add_parser("need"); n.add_argument("klass"); n.set_defaults(fn=cmd_need)
    h = sub.add_parser("hydrate"); h.set_defaults(fn=cmd_hydrate)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
