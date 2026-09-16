#!/usr/bin/env python3
"""creds-provision.py — CLAVIS, the credential-PROVISIONING organ.

The sibling of creds-hydrate.py (the CONSUMER): where creds-hydrate READS secrets from 1Password
into ~/.limen.env, creds-provision OWNS the upstream that makes those reads possible — the fleet
service account and the ONE vault it reads. It closes the gap the operator named: credential
provisioning must live in a repo, controlled as code, not as a manual 1Password-console click.

THE INVARIANT (institutio/governance/credentials.yaml): a 1Password service account's vault access
is IMMUTABLE (set at creation). You cannot add a vault to a live SA. So the only stable shape is a
SINGLE SA-owned vault holding every fleet secret. This organ:

  check      the forever-PREDICATE. Every enabled, op-sourced, REQUIRED secret in creds-hydrate's
             DEFAULT_MAP must resolve to an SA-readable vault (per the policy). Exit 1 if any does
             not — so a starved credential is LOUD in the beat log, never a silent green. Read-only.

  bootstrap  establish the automation vault and service-account custody using the owner session.
             Read back canonical custody and exact vault scope before replacing the local token;
             preserve its predecessor. Source-item migration and account retirement are separate.

  apply      idempotent conformance (dry-run by default; --apply executes): ensure every op-sourced
             secret lives in the automation vault. Because the SA OWNS that vault, adding a secret is
             a create/move IN the vault — never a re-grant (which 1Password forbids on a live SA).

Never prints provider output or secret values. Bootstrap fails closed and uses the existing
owner session only on explicit --apply; dry-run never contacts 1Password.
"""

from __future__ import annotations

import argparse
import fcntl
import tempfile
import importlib.util
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY_PATH = Path(os.getenv("LIMEN_CREDS_POLICY", HERE.parent / "institutio" / "governance" / "credentials.yaml"))
HYDRATE_PATH = HERE / "creds-hydrate.py"

# Policy defaults — used if credentials.yaml is unreadable (fail toward caution: no vault is
# SA-readable, so every op-sourced secret reports as an outlier rather than a false green).
_POLICY_DEFAULTS = {
    "automation_vault": "Limen-Automation",
    "sa_readable_vaults": ["Limen-Automation"],
    "service_account": {
        "name": "limen-fleet",
        "token_file": "~/.config/op/service-account-token",
        "create_flags": "--vault Limen-Automation:read_items,write_items --can-create-vaults",
    },
    "policy": {"required_must_be_sa_readable": True, "warn_on_nonrequired_outliers": True, "derive_exempt": True},
    "bootstrap": {"wall_issue": 320, "supersedes_inert_sa": True},
}


def _scrub(s: str) -> str:
    """Redact anything op-token / secret shaped so a value can never reach a log."""
    s = re.sub(r"ops_[A-Za-z0-9+/_=-]{20,}", "ops_***", s or "")
    s = re.sub(r"eyJ[A-Za-z0-9._-]{20,}", "eyJ***", s)
    return s


def load_policy(*, strict: bool = False) -> dict:
    """Read credentials.yaml. Fail-open to the caution defaults if PyYAML/file is unavailable."""
    try:
        import yaml  # noqa: PLC0415 — optional; defaults cover its absence

        data = yaml.safe_load(POLICY_PATH.read_text()) or {}
    except Exception:
        if strict:
            raise ValueError("credential policy unavailable") from None
        return dict(_POLICY_DEFAULTS)
    merged = dict(_POLICY_DEFAULTS)
    merged.update({k: v for k, v in data.items() if v is not None})
    return merged


def load_cred_map() -> list[dict]:
    """The per-secret registry. LIMEN_CREDS_MAP (JSON) overrides for tests; else import DEFAULT_MAP
    from creds-hydrate.py (the single in-code source — never duplicated here)."""
    override = os.getenv("LIMEN_CREDS_MAP")
    if override:
        try:
            return json.loads(Path(override).read_text()) if os.path.exists(override) else json.loads(override)
        except Exception:
            return []
    spec = importlib.util.spec_from_file_location("creds_hydrate_for_provision", HYDRATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(getattr(mod, "DEFAULT_MAP", []))


def vault_of(ref: str) -> str | None:
    """op://<vault>/<item>/<field> -> <vault>. None if not an op:// ref."""
    m = re.match(r"op://([^/]+)/", ref or "")
    return m.group(1) if m else None


# Classification of a DEFAULT_MAP entry against the policy.
#  parked         — enabled: False (ignored)
#  derive_exempt  — has a `derive` (keyless keyring source); op vault access not required
#  no_ref         — no op:// ref (nothing to home)
#  sa_readable    — op-sourced and its vault is SA-readable (conformant)
#  outlier        — op-sourced and its vault is NOT SA-readable (needs migration)
def classify(entry: dict, policy: dict) -> str:
    if not entry.get("enabled", True):
        return "parked"
    ref = entry.get("ref")
    if entry.get("derive") and policy["policy"].get("derive_exempt", True):
        return "derive_exempt"
    if not ref:
        return "no_ref"
    v = vault_of(ref)
    return "sa_readable" if v in set(policy.get("sa_readable_vaults", [])) else "outlier"


def cmd_check(policy: dict, cred_map: list[dict]) -> int:
    """The forever-predicate. Exit 1 iff a REQUIRED op-sourced secret is not SA-readable."""
    av = policy.get("automation_vault")
    print(
        f"creds-provision --check — SA-readable vault(s): {policy.get('sa_readable_vaults')}  (automation vault: {av})"
    )
    hard_fail = False
    counts = {"sa_readable": 0, "outlier": 0, "derive_exempt": 0, "no_ref": 0, "parked": 0}
    for e in cred_map:
        kind = classify(e, policy)
        counts[kind] += 1
        if kind == "outlier":
            required = bool(e.get("required"))
            src_vault = vault_of(e.get("ref", ""))
            if required and policy["policy"].get("required_must_be_sa_readable", True):
                hard_fail = True
                print(
                    f"  ✗ {e.get('lane', '?'):32} REQUIRED but in vault '{src_vault}' — NOT SA-readable "
                    f"(migrate → {av}: `creds-provision bootstrap`)"
                )
            elif policy["policy"].get("warn_on_nonrequired_outliers", True):
                print(f"  ! {e.get('lane', '?'):32} in vault '{src_vault}' — migration pending → {av}")
        elif kind == "sa_readable":
            print(f"  ✓ {e.get('lane', '?'):32} SA-readable ({vault_of(e.get('ref', ''))})")
    print(
        f"  ── {counts['sa_readable']} SA-homed · {counts['outlier']} outlier · "
        f"{counts['derive_exempt']} derive-exempt · {counts['parked']} parked"
    )
    if hard_fail:
        print(
            "creds-provision: ✗ a REQUIRED secret is not readable by the fleet service account. "
            "The estate is not yet SA-homed — run `creds-provision bootstrap` (one owner-op step, "
            "Wall #320). The predicate stays red until every required secret lives in the "
            f"'{av}' vault."
        )
        return 1
    print("creds-provision: ✓ every required op-sourced secret is SA-readable.")
    return 0


class ProvisionError(RuntimeError):
    """A bounded bootstrap step failed; never include provider output or secrets."""


def _owner_environment() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("OP_SERVICE_ACCOUNT_TOKEN", "OP_CONNECT_HOST", "OP_CONNECT_TOKEN", "OP_BIOMETRIC_UNLOCK_ENABLED"):
        env.pop(key, None)
    return env


def _op(args: list[str], env: dict[str, str], *, payload: str | None = None) -> str:
    try:
        result = subprocess.run(["op", *args], input=payload, capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        raise ProvisionError("op invocation unavailable or ambiguous; reconcile before retry") from None
    if result.returncode:
        raise ProvisionError("op rejected the step; later mutations were not attempted")
    return result.stdout


def _private_create(path: Path, value: str) -> None:
    """Exclusive custody: a pending credential is never overwritten by another run."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _read_private(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ProvisionError("credential custody path is not a private regular file")
    return path.read_text().strip()


def _migration_plan(policy: dict, cred_map: list[dict]) -> None:
    seen = set()
    for entry in cred_map:
        if classify(entry, policy) != "outlier":
            continue
        ref = entry.get("ref", "")
        source = vault_of(ref)
        item = ref.split("/")[3] if len(ref.split("/")) > 3 else ""
        if not item or (source, item) in seen:
            continue
        seen.add((source, item))
        command = [
            "op",
            "item",
            "move",
            item,
            "--current-vault",
            source,
            "--destination-vault",
            policy["automation_vault"],
        ]
        print("  [dry-run] separate source-reference migration: " + _scrub(shlex.join(command)))


def _bootstrap_locked(policy: dict, env: dict[str, str], target: Path) -> None:
    sa, vault = policy["service_account"], policy["automation_vault"]
    expected_flags = ["--vault", f"{vault}:read_items,write_items", "--can-create-vaults"]
    if shlex.split(sa["create_flags"]) != expected_flags:
        raise ProvisionError("service-account grant flags do not match the owning vault policy")
    vaults = json.loads(_op(["vault", "list", "--format", "json"], env))
    matches = [row for row in vaults if row.get("name") == vault]
    if not matches:
        created = json.loads(_op(["vault", "create", vault, "--format", "json"], env))
        matches = [created]
    if len(matches) != 1 or not isinstance(matches[0].get("id"), str):
        raise ProvisionError("automation vault identity is ambiguous")
    vault_id = matches[0]["id"]
    title = sa["name"] + " service account"
    items = json.loads(_op(["item", "list", "--vault", vault_id, "--format", "json"], env))
    existing = [row for row in items if row.get("title") == title]
    if len(existing) > 1:
        raise ProvisionError("service-account custody item is ambiguous")
    pending = target.with_name(target.name + ".pending")
    intent = target.with_name(target.name + ".creation-intent")
    if existing:
        credential = _op(["read", f"op://{vault_id}/{existing[0]['id']}/password"], env).strip()
        if pending.exists() and _read_private(pending) != credential:
            raise ProvisionError("pending credential conflicts with canonical custody")
    elif pending.exists():
        credential = _read_private(pending)
    else:
        # A lost create response must never mint another account on an automatic retry.
        _private_create(intent, json.dumps({"vault_id": vault_id, "name": sa["name"]}))
        credential = _op(["service-account", "create", sa["name"], *expected_flags, "--raw"], env).strip()
        _private_create(pending, credential + "\n")
    if not re.fullmatch(r"ops_[A-Za-z0-9+/_=-]{20,}", credential):
        raise ProvisionError("service-account credential has an invalid shape")
    if not existing:
        payload = json.dumps(
            {
                "title": title,
                "category": "PASSWORD",
                "fields": [{"id": "password", "type": "CONCEALED", "purpose": "PASSWORD", "value": credential}],
            }
        )
        stored = json.loads(_op(["item", "create", "--vault", vault_id, "--format", "json", "-"], env, payload=payload))
        item_id = stored.get("id")
        if not isinstance(item_id, str):
            raise ProvisionError("canonical credential custody is unmeasured")
        if _op(["read", f"op://{vault_id}/{item_id}/password"], env).strip() != credential:
            raise ProvisionError("canonical credential readback differs")
    service_env = dict(env)
    service_env["OP_SERVICE_ACCOUNT_TOKEN"] = credential
    visible = json.loads(_op(["vault", "list", "--format", "json"], service_env))
    if {row.get("id") for row in visible} != {vault_id}:
        raise ProvisionError("service-account vault scope readback differs")
    if target.exists():
        previous = _read_private(target)
        if previous != credential:
            backup = target.with_name(target.name + ".previous")
            if backup.exists():
                if _read_private(backup) != previous:
                    raise ProvisionError("previous credential custody conflicts")
            else:
                _private_create(backup, previous + "\n")
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=".credential-install-")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(credential + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if _read_private(target) != credential:
        raise ProvisionError("installed credential readback differs")
    pending.unlink(missing_ok=True)
    intent.unlink(missing_ok=True)


def cmd_bootstrap(policy: dict, cred_map: list[dict], apply: bool) -> int:
    """Bootstrap custody once; source-item migration and old-account retirement are separate."""
    sa, vault = policy["service_account"], policy["automation_vault"]
    print("creds-provision bootstrap — canonical custody then installed scope readback")
    if not apply:
        print("  [dry-run] " + shlex.join(["op", "vault", "create", vault]))
        print(
            "  [dry-run] "
            + shlex.join(["op", "service-account", "create", sa["name"], *shlex.split(sa["create_flags"]), "--raw"])
        )
        _migration_plan(policy, cred_map)
        return 0
    try:
        target = Path(sa["token_file"]).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        for candidate in (
            target,
            target.with_name(target.name + ".pending"),
            target.with_name(target.name + ".previous"),
        ):
            if candidate.exists() or candidate.is_symlink():
                _read_private(candidate)
        lock = target.with_name(target.name + ".bootstrap-lock")
        if lock.is_symlink():
            raise ProvisionError("bootstrap lock is a symlink")
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _bootstrap_locked(policy, _owner_environment(), target)
    except (ProvisionError, OSError, ValueError, KeyError, TypeError, AttributeError):
        print("creds-provision: bootstrap incomplete; preserved custody must be reconciled before retry")
        return 2
    print("creds-provision: installed; canonical credential and exact vault scope read back")
    print("Existing source items and previous account remain preserved; migration requires its own receipt.")
    return 0


def cmd_apply(policy: dict, cred_map: list[dict], apply: bool) -> int:
    """Idempotent conformance: report/ensure every op-sourced secret lives in the automation vault.
    Non-mutating today (reports the outliers bootstrap/migration will resolve); the create/move path
    activates once the SA owns the vault."""
    return cmd_check(policy, cred_map)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CLAVIS — credential provisioning (SA + the one vault it reads).")
    ap.add_argument("command", choices=["check", "bootstrap", "apply"], nargs="?", default="check")
    ap.add_argument(
        "--apply", action="store_true", help="execute mutations (default: dry-run). bootstrap needs owner op."
    )
    args = ap.parse_args(argv)
    try:
        policy = load_policy(strict=args.apply)
    except (OSError, ValueError, TypeError, AttributeError):
        print("creds-provision: mutation requires a readable valid credential policy")
        return 2
    cred_map = load_cred_map()
    if args.command == "check":
        return cmd_check(policy, cred_map)
    if args.command == "bootstrap":
        return cmd_bootstrap(policy, cred_map, args.apply)
    return cmd_apply(policy, cred_map, args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
