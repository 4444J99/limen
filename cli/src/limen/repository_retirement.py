"""Exact-scope repository retirement. No estate discovery and no deletion by prose.

The keeper authorizes actors; this module owns deterministic Git decisions and
crash-visible progress. All subprocesses are bounded and their real exits recorded.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.personal_custody import _assert_content, _file_sha256, _record
from limen.worktree_abandonment import (
    CustodyPathIdentity,
    WorktreeAbandonmentError,
    detach_registered_worktree,
    purge_custody_proven_path,
)

SCHEMA = "limen.repository_retirement.v1"
OID = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class RetirementError(RuntimeError):
    """Public-safe reason code. Raw subprocess output never enters public receipts."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def manifest_binding(value: dict) -> str:
    # Run IDs are allocated by the keeper after packet hashing. Excluding these
    # references avoids a circular packet -> manifest -> run ID hash dependency.
    return digest({key: item for key, item in value.items() if key not in {"run_id", "review_run_id"}})


def timestamp(value: str) -> float:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise RetirementError("deadline-requires-timezone")
    return parsed.timestamp()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RetirementError("mutation-owner-busy") from exc
        yield
    finally:
        os.close(fd)


class Runtime:
    def __init__(self, deadline: float, *, command_seconds: float = 30):
        self.deadline = deadline
        self.monotonic_deadline = time.monotonic() + max(0, deadline - time.time())
        self.command_seconds = command_seconds
        self.exits: list[dict[str, Any]] = []
        self.verification_seconds = 0.0

    @contextmanager
    def verification(self):
        remaining = 600 - self.verification_seconds
        if remaining <= 0:
            raise RetirementError("verification-budget-exhausted")
        wall, monotonic = self.deadline, self.monotonic_deadline
        started = time.monotonic()
        self.deadline = min(wall, time.time() + remaining)
        self.monotonic_deadline = min(monotonic, started + remaining)
        try:
            yield
        finally:
            self.verification_seconds += time.monotonic() - started
            self.deadline, self.monotonic_deadline = wall, monotonic

    def check(self) -> float:
        remaining = min(self.deadline - time.time(), self.monotonic_deadline - time.monotonic())
        if remaining <= 0:
            raise RetirementError("deadline-exhausted")
        return remaining

    def run(self, argv: list[str], *, data: str | None = None, timeout: float | None = None):
        allowed = min(self.check(), timeout or self.command_seconds)
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
        started = time.monotonic()
        operation = Path(argv[0]).name
        try:
            result = subprocess.run(
                argv,
                input=data,
                capture_output=True,
                text=True,
                errors="surrogateescape",
                timeout=allowed,
                check=False,
                env=env,
                stdin=subprocess.DEVNULL if data is None else None,
            )
        except subprocess.TimeoutExpired as exc:
            self.exits.append(
                {"operation": operation, "exit": None, "timed_out": True, "seconds": time.monotonic() - started}
            )
            raise RetirementError("subprocess-timeout") from exc
        except OSError as exc:
            raise RetirementError("subprocess-unavailable") from exc
        self.exits.append({"operation": operation, "exit": result.returncode, "seconds": time.monotonic() - started})
        if len(result.stdout) + len(result.stderr) > 4 * 1024 * 1024:
            raise RetirementError("subprocess-output-ceiling")
        return result

    def git(self, repo: Path, *args: str, data: str | None = None, **_kwargs):
        return self.run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.excludesFile=/dev/null",
                "-c",
                "gc.auto=0",
                "-c",
                "maintenance.auto=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-C",
                str(repo),
                *args,
            ],
            data=data,
        )

    def text(self, repo: Path, *args: str) -> str:
        result = self.git(repo, *args)
        if result.returncode:
            raise RetirementError(f"git-{args[0]}-failed")
        return result.stdout.rstrip("\n")


def load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if value.get("schema") != SCHEMA or not IDENTIFIER.fullmatch(value.get("campaign_id", "")):
        raise RetirementError("invalid-batch-manifest")
    timestamp(value["deadline"])
    repositories = value.get("repositories")
    if not isinstance(repositories, list) or not repositories or len(repositories) > 500:
        raise RetirementError("batch-must-list-exact-repositories")
    seen: set[str] = set()
    for repo in repositories:
        source = Path(repo["path"])
        if not source.is_absolute() or str(source) != os.path.normpath(source) or source.is_symlink():
            raise RetirementError("repository-path-must-be-exact-and-not-symlink")
        if str(source) in seen or type(repo.get("repository_id")) is not int:
            raise RetirementError("duplicate-path-or-missing-immutable-id")
        seen.add(str(source))
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*", repo.get("owner", "")):
            raise RetirementError("existing-owner-issue-required")
    ordered_paths = sorted(seen)
    for index, a in enumerate(ordered_paths):
        if any(Path(a) in Path(b).parents for b in ordered_paths[index + 1 :]):
            raise RetirementError("overlapping-assigned-roots")
    return value


def identity(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(before.st_mode) or path.resolve() != path:
        raise RetirementError("path-identity-unsafe")
    return {"path": str(path), "device": before.st_dev, "inode": before.st_ino}


def common_key(common: Path) -> str:
    return "git-common:" + digest(identity(common))


def worktrees(runtime: Runtime, repo: Path) -> list[dict[str, str]]:
    output = runtime.text(repo, "worktree", "list", "--porcelain", "-z")
    rows: list[dict[str, str]] = []
    for block in output.split("\0\0"):
        row: dict[str, str] = {}
        for field in block.split("\0"):
            if field:
                key, _, value = field.partition(" ")
                row[key] = value
        if "worktree" in row:
            rows.append(row)
    if not rows:
        raise RetirementError("worktree-inventory-empty")
    return rows


def github_identity(runtime: Runtime, url: str) -> dict[str, Any]:
    match = re.fullmatch(
        r"(?:git@github.com:|https://github.com/|ssh://git@github.com/)([\w.-]+/[\w.-]+?)(?:\.git)?/?", url
    )
    if match is None:
        raise RetirementError("remote-requires-authenticated-identity-mapping")
    result = runtime.run(["gh", "api", f"repos/{match.group(1)}"])
    if result.returncode:
        raise RetirementError("authenticated-remote-identity-unavailable")
    value = json.loads(result.stdout)
    if type(value.get("id")) is not int:
        raise RetirementError("authenticated-remote-identity-invalid")
    return {"id": value["id"], "name": value["full_name"], "private": value["private"]}


def remote_refs(runtime: Runtime, repo: Path, remote: str) -> dict[str, str]:
    output = runtime.text(repo, "ls-remote", "--heads", "--tags", remote)
    refs = {ref: oid for oid, ref in (line.split("\t") for line in output.splitlines())}
    if any(not OID.fullmatch(oid) for oid in refs.values()):
        raise RetirementError("remote-object-id-invalid")
    return refs


def inspect(runtime: Runtime, entry: dict[str, Any], remote_identity=github_identity) -> dict[str, Any]:
    path = Path(entry["path"])
    source = identity(path)
    common = Path(runtime.text(path, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    registered = worktrees(runtime, path)
    remotes: dict[str, Any] = {}
    for remote in runtime.text(path, "remote").splitlines():
        urls = runtime.text(path, "remote", "get-url", "--all", remote).splitlines()
        push_urls = runtime.text(path, "remote", "get-url", "--push", "--all", remote).splitlines()
        verified = [remote_identity(runtime, url) for url in urls + push_urls]
        if len({item["id"] for item in verified}) != 1:
            raise RetirementError("fetch-push-remote-identity-mismatch")
        refspecs = runtime.git(path, "config", "--get-all", f"remote.{remote}.fetch")
        if refspecs.returncode not in {0, 1}:
            raise RetirementError("remote-refspec-unavailable")
        remotes[remote] = {
            "identity": verified[0],
            "urls": urls,
            "push_urls": push_urls,
            "refspecs": refspecs.stdout.splitlines(),
            "refs": remote_refs(runtime, path, remote),
        }
    if "origin" not in remotes or remotes["origin"]["identity"]["id"] != entry["repository_id"]:
        raise RetirementError("origin-immutable-identity-mismatch")
    refs = runtime.text(
        path,
        "for-each-ref",
        "--format=%(refname)%00%(objectname)%00%(upstream)%00%(upstream:remotename)%00%(upstream:remoteref)",
    )
    return {
        "source": source,
        "common": identity(common),
        "key": common_key(common),
        "worktrees": registered,
        "remotes": remotes,
        "refs": refs,
        "head": runtime.text(path, "rev-parse", "HEAD"),
        "dirty": bool(runtime.text(path, "status", "--porcelain=v1", "-z", "--untracked-files=all")),
    }


def process_owner(runtime: Runtime, root: Path) -> int | None:
    result = runtime.run(["lsof", "-n", "-Fpn", "+D", str(root)], timeout=20)
    if result.returncode not in {0, 1} or result.stderr or (result.returncode == 1 and result.stdout):
        raise RetirementError("process-ownership-unmeasured")
    for line in result.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            return int(line[1:])
    return None


def sync(
    runtime: Runtime, entry: dict[str, Any], observed: dict[str, Any], *, on_change=None, before_checkout=None
) -> list[dict[str, Any]]:
    path = Path(entry["path"])
    for remote, value in observed["remotes"].items():
        # Configured refspecs are recorded, but never apply their leading '+' or
        # replace a stale tracking ref to manufacture parity. Fetch immutable OIDs
        # into the object store only; no remote-tracking ref is overwritten.
        oids = sorted({oid for ref, oid in value["refs"].items() if not ref.endswith("^{}")})
        for offset in range(0, len(oids), 50):
            result = runtime.git(
                path,
                "fetch",
                "--no-prune",
                "--no-prune-tags",
                "--no-tags",
                "--no-write-fetch-head",
                "--no-auto-maintenance",
                remote,
                *oids[offset : offset + 50],
            )
            if result.returncode:
                raise RetirementError("additive-fetch-failed")
    changes: list[dict[str, Any]] = []
    checked = {row.get("branch"): Path(row["worktree"]) for row in observed["worktrees"]}
    for line in observed["refs"].splitlines():
        ref, old, upstream, remote, remote_ref = line.split("\0")
        if not ref.startswith("refs/heads/") or not upstream or remote not in observed["remotes"]:
            continue
        target = observed["remotes"][remote]["refs"].get(remote_ref)
        if target is None or old == target:
            continue
        ancestor = runtime.git(path, "merge-base", "--is-ancestor", old, target)
        if ancestor.returncode == 1:
            continue  # Ahead/divergent history stays intact and enters full custody.
        if ancestor.returncode:
            raise RetirementError("branch-ancestry-unavailable")
        checkout = checked.get(ref)
        if checkout:
            if checkout != path:
                continue
            if runtime.text(checkout, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
                continue
            if runtime.text(checkout, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"):
                if before_checkout is None:
                    continue
                before_checkout()
            result = runtime.git(checkout, "merge", "--ff-only", "--no-edit", target)
        else:
            result = runtime.git(path, "update-ref", ref, target, old)
        if result.returncode:
            raise RetirementError("fast-forward-failed")
        changes.append({"ref": ref, "before": old, "after": target})
        if on_change:
            on_change(changes[-1])
    # New tags are additive; a local tag with the same name is never rewritten.
    for remote in observed["remotes"].values():
        for ref, oid in remote["refs"].items():
            if not ref.startswith("refs/tags/") or ref.endswith("^{}"):
                continue
            current = runtime.git(path, "show-ref", "--verify", "--quiet", ref)
            if current.returncode == 1:
                result = runtime.git(path, "update-ref", ref, oid, "0" * len(oid))
                if result.returncode:
                    raise RetirementError("additive-tag-update-failed")
                changes.append({"ref": ref, "before": None, "after": oid})
                if on_change:
                    on_change(changes[-1])
            elif current.returncode:
                raise RetirementError("tag-read-failed")
    return changes


def records(runtime: Runtime, root: Path) -> tuple:
    """Reuse metadata hashing, adding a deadline and mount boundary per entry."""
    source = identity(root)
    values = []
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        files.sort()
        for item in [
            Path(current),
            *(Path(current) / name for name in files),
            *(Path(current) / name for name in dirs if (Path(current) / name).is_symlink()),
        ]:
            runtime.check()
            if item.lstat().st_dev != source["device"]:
                raise RetirementError("nested-mounted-storage")
            values.append(_record(item, root, checkpoint=runtime.check))
    if identity(root) != source:
        raise RetirementError("source-identity-drift")
    return tuple(sorted(values, key=lambda row: row.relative))


def proof_sources(observed: dict[str, Any]) -> list[Path]:
    root = Path(observed["source"]["path"])
    common = Path(observed["common"]["path"])
    return [root] if common == root or root in common.parents else [root, common]


def dependencies(runtime: Runtime, observed: dict[str, Any], assigned: set[str]) -> None:
    common = Path(observed["common"]["path"])
    for row in observed["worktrees"]:
        root = Path(row["worktree"])
        if not root.exists() or row.get("prunable") is not None or "locked" in row:
            raise RetirementError("broken-or-locked-worktree-registration")
        actual = Path(runtime.text(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        if actual != common:
            raise RetirementError("cross-store-worktree-registration")
    alternate = common / "objects" / "info" / "alternates"
    if alternate.exists() and alternate.read_bytes().strip():
        raise RetirementError("external-object-alternate-requires-custody")
    if (common / "shallow").exists():
        raise RetirementError("shallow-history-requires-completion")
    if list((common / "objects" / "pack").glob("*.promisor")):
        raise RetirementError("promisor-objects-require-materialization")
    # Independent nested stores are included byte-for-byte. A gitfile pointing
    # outside the captured tree is a dependency, not an independent archive.
    root = Path(observed["source"]["path"])
    for current, dirs, files in os.walk(root, followlinks=False):
        runtime.check()
        if Path(current) == common:
            dirs[:] = []
            continue
        if ".git" in files and Path(current) != root:
            nested_common = Path(runtime.text(Path(current), "rev-parse", "--path-format=absolute", "--git-common-dir"))
            if root not in nested_common.parents:
                raise RetirementError("nested-repository-external-store")
            if runtime.git(Path(current), "fsck", "--full", "--no-dangling").returncode:
                raise RetirementError("nested-git-object-integrity-unproven")
        if (
            ".git" in dirs
            and Path(current) != root
            and runtime.git(Path(current), "fsck", "--full", "--no-dangling").returncode
        ):
            raise RetirementError("nested-git-object-integrity-unproven")
    objects = runtime.text(root, "cat-file", "--batch-all-objects", "--batch-check")
    storage = runtime.git(root, "config", "--get", "lfs.storage")
    if storage.returncode not in {0, 1}:
        raise RetirementError("lfs-storage-unavailable")
    lfs = common / "lfs" if not storage.stdout.strip() else Path(storage.stdout.strip())
    if not lfs.is_absolute():
        lfs = common / lfs
    if storage.stdout.strip() and common not in lfs.resolve().parents:
        raise RetirementError("external-lfs-storage")
    for line in objects.splitlines():
        oid, kind, size = line.split()
        if kind != "blob" or int(size) > 512:
            continue
        content = runtime.text(root, "cat-file", "blob", oid)
        if not content.startswith("version https://git-lfs.github.com/spec/v1\n"):
            continue
        match = re.search(r"^oid sha256:([0-9a-f]{64})$", content, re.MULTILINE)
        if match is None:
            raise RetirementError("lfs-pointer-invalid")
        object_id = match.group(1)
        payload = lfs / "objects" / object_id[:2] / object_id[2:4] / object_id
        if not payload.is_file() or payload.is_symlink():
            raise RetirementError("local-lfs-payload-custody-missing")
        if _file_sha256(payload, checkpoint=runtime.check) != object_id:
            raise RetirementError("local-lfs-payload-corrupt")


class Campaign:
    def __init__(self, manifest: dict[str, Any], state_root: Path):
        self.manifest = manifest
        self.root = state_root / manifest["campaign_id"]
        self.path = self.root / "state.json"
        self.hash = digest(manifest)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if self.state["manifest_sha256"] != self.hash:
                raise RetirementError("campaign-manifest-changed")
        else:
            self.state = {
                "schema": SCHEMA,
                "manifest_sha256": self.hash,
                "manifest": manifest,
                "candidates": {},
                "exits": [],
                "attempts": [],
                "publication": None,
            }

    def save(self) -> None:
        atomic_json(self.path, self.state)

    def candidate(self, entry: dict[str, Any]) -> dict[str, Any]:
        return self.state["candidates"].setdefault(entry["path"], {"status": "pending", "changes": []})

    def summary(self) -> dict[str, Any]:
        rows = self.state["candidates"]
        return {
            "schema": SCHEMA,
            "campaign_id": self.manifest["campaign_id"],
            "assigned": len(self.manifest["repositories"]),
            "branches_synchronized": sum(
                sum(c["ref"].startswith("refs/heads/") for c in row.get("changes", [])) for row in rows.values()
            ),
            "tags_synchronized": sum(
                sum(c["ref"].startswith("refs/tags/") for c in row.get("changes", [])) for row in rows.values()
            ),
            "custody_verified": sum(bool(row.get("custody")) for row in rows.values()),
            "copies_removed": sum(row.get("status") == "removed" for row in rows.values()),
            "allocated_bytes_removed": sum(row.get("removed_bytes", 0) for row in rows.values()),
            "free_bytes_before": self.state.get("free_before"),
            "free_bytes_after": self.state.get("free_after"),
            "agent_minutes_consumed": self.state.get("agent_minutes_consumed"),
            "agent_minutes_remaining": self.state.get("agent_minutes_remaining"),
            "retained": [
                {
                    "candidate": digest(path)[:16],
                    "owner": next(e["owner"] for e in self.manifest["repositories"] if e["path"] == path),
                    "reason": row.get("reason", row["status"]),
                }
                for path, row in rows.items()
                if row["status"] != "removed"
            ],
            "verification_exits": self.state["exits"],
            "publication": self.state.get("publication"),
        }


def public_publish(runtime: Runtime, campaign: Campaign) -> dict:
    """One idempotent redacted issue comment, followed by exact readback."""
    summary = campaign.summary()
    summary.pop("publication", None)
    body = "Repository retirement receipt\n\n```json\n" + json.dumps(summary, sort_keys=True, indent=2) + "\n```"
    body_hash = hashlib.sha256(body.encode()).hexdigest()
    previous = campaign.state.get("publication")
    owner = campaign.manifest["repositories"][0]["owner"]
    repository, number = owner.split("#")
    # Machine progress publication is restricted to the exact existing owner.
    # Observe the issue and authenticated principal before every outward write;
    # missing, redirected, locked, or closed owners cannot receive this receipt.
    target = runtime.run(["gh", "api", f"repos/{repository}/issues/{number}"])
    principal = runtime.run(["gh", "api", "user"])
    if target.returncode or principal.returncode:
        raise RetirementError("receipt-owner-observation-failed")
    observed_owner = json.loads(target.stdout)
    if (
        observed_owner.get("number") != int(number)
        or observed_owner.get("state") != "open"
        or observed_owner.get("locked")
        or observed_owner.get("html_url", "").lower() != f"https://github.com/{repository}/issues/{number}".lower()
        or not json.loads(principal.stdout).get("login")
    ):
        raise RetirementError("receipt-owner-not-authorized")
    if previous and previous["body_sha256"] == body_hash:
        comment = previous["id"]
    else:
        # Write-ahead intent: a failed POST is not blindly retried. Reconcile the
        # bounded comment page using the body digest before creating another.
        pending = campaign.state.get("publication_pending")
        if pending and pending["body_sha256"] == body_hash:
            read = runtime.run(["gh", "api", f"repos/{repository}/issues/{number}/comments?per_page=100"])
            if read.returncode:
                raise RetirementError("receipt-publication-reconciliation-failed")
            matches = [row for row in json.loads(read.stdout) if row.get("body") == body]
            if not matches:
                raise RetirementError("receipt-publication-outcome-unresolved")
            comment = matches[-1]["id"]
        else:
            campaign.state["publication_pending"] = {"body_sha256": body_hash}
            campaign.save()
            result = runtime.run(
                ["gh", "api", "--method", "POST", f"repos/{repository}/issues/{number}/comments", "--input", "-"],
                data=json.dumps({"body": body}),
            )
            if result.returncode:
                raise RetirementError("receipt-publication-failed")
            comment = json.loads(result.stdout)["id"]
    read = runtime.run(["gh", "api", f"repos/{repository}/issues/comments/{comment}"])
    if read.returncode or json.loads(read.stdout).get("body") != body:
        raise RetirementError("receipt-readback-mismatch")
    result = {
        "id": comment,
        "body_sha256": body_hash,
        "url": json.loads(read.stdout)["html_url"],
        "readback_exit": read.returncode,
    }
    campaign.state["publication"] = result
    campaign.state.pop("publication_pending", None)
    campaign.save()
    return result


class Runner:
    def __init__(
        self,
        campaign: Campaign,
        *,
        keeper=None,
        runtime=None,
        custody=None,
        remote_identity=github_identity,
        owner_probe=None,
        heavy=None,
        progress=None,
    ):
        from limen.host_admission import hold_lease
        from limen.repository_retirement_custody import PairCustody

        self.campaign = campaign
        self.runtime = runtime or Runtime(timestamp(campaign.manifest["deadline"]))
        self.keeper = keeper
        self.custody = custody or PairCustody(campaign.manifest["custody"], self.runtime)
        self.remote_identity = remote_identity
        self.owner_probe = owner_probe or (lambda p: process_owner(self.runtime, p))
        self.heavy = heavy or (
            lambda: hold_lease(
                "heavy", owner="repository-retirement-" + campaign.manifest["campaign_id"], surface="limen-repos"
            )
        )
        self.progress = progress or (lambda _row: None)

    def safe(self, observed: dict, entry: dict, *, review: bool = False) -> None:
        roots = [Path(row["worktree"]) for row in observed["worktrees"]]
        common = Path(observed["common"]["path"])
        protected = [
            Path.home(),
            Path.home() / "Workspace",
            Path(__file__).resolve().parents[3],
            self.campaign.root,
            *[Path(p) for p in self.campaign.manifest.get("protected_paths", [])],
        ]
        target = Path(entry["path"])
        if any(target == p or target in p.parents for p in protected):
            raise RetirementError("protected-root-or-runtime-dependency")
        for root in [*roots, common]:
            if self.owner_probe(root) is not None:
                raise RetirementError("active-process-or-open-file")
        if self.keeper:
            deadline = self.keeper.authorize(observed["key"], [str(root) for root in [*roots, common]], review=review)
            self.runtime.deadline = min(self.runtime.deadline, deadline)
            self.runtime.monotonic_deadline = min(
                self.runtime.monotonic_deadline, time.monotonic() + deadline - time.time()
            )
            self.keeper.heartbeat(review=review)
        else:
            raise RetirementError("authenticated-keeper-admission-required")
        dependencies(self.runtime, observed, {e["path"] for e in self.campaign.manifest["repositories"]})
        self.runtime.check()

    def _read(self, entry: dict) -> dict:
        with self.runtime.verification():
            return inspect(self.runtime, entry, self.remote_identity)

    def _proof(self, observed: dict, custody: dict, pre_sync=None) -> str:
        return digest(
            {
                "manifest": self.campaign.hash,
                "observed": observed,
                "custody": custody["digest"],
                "pre_sync": pre_sync["digest"] if pre_sync else None,
            }
        )

    def _verify_current(self, entry: dict, row: dict, *, review: bool = False) -> dict:
        observed = self._read(entry)
        self.safe(observed, entry, review=review)
        if observed != row["observed"]:
            raise RetirementError("candidate-proof-invalidated")
        for source in row["custody"]["sources"]:
            self.custody.verify_source(Path(source["identity"]["path"]), source)
        if self._proof(observed, row["custody"], row.get("pre_sync_custody")) != row["proof_sha256"]:
            raise RetirementError("candidate-proof-digest-mismatch")
        return observed

    def preview(self) -> dict:
        rows = []
        for entry in self.campaign.manifest["repositories"]:
            try:
                observed = self._read(entry)
                rows.append(
                    {
                        "candidate": digest(entry["path"])[:16],
                        "repository_id": entry["repository_id"],
                        "resource_claim": {"key": observed["key"], "mode": "exclusive"},
                        "registered_worktrees": len(observed["worktrees"]),
                        "dirty": observed["dirty"],
                    }
                )
            except (RetirementError, OSError, ValueError) as exc:
                rows.append(
                    {
                        "candidate": digest(entry["path"])[:16],
                        "reason": str(exc) if isinstance(exc, RetirementError) else "inspection-unavailable",
                    }
                )
        return {
            "schema": SCHEMA,
            "preview": True,
            "campaign_id": self.campaign.manifest["campaign_id"],
            "manifest_binding": manifest_binding(self.campaign.manifest),
            "candidates": rows,
        }

    def apply(self) -> dict:
        runtime, campaign = self.runtime, self.campaign
        with lock(campaign.root / "campaign.lock"):
            self.runtime.verification_seconds = campaign.state.get("verification_seconds", 0.0)
            campaign.state["interrupted_attempt"] = True
            campaign.state["attempts"].append({"started_at": datetime.now(UTC).isoformat()})
            campaign.save()
            try:
                existing = [Path(e["path"]) for e in campaign.manifest["repositories"] if Path(e["path"]).exists()]
                campaign.state.setdefault(
                    "free_before",
                    os.statvfs(existing[0] if existing else campaign.root).f_bavail
                    * os.statvfs(existing[0] if existing else campaign.root).f_frsize,
                )
                # Linked views retire before their common-store root. Scope remains
                # the explicitly listed batch; registered dependencies are observed.
                entries = sorted(
                    campaign.manifest["repositories"], key=lambda e: not (Path(e["path"]) / ".git").is_file()
                )
                for entry in entries:
                    row = campaign.candidate(entry)
                    path = Path(entry["path"])
                    if row["status"] == "removed":
                        if path.exists() or path.is_symlink():
                            row.update(status="retained", reason="removed-path-reappeared")
                        continue
                    try:
                        runtime.check()
                        if not path.exists():
                            removal = row.get("removal")
                            if not removal:
                                completed = [
                                    json.loads(p.read_text()) for p in (campaign.root / "removals").glob("*.json")
                                ]
                                removal = next(
                                    (
                                        r
                                        for r in completed
                                        if r.get("target") == str(path) and r.get("state") == "completed"
                                    ),
                                    None,
                                )
                            if (
                                removal
                                and removal.get("state") == "completed"
                                and row.get("custody")
                                and self.keeper.accepted(row.get("proof_sha256", ""))
                            ):
                                with self.heavy():
                                    self.custody.verify(row["custody"], restore=False)
                                self._remote_readback(row["observed"])
                                row.update(
                                    status="removed",
                                    reason=None,
                                    removal=removal,
                                    removed_bytes=sum(
                                        v["physical_bytes"] for v in row["custody"]["sources"][0]["records"]
                                    ),
                                )
                                continue
                            raise RetirementError("absent-without-completed-removal-journal")
                        if (
                            row.get("preparation", {}).get("state") == "applying"
                            or row.get("custody", {}).get("preparation", {}).get("state") == "applying"
                        ):
                            raise RetirementError("interrupted-checkout-preparation")
                        observed = self._read(entry)
                        with lock(campaign.root.parent / "locks" / (observed["key"].split(":")[1] + ".lock")):
                            self.safe(observed, entry)
                            if row.get("custody") and observed == row.get("observed"):
                                self._verify_current(entry, row)
                            else:

                                def recorded(change, current_row=row):
                                    current_row["changes"].append(change)
                                    campaign.save()

                                def before_checkout(current_row=row, before=observed):
                                    with self.heavy():
                                        current_row["pre_sync_custody"] = self.custody.capture(
                                            proof_sources(before), journal_root=campaign.root / "removals"
                                        )
                                    campaign.save()

                                sync(runtime, entry, observed, on_change=recorded, before_checkout=before_checkout)
                                observed = self._read(entry)
                                row["observed"] = observed
                                row.update(status="synchronized", reason="custody-pending")
                                campaign.save()
                                with self.heavy():
                                    for source in proof_sources(observed):
                                        runtime.check()
                                    if runtime.git(path, "fsck", "--full", "--no-dangling").returncode:
                                        raise RetirementError("git-object-integrity-unproven")
                                    row["custody"] = self.custody.capture(
                                        proof_sources(observed), journal_root=campaign.root / "removals"
                                    )
                                row["proof_sha256"] = self._proof(observed, row["custody"], row.get("pre_sync_custody"))
                                row.update(status="preserved", reason="independent-acceptance-pending")
                                campaign.save()
                            if not self.keeper.accepted(row["proof_sha256"]):
                                row.update(status="preserved", reason="independent-acceptance-pending")
                                continue
                            with self.heavy():
                                if row.get("pre_sync_custody"):
                                    self.custody.verify(row["pre_sync_custody"], restore=False)
                                self.custody.verify(row["custody"], restore=False)
                                observed = self._verify_current(entry, row)
                                if (path / ".git").is_file():
                                    parent = next(
                                        (
                                            Path(w["worktree"])
                                            for w in observed["worktrees"]
                                            if (Path(w["worktree"]) / ".git").is_dir()
                                        ),
                                        None,
                                    )
                                    if parent is None:
                                        raise RetirementError("linked-worktree-parent-unavailable")
                                    row.update(status="removing", reason="native-detach-pending")
                                    campaign.save()
                                    prepare_linked(runtime, path, observed, row["custody"], campaign.save)
                                    removed = detach_registered_worktree(
                                        parent,
                                        path,
                                        reason="independently-accepted+full-custody+idle",
                                        receipt_root=campaign.root / "removals",
                                        owner_probe=self.owner_probe,
                                        git_runner=runtime.git,
                                    )
                                else:
                                    if len(observed["worktrees"]) != 1:
                                        raise RetirementError("common-store-still-has-dependent-worktrees")
                                    source = row["custody"]["sources"][0]
                                    info = path.lstat()
                                    expected = CustodyPathIdentity(
                                        str(path),
                                        hashlib.sha256(str(path).encode()).hexdigest(),
                                        info.st_dev,
                                        info.st_ino,
                                        info.st_mtime_ns,
                                    )
                                    row.update(status="removing", reason="journaled-purge-pending")
                                    campaign.save()
                                    removed = purge_custody_proven_path(
                                        path,
                                        expected,
                                        reason="custody-restored+idle",
                                        custody_plan_sha256=row["custody"]["digest"],
                                        custody_content_sha256=digest(source["records"]),
                                        receipt_root=campaign.root / "removals",
                                        owner_probe=self.owner_probe,
                                        content_probe=lambda p, expected_source=source: (  # type: ignore[misc]
                                            self.custody.verify_source(p, expected_source)
                                        ),
                                    )
                                row["removal"] = removed
                                campaign.save()
                            # Live remote readback is performed from a retained view,
                            # or against the captured authenticated URLs after purge.
                            self._remote_readback(observed)
                            if path.exists() or path.is_symlink():
                                raise RetirementError("physical-absence-unverified")
                            row.update(
                                status="removed",
                                reason=None,
                                removed_bytes=sum(v["physical_bytes"] for v in row["custody"]["sources"][0]["records"]),
                            )
                    except (RetirementError, WorktreeAbandonmentError, OSError, ValueError) as exc:
                        reason = str(exc) if isinstance(exc, RetirementError) else "journaled-operation-failed"
                        if isinstance(exc, WorktreeAbandonmentError):
                            row["removal"] = exc.receipt
                        row.update(status="retained", reason=reason)
                    finally:
                        campaign.save()
                        self.progress(
                            {
                                "candidate": digest(entry["path"])[:16],
                                "status": row["status"],
                                "reason": row.get("reason"),
                            }
                        )
                if self.keeper:
                    consumed, remaining = self.keeper.accounting()
                    campaign.state.update(agent_minutes_consumed=consumed, agent_minutes_remaining=remaining)
                    pending = {
                        digest(path)[:16]: row["proof_sha256"]
                        for path, row in campaign.state["candidates"].items()
                        if row["status"] == "preserved"
                    }
                    if pending and hasattr(self.keeper, "request_review"):
                        request_key = digest(pending)
                        if request_key not in campaign.state.setdefault("review_requests", {}):
                            campaign.state["review_requests"][request_key] = {"state": "requesting"}
                            campaign.save()
                            campaign.state["review_requests"][request_key] = {
                                "state": "reserved",
                                "receipt": self.keeper.request_review(pending),
                            }
                campaign.state["free_after"] = (
                    os.statvfs(existing[0].parent if existing else campaign.root).f_bavail
                    * os.statvfs(existing[0].parent if existing else campaign.root).f_frsize
                )
            finally:
                campaign.state["exits"].extend(runtime.exits)
                runtime.exits.clear()
                campaign.state["verification_seconds"] = runtime.verification_seconds
                campaign.state["attempts"][-1]["finished_at"] = datetime.now(UTC).isoformat()
                campaign.state["interrupted_attempt"] = False
                campaign.save()
            return campaign.summary()

    def _remote_readback(self, observed: dict) -> None:
        for remote in observed["remotes"].values():
            advertised = self.runtime.run(
                ["git", "-c", "core.fsmonitor=false", "ls-remote", "--heads", "--tags", remote["urls"][0]]
            )
            if advertised.returncode or digest(
                {ref: oid for oid, ref in (line.split("\t") for line in advertised.stdout.splitlines())}
            ) != digest(remote["refs"]):
                raise RetirementError("post-removal-remote-readback-changed")

    def accept(self) -> dict:
        proofs = {}
        with lock(self.campaign.root / "campaign.lock"):
            for entry in self.campaign.manifest["repositories"]:
                row = self.campaign.candidate(entry)
                if row["status"] != "preserved":
                    continue
                observed = row["observed"]
                with lock(self.campaign.root.parent / "locks" / (observed["key"].split(":")[1] + ".lock")):
                    self._verify_current(entry, row, review=True)
                    with self.heavy():
                        if row.get("pre_sync_custody"):
                            self.custody.verify(row["pre_sync_custody"])
                        self.custody.verify(row["custody"])
                    self._verify_current(entry, row, review=True)
                    proofs[digest(entry["path"])[:16]] = row["proof_sha256"]
            if not proofs:
                raise RetirementError("no-current-proofs-to-accept")
            result = self.keeper.report(proofs, review=True)
            self.campaign.state["independent_acceptance"] = result
            self.campaign.state["exits"].extend(self.runtime.exits)
            self.campaign.save()
            return result


def prepare_linked(runtime: Runtime, root: Path, observed: dict, custody: dict, save: Callable[[], None]) -> None:
    """Only prepare the exact tree whose original bytes were independently accepted."""
    tracked = runtime.text(root, "diff", "HEAD", "--name-only", "-z")
    payload = runtime.text(root, "ls-files", "--others", "--exclude-standard", "-z")
    payload += runtime.text(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z")
    names = sorted(set(payload.rstrip("\0").split("\0")) - {""}, key=lambda name: (-name.count("/"), name))
    custody["preparation"] = {"tracked": tracked, "payload": names, "state": "applying"}
    save()  # Crash before/after preparation never becomes an unrecorded deletion.
    if tracked:
        result = runtime.git(
            root,
            "restore",
            "--source=HEAD",
            "--staged",
            "--worktree",
            "--pathspec-from-file=-",
            "--pathspec-file-nul",
            data=tracked,
        )
        if result.returncode:
            raise RetirementError("captured-tracked-preparation-failed")
    # Git may list a whole untracked directory (e.g. a nested repository). Only
    # captured content can be removed; fd-isolated purge checks its own identity.
    captured = {value["relative"]: value for value in custody["sources"][0]["records"]}
    for name in names:
        runtime.check()
        target = root / name.rstrip("/")
        if root not in target.parents or ".git" in target.relative_to(root).parts:
            raise RetirementError("payload-preparation-path-unsafe")
        relative = target.relative_to(root).as_posix()
        if relative not in captured or asdict(_record(target, root)) != captured[relative]:
            raise RetirementError("payload-preparation-content-drift")
        if target.is_dir() and not target.is_symlink():
            expected = tuple(
                v
                for v in custody["sources"][0]["records"]
                if v["relative"] == relative or v["relative"].startswith(relative + "/")
            )
            from limen.personal_custody import ContentRecord

            subtree = tuple(
                ContentRecord(
                    **{**v, "relative": "." if v["relative"] == relative else v["relative"][len(relative) + 1 :]}
                )
                for v in expected
            )
            info = target.lstat()
            purge_custody_proven_path(
                target,
                CustodyPathIdentity(
                    str(target),
                    hashlib.sha256(str(target).encode()).hexdigest(),
                    info.st_dev,
                    info.st_ino,
                    info.st_mtime_ns,
                ),
                reason="custody-restored+idle",
                custody_plan_sha256=digest(custody),
                custody_content_sha256=digest(expected),
                receipt_root=Path(custody["journal_root"]),
                owner_probe=lambda p: process_owner(runtime, p),
                content_probe=lambda p, expected_subtree=subtree: (  # type: ignore[misc]
                    _assert_content(p, expected_subtree)
                ),
            )
        else:
            target.unlink()
    custody["preparation"]["state"] = "completed"
    save()
