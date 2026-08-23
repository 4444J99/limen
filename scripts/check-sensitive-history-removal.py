#!/usr/bin/env python3
"""Verify a sensitive-history removal without exposing the removed material.

The private packet supplies exact public object identities, two independent readable custody
copies, the reachability scan/deletion targets, and bounded Pages URLs.  This predicate keeps the
packet and artifact content private.  Its optional tracked receipt contains only identifiers,
counts, HTTP status codes, and boolean results.

Usage:
  python3 scripts/check-sensitive-history-removal.py preflight --packet PRIVATE.json
  python3 scripts/check-sensitive-history-removal.py postflight --packet PRIVATE.json \
    --apply --receipt docs/receipts/privacy/pr-2532-history-removal.json
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKET_SCHEMA = "limen.sensitive_history_removal_packet.v1"
RECEIPT_SCHEMA = "limen.sensitive_history_removal_receipt.v1"
RECEIPT_ROOT = (ROOT / "docs" / "receipts" / "privacy").resolve()
OID_LENGTH = 40
MAX_HTTP_BYTES = 2 * 1024 * 1024
HTTP_TIMEOUT_S = 15


class VerificationError(RuntimeError):
    """A redacted, operator-actionable predicate failure."""


def _sha256(data: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(data).hexdigest()


def _git_blob_oid(data: bytes) -> str:
    """Derive GitHub's SHA-1 blob identity without invoking Git on private content."""
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity, not cryptography


def _required_string(obj: dict[str, Any], key: str, *, where: str = "packet") -> str:
    """Read one required non-empty string without echoing private values in errors."""
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise VerificationError(f"{where} requires non-empty {key}")
    return value.strip()


def _load_packet(path: Path) -> tuple[dict[str, Any], str]:
    """Load the private packet and return its data plus a redacted content digest."""
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise VerificationError("private removal packet is unreadable or invalid JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError("private removal packet must be a JSON object")
    return value, _sha256(raw)


def _validate_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Validate exact identities, two-copy custody, and the bound reachability packet."""
    if packet.get("schema") != PACKET_SCHEMA:
        raise VerificationError(f"packet schema must be {PACKET_SCHEMA}")
    repository = _required_string(packet, "repository")
    if repository.count("/") != 1:
        raise VerificationError("repository must use owner/name form")
    pr_number = packet.get("pr_number")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise VerificationError("packet requires a positive pr_number")
    head = _required_string(packet, "original_head_oid")
    blob = _required_string(packet, "artifact_blob_oid")
    if len(head) != OID_LENGTH or len(blob) != OID_LENGTH:
        raise VerificationError("head and blob identities must be full 40-character OIDs")
    artifact_path = _required_string(packet, "artifact_path")

    copies = packet.get("custody_copies")
    if not isinstance(copies, list) or len(copies) < 2:
        raise VerificationError("packet requires at least two private custody copies")
    devices: set[str] = set()
    content_digests: set[str] = set()
    artifact: bytes | None = None
    copy_ids: set[str] = set()
    for index, copy in enumerate(copies, 1):
        if not isinstance(copy, dict):
            raise VerificationError(f"custody copy {index} must be an object")
        copy_id = _required_string(copy, "copy_id", where=f"custody copy {index}")
        device_id = _required_string(copy, "device_id", where=f"custody copy {index}")
        if copy_id in copy_ids or device_id in devices:
            raise VerificationError("custody copies must have distinct copy and device identities")
        copy_ids.add(copy_id)
        devices.add(device_id)
        _required_string(copy, "restore_verified_at", where=f"custody copy {copy_id}")
        declared_sha256 = _required_string(copy, "sha256", where=f"custody copy {copy_id}").lower()
        private_path = Path(_required_string(copy, "path", where=f"custody copy {copy_id}"))
        try:
            content = private_path.read_bytes()
        except OSError as exc:
            raise VerificationError(f"custody copy {copy_id} is not readable") from exc
        if _sha256(content) != declared_sha256:
            raise VerificationError(f"custody copy {copy_id} failed its SHA-256 check")
        if _git_blob_oid(content) != blob:
            raise VerificationError(f"custody copy {copy_id} does not reproduce the exact artifact blob")
        content_digests.add(declared_sha256)
        artifact = content if artifact is None else artifact
    if len(content_digests) != 1:
        raise VerificationError("private custody copies do not contain the same artifact bytes")

    scan = packet.get("reachability_scan")
    if not isinstance(scan, dict):
        raise VerificationError("packet requires a private reachability_scan object")
    for key, expected in (
        ("repository", repository),
        ("pr_number", pr_number),
        ("original_head_oid", head),
        ("artifact_blob_oid", blob),
    ):
        if scan.get(key) != expected:
            raise VerificationError(f"reachability_scan {key} is not bound to the removal target")
    _required_string(scan, "observed_at", where="reachability_scan")

    targets = packet.get("deletion_targets")
    if not isinstance(targets, dict):
        raise VerificationError("packet requires deletion_targets")
    pull_ref = _required_string(targets, "pull_ref", where="deletion_targets")
    branch_ref = _required_string(targets, "branch_ref", where="deletion_targets")
    if pull_ref != f"refs/pull/{pr_number}/head" or not branch_ref.startswith("refs/heads/"):
        raise VerificationError("deletion targets must bind the exact PR ref and one branch ref")
    if targets.get("original_head_oid") != head or targets.get("artifact_blob_oid") != blob:
        raise VerificationError("deletion targets are not bound to the exact head and blob")
    reachable = scan.get("reachable_refs")
    if not isinstance(reachable, list) or pull_ref not in reachable or branch_ref not in reachable:
        raise VerificationError("reachability scan must include both exact deletion refs")

    pages_urls = packet.get("pages_urls")
    if not isinstance(pages_urls, list) or not pages_urls or len(pages_urls) > 20:
        raise VerificationError("packet requires 1-20 bounded Pages URLs")
    for url in pages_urls:
        parsed = urllib.parse.urlparse(str(url))
        if parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".github.io"):
            raise VerificationError("every Pages probe must be an absolute GitHub Pages HTTPS URL")

    return {
        "repository": repository,
        "pr_number": pr_number,
        "head": head,
        "blob": blob,
        "artifact_path": artifact_path,
        "artifact": artifact or b"",
        "custody_copy_count": len(copies),
        "custody_device_count": len(devices),
        "pull_ref": pull_ref,
        "branch_ref": branch_ref,
        "pages_urls": [str(url) for url in pages_urls],
    }


def _pr_state(context: dict[str, Any]) -> dict[str, Any]:
    """Read the authenticated PR object without exposing its body or comments."""
    command = [
        "gh",
        "pr",
        "view",
        str(context["pr_number"]),
        "--repo",
        context["repository"],
        "--json",
        "state,mergedAt,headRefOid,url",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        value = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise VerificationError("authenticated PR-state probe failed") from exc
    if not isinstance(value, dict):
        raise VerificationError("authenticated PR-state probe returned no object")
    if value.get("state") != "CLOSED" or value.get("mergedAt") is not None:
        raise VerificationError("target PR is not closed unmerged")
    observed_head = value.get("headRefOid")
    if observed_head and observed_head != context["head"]:
        raise VerificationError("target PR head moved after the private packet was sealed")
    return value


def _public_refs(context: dict[str, Any]) -> dict[str, str]:
    """Read the two public refs with credential helpers disabled."""
    remote = f"https://github.com/{context['repository']}.git"
    command = [
        "git",
        "-c",
        "credential.helper=",
        "ls-remote",
        remote,
        context["pull_ref"],
        context["branch_ref"],
    ]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError("unauthenticated ref probe failed") from exc
    if result.returncode != 0:
        raise VerificationError("unauthenticated ref probe was unavailable")
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2:
            refs[fields[1]] = fields[0]
    return refs


def _http_get(url: str) -> tuple[int, bytes]:
    """Perform one bounded unauthenticated HTTP GET."""
    request = urllib.request.Request(url, headers={"User-Agent": "limen-sensitive-history-removal/1"})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            return int(response.status), response.read(MAX_HTTP_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(MAX_HTTP_BYTES + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise VerificationError("unauthenticated HTTP probe was unavailable") from exc


def _public_object_probes(context: dict[str, Any]) -> dict[str, int]:
    """Probe the public blob API, GitHub blob page, and raw object URL."""
    quoted_path = urllib.parse.quote(context["artifact_path"], safe="/")
    owner_repo = context["repository"]
    urls = {
        "blob_api": f"https://api.github.com/repos/{owner_repo}/git/blobs/{context['blob']}",
        "blob_page": f"https://github.com/{owner_repo}/blob/{context['head']}/{quoted_path}",
        "raw_object": f"https://raw.githubusercontent.com/{owner_repo}/{context['head']}/{quoted_path}",
    }
    return {name: _http_get(url)[0] for name, url in urls.items()}


def _pages_clean(context: dict[str, Any]) -> tuple[bool, dict[str, int]]:
    """Check bounded Pages URLs for exact public identities and private artifact text."""
    artifact_text = context["artifact"].decode("utf-8", errors="replace")
    private_needles = [line.strip() for line in artifact_text.splitlines() if len(line.strip()) >= 24]
    public_needles = [context["head"], context["blob"], context["artifact_path"]]
    statuses: dict[str, int] = {}
    clean = True
    for index, url in enumerate(context["pages_urls"], 1):
        status, body = _http_get(url)
        statuses[f"pages_{index}"] = status
        if len(body) > MAX_HTTP_BYTES:
            clean = False
            continue
        rendered = html.unescape(body.decode("utf-8", errors="replace"))
        if any(needle and needle in rendered for needle in public_needles):
            clean = False
        if any(needle in rendered for needle in private_needles):
            clean = False
    return clean, statuses


def _verify(mode: str, packet: dict[str, Any], packet_sha256: str) -> dict[str, Any]:
    """Run the preflight or postflight predicate and return a redacted receipt."""
    context = _validate_packet(packet)
    pr = _pr_state(context)
    refs = _public_refs(context)
    object_status = _public_object_probes(context)
    pages_clean, pages_status = _pages_clean(context)
    pull_value = refs.get(context["pull_ref"])
    branch_value = refs.get(context["branch_ref"])

    if mode == "preflight":
        if pull_value != context["head"] or branch_value != context["head"]:
            raise VerificationError("preflight refs do not both resolve to the sealed original head")
        if any(status != 200 for status in object_status.values()):
            raise VerificationError("preflight could not reproduce every public object surface")
    else:
        if pull_value == context["head"] or branch_value == context["head"]:
            raise VerificationError("an exact contaminated PR or branch ref remains publicly reachable")
        if any(status not in {404, 410} for status in object_status.values()):
            raise VerificationError("an exact contaminated object surface remains publicly reachable")
        if not pages_clean:
            raise VerificationError("a bounded Pages probe still exposes a target identity or artifact content")

    return {
        "schema": RECEIPT_SCHEMA,
        "mode": mode,
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": context["repository"],
        "pr_number": context["pr_number"],
        "original_head_oid": context["head"],
        "artifact_blob_oid": context["blob"],
        "artifact_path": context["artifact_path"],
        "packet_sha256": packet_sha256,
        "custody_copy_count": context["custody_copy_count"],
        "distinct_custody_device_count": context["custody_device_count"],
        "pr_state": pr.get("state"),
        "pr_merged": pr.get("mergedAt") is not None,
        "exact_pull_ref_present": pull_value == context["head"],
        "exact_branch_ref_present": branch_value == context["head"],
        "public_object_status": object_status,
        "pages_status": pages_status,
        "pages_clean": pages_clean,
        "result": "pass",
    }


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    """Create, but never overwrite, one tracked redacted receipt."""
    target = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        target.relative_to(RECEIPT_ROOT)
    except ValueError as exc:
        raise VerificationError("receipt target must live under docs/receipts/privacy") from exc
    if target.exists():
        raise VerificationError("immutable receipt target already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments, run the predicate, and optionally create its immutable receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "postflight"))
    parser.add_argument("--packet", type=Path, required=True, help="private packet path; never printed or copied")
    parser.add_argument("--receipt", type=Path, help="new tracked redacted receipt under docs/receipts/privacy")
    parser.add_argument("--apply", action="store_true", help="allow creation of the new redacted receipt")
    args = parser.parse_args(argv)
    if args.receipt and (args.mode != "postflight" or not args.apply):
        parser.error("--receipt requires postflight --apply")
    if args.apply and not args.receipt:
        parser.error("--apply requires --receipt")

    try:
        packet, packet_sha256 = _load_packet(args.packet)
        receipt = _verify(args.mode, packet, packet_sha256)
        if args.receipt:
            _write_receipt(args.receipt, receipt)
    except VerificationError as exc:
        print(f"sensitive-history-removal: FAIL — {exc}")
        return 1
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
