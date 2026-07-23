"""Canonical resource ordering and overlap rules for peer-safe parallelism."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from limen.conduct.models import ResourceClaimV1

_PR_RE = re.compile(
    r"^pr/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<number>[0-9]+)"
    r"/(?P<kind>write|review/(?P<provider>[^@/]+))@(?P<head>[A-Za-z0-9._+-]+)$"
)
_REPO_KIND_RE = re.compile(
    r"^(?P<kind>branch|base|repo-common-dir|agy-scratch|repo)/"
    r"(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:/(?P<rest>.*))?$"
)
_PATH_RE = re.compile(r"^path/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<base>[^/]+)/(?P<prefix>.*)$")


@dataclass(frozen=True)
class Resource:
    raw: str
    kind: str
    repo: str | None = None
    identity: tuple[str, ...] = ()
    prefix: str | None = None


def normalize_key(key: str) -> str:
    key = key.strip().rstrip("/")
    if key.startswith("worktree/"):
        raw_path = key.removeprefix("worktree/") or "/"
        return f"worktree/{posixpath.normpath(raw_path)}"
    pr_match = _PR_RE.fullmatch(key)
    if pr_match:
        kind = f"review/{pr_match.group('provider')}" if pr_match.group("provider") else "write"
        return (
            f"pr/{pr_match.group('owner').lower()}/{pr_match.group('repo').lower()}/"
            f"{pr_match.group('number')}/{kind}@{pr_match.group('head')}"
        )
    if key.startswith("path/"):
        match = _PATH_RE.fullmatch(key)
        if match:
            prefix = posixpath.normpath("/" + match.group("prefix")).lstrip("/")
            return (
                f"path/{match.group('owner').lower()}/{match.group('repo').lower()}/{match.group('base')}/{prefix}"
            ).rstrip("/")
    repo_match = _REPO_KIND_RE.fullmatch(key)
    if repo_match:
        rest = repo_match.group("rest")
        suffix = f"/{rest}" if rest else ""
        return (
            f"{repo_match.group('kind')}/{repo_match.group('owner').lower()}/{repo_match.group('repo').lower()}{suffix}"
        )
    return key


def parse_resource(key: str) -> Resource:
    key = normalize_key(key)
    if key.startswith("task/"):
        return Resource(key, "task", identity=(key.removeprefix("task/"),))
    if key.startswith("external/"):
        return Resource(key, "external", identity=(key.removeprefix("external/"),))
    if key.startswith("worktree/"):
        return Resource(key, "worktree", identity=(key.removeprefix("worktree/"),))
    pr_match = _PR_RE.fullmatch(key)
    if pr_match:
        repo = f"{pr_match.group('owner')}/{pr_match.group('repo')}"
        kind = "pr-review" if pr_match.group("provider") else "pr-write"
        identity = (repo, pr_match.group("number"), pr_match.group("provider") or "")
        return Resource(key, kind, repo=repo, identity=identity)
    path_match = _PATH_RE.fullmatch(key)
    if path_match:
        repo = f"{path_match.group('owner')}/{path_match.group('repo')}"
        return Resource(
            key,
            "path",
            repo=repo,
            identity=(repo, path_match.group("base")),
            prefix=str(PurePosixPath("/" + path_match.group("prefix"))),
        )
    repo_match = _REPO_KIND_RE.fullmatch(key)
    if repo_match:
        repo = f"{repo_match.group('owner')}/{repo_match.group('repo')}"
        kind = repo_match.group("kind")
        rest = repo_match.group("rest") or ""
        if kind == "base" and rest.endswith("/integrate"):
            rest = rest[: -len("/integrate")]
            kind = "base-integrate"
        elif kind == "repo-common-dir" and rest == "plumbing":
            kind = "repo-plumbing"
        elif kind == "repo" and rest == "write":
            kind = "repo-write"
        return Resource(key, kind, repo=repo, identity=(repo, rest))
    return Resource(key, "opaque", identity=(key,))


def _prefixes_overlap(left: str, right: str) -> bool:
    left = str(PurePosixPath(left))
    right = str(PurePosixPath(right))
    return left == right or left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/")


def resources_overlap(left: ResourceClaimV1, right: ResourceClaimV1) -> bool:
    """Return whether two claims contend under the conduct protocol."""

    a = parse_resource(left.key)
    b = parse_resource(right.key)
    if a.kind == b.kind == "pr-review" and a.identity == b.identity:
        # One provider receipt per exact PR head, even if a caller mislabeled
        # the read-oriented review lease as shared.
        return True
    shareable = {"path"}
    if left.mode == right.mode == "shared" and a.kind in shareable and b.kind in shareable:
        return False
    if a.raw == b.raw:
        return True
    if a.kind == "repo-write" and (a.repo == "*/*" or a.repo == b.repo):
        return b.kind not in {"pr-review"}
    if b.kind == "repo-write" and (b.repo == "*/*" or b.repo == a.repo):
        return a.kind not in {"pr-review"}
    if a.kind == b.kind == "pr-write":
        return a.identity[:2] == b.identity[:2]
    if "pr-review" in {a.kind, b.kind}:
        # Review keys are deliberately independent from writers and from other providers.
        return a.kind == b.kind and a.identity == b.identity
    if a.kind == b.kind == "path":
        return a.identity == b.identity and bool(a.prefix and b.prefix and _prefixes_overlap(a.prefix, b.prefix))
    if a.kind == b.kind == "branch":
        return a.identity == b.identity
    if {a.kind, b.kind} == {"branch", "path"} and a.repo == b.repo:
        branch = a if a.kind == "branch" else b
        path = b if b.kind == "path" else a
        return bool(branch.identity[1] and path.identity[1] == branch.identity[1])
    if a.kind == b.kind == "worktree":
        return a.identity == b.identity
    if a.kind == b.kind and a.kind in {
        "task",
        "external",
        "repo-plumbing",
        "base-integrate",
        "agy-scratch",
        "opaque",
    }:
        return a.identity == b.identity
    return False


def conflicting_keys(
    requested: tuple[ResourceClaimV1, ...] | list[ResourceClaimV1],
    held: tuple[ResourceClaimV1, ...] | list[ResourceClaimV1],
) -> list[tuple[str, str]]:
    return sorted(
        {
            (normalize_key(left.key), normalize_key(right.key))
            for left in requested
            for right in held
            if resources_overlap(left, right)
        }
    )


def sorted_claims(claims: tuple[ResourceClaimV1, ...] | list[ResourceClaimV1]) -> tuple[ResourceClaimV1, ...]:
    dedup: dict[str, ResourceClaimV1] = {}
    for claim in claims:
        normalized = normalize_key(claim.key)
        current = dedup.get(normalized)
        mode: Literal["shared", "exclusive"] = (
            "exclusive" if claim.mode == "exclusive" or current and current.mode == "exclusive" else "shared"
        )
        dedup[normalized] = ResourceClaimV1(key=normalized, mode=mode)
    return tuple(dedup[key] for key in sorted(dedup))
