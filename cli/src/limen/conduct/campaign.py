"""Resumable, exact-head census and packet planner for the whole open-PR estate."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    FanoutBoundsV1,
    ResourceClaimV1,
    RetryPolicyV1,
    SpendEnvelopeV1,
    WorkPacketV1,
    canonical_hash,
)
from limen.work_loan import WorkLoanV1


REPOSITORIES_QUERY = """
query($owner:String!, $cursor:String) {
  organization(login:$owner) {
    repositories(first:100, after:$cursor, orderBy:{field:NAME,direction:ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        isArchived
        defaultBranchRef { name target { oid } }
        pullRequests(states:OPEN) { totalCount }
      }
    }
  }
}
"""

PULL_REQUESTS_QUERY = """
query($owner:String!, $name:String!, $cursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequests(states:OPEN, first:100, after:$cursor, orderBy:{field:CREATED_AT,direction:ASC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        url
        isDraft
        createdAt
        updatedAt
        headRefName
        headRefOid
        baseRefName
        baseRefOid
        mergeable
        mergeStateStatus
        reviewDecision
        additions
        deletions
        changedFiles
        author { login }
      }
    }
  }
}
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CampaignModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RepositoryCensusV1(CampaignModel):
    schema_version: str = "limen.pr_repository_census.v1"
    name_with_owner: str
    archived: bool = False
    default_branch: str | None = None
    default_head: str | None = None
    advertised_open_prs: int = Field(ge=0)
    observed_open_prs: int = Field(ge=0)
    complete: bool
    page_count: int = Field(ge=0)


class PullRequestLeafV1(CampaignModel):
    schema_version: str = "limen.pr_leaf.v1"
    repo: str
    number: int = Field(ge=1)
    title: str
    url: str
    archived_repo: bool
    draft: bool
    created_at: str | None = None
    updated_at: str | None = None
    head_ref: str | None = None
    head_oid: str | None = None
    base_ref: str | None = None
    base_oid: str | None = None
    mergeable: str | None = None
    merge_state_status: str | None = None
    review_decision: str | None = None
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
    changed_files: int = Field(default=0, ge=0)
    author: str | None = None
    work_key: str
    disposition: str
    owner: str
    receipt_target: str
    eligible_action: str | None = None


class PullRequestCensusV1(CampaignModel):
    schema_version: str = "limen.pr_census.v1"
    owner: str
    generated_at: datetime
    repository_total: int = Field(ge=0)
    repositories_with_open_prs: int = Field(ge=0)
    advertised_open_prs: int = Field(ge=0)
    observed_open_prs: int = Field(ge=0)
    complete: bool
    errors: tuple[str, ...] = ()
    repositories: tuple[RepositoryCensusV1, ...]
    leaves: tuple[PullRequestLeafV1, ...]
    snapshot_digest: str


class GraphQL(Protocol):
    def __call__(self, query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]: ...


def gh_graphql(query: str, variables: Mapping[str, Any]) -> Mapping[str, Any]:
    argv = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is not None:
            argv.extend(["-F", f"{key}={value}"])
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "GraphQL request failed").strip().replace("\n", " ")[:500]
        raise RuntimeError(detail)
    payload = json.loads(proc.stdout)
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], sort_keys=True)[:500])
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("GraphQL response omitted data")
    return data


def _connection_pages(
    fetch: Callable[[str | None], Mapping[str, Any]],
    *,
    max_pages: int,
) -> tuple[list[dict[str, Any]], int, int, bool]:
    cursor: str | None = None
    seen_cursors: set[str] = set()
    nodes: list[dict[str, Any]] = []
    advertised_total: int | None = None
    pages = 0
    while True:
        if pages >= max_pages:
            return nodes, int(advertised_total or 0), pages, False
        connection = fetch(cursor)
        pages += 1
        if advertised_total is None:
            advertised_total = int(connection.get("totalCount") or 0)
        raw_nodes = connection.get("nodes")
        if not isinstance(raw_nodes, list):
            return nodes, int(advertised_total or 0), pages, False
        nodes.extend(node for node in raw_nodes if isinstance(node, dict))
        page_info = connection.get("pageInfo")
        if not isinstance(page_info, dict):
            return nodes, int(advertised_total or 0), pages, False
        if not bool(page_info.get("hasNextPage")):
            return nodes, int(advertised_total or 0), pages, len(nodes) == int(advertised_total or 0)
        next_cursor = page_info.get("endCursor")
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
            return nodes, int(advertised_total or 0), pages, False
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _disposition(repo: Mapping[str, Any], pr: Mapping[str, Any]) -> tuple[str, str | None]:
    if not pr.get("headRefOid"):
        return "missing-head", None
    if bool(repo.get("isArchived")):
        return "archived-repository", None
    if bool(pr.get("isDraft")):
        return "preservation-draft", None
    if int(pr.get("changedFiles") or 0) == 0 or int(pr.get("additions") or 0) + int(pr.get("deletions") or 0) == 0:
        return "empty-diff", None
    return "review-candidate", "exact-head-review"


def _leaf(repo: Mapping[str, Any], pr: Mapping[str, Any]) -> PullRequestLeafV1:
    repo_name = str(repo.get("nameWithOwner") or "")
    number = int(pr.get("number") or 0)
    head = str(pr.get("headRefOid") or "") or None
    disposition, eligible_action = _disposition(repo, pr)
    work_key = f"{repo_name}#{number}@{head or 'missing'}"
    return PullRequestLeafV1(
        repo=repo_name,
        number=number,
        title=str(pr.get("title") or ""),
        url=str(pr.get("url") or ""),
        archived_repo=bool(repo.get("isArchived")),
        draft=bool(pr.get("isDraft")),
        created_at=pr.get("createdAt"),
        updated_at=pr.get("updatedAt"),
        head_ref=pr.get("headRefName"),
        head_oid=head,
        base_ref=pr.get("baseRefName"),
        base_oid=pr.get("baseRefOid"),
        mergeable=pr.get("mergeable"),
        merge_state_status=pr.get("mergeStateStatus"),
        review_decision=pr.get("reviewDecision"),
        additions=int(pr.get("additions") or 0),
        deletions=int(pr.get("deletions") or 0),
        changed_files=int(pr.get("changedFiles") or 0),
        author=(pr.get("author") or {}).get("login") if isinstance(pr.get("author"), dict) else None,
        work_key=work_key,
        disposition=disposition,
        owner="limen-conduct-broker",
        receipt_target=f"github:{repo_name}:pull-request:{number}@{head or 'missing'}",
        eligible_action=eligible_action,
    )


def build_census(
    owner: str,
    *,
    graphql: GraphQL = gh_graphql,
    generated_at: datetime | None = None,
    max_pages: int = 10000,
) -> PullRequestCensusV1:
    generated_at = generated_at or utc_now()
    errors: list[str] = []

    def fetch_repos(cursor: str | None) -> Mapping[str, Any]:
        data = graphql(REPOSITORIES_QUERY, {"owner": owner, "cursor": cursor})
        organization = data.get("organization")
        if not isinstance(organization, dict) or not isinstance(organization.get("repositories"), dict):
            raise RuntimeError(f"organization not found or repository connection unavailable: {owner}")
        return organization["repositories"]

    try:
        repositories, repository_total, _, repositories_complete = _connection_pages(fetch_repos, max_pages=max_pages)
    except Exception as exc:
        raise RuntimeError(f"cannot enumerate {owner} repositories: {exc}") from exc

    repo_receipts: list[RepositoryCensusV1] = []
    leaves: list[PullRequestLeafV1] = []
    for repo in sorted(repositories, key=lambda item: str(item.get("nameWithOwner") or "").casefold()):
        repo_name = str(repo.get("nameWithOwner") or "")
        advertised = int((repo.get("pullRequests") or {}).get("totalCount") or 0)
        if advertised == 0:
            repo_receipts.append(
                RepositoryCensusV1(
                    name_with_owner=repo_name,
                    archived=bool(repo.get("isArchived")),
                    default_branch=((repo.get("defaultBranchRef") or {}).get("name")),
                    default_head=(((repo.get("defaultBranchRef") or {}).get("target") or {}).get("oid")),
                    advertised_open_prs=0,
                    observed_open_prs=0,
                    complete=True,
                    page_count=0,
                )
            )
            continue
        try:
            repo_owner, name = repo_name.split("/", 1)

            def fetch_prs(cursor: str | None) -> Mapping[str, Any]:
                data = graphql(PULL_REQUESTS_QUERY, {"owner": repo_owner, "name": name, "cursor": cursor})
                repository = data.get("repository")
                if not isinstance(repository, dict) or not isinstance(repository.get("pullRequests"), dict):
                    raise RuntimeError("pullRequests connection unavailable")
                return repository["pullRequests"]

            pull_requests, pr_total, page_count, pr_complete = _connection_pages(fetch_prs, max_pages=max_pages)
            if pr_total != advertised:
                pr_complete = False
                errors.append(f"{repo_name}: repository count {advertised} != PR connection count {pr_total}")
            leaves.extend(_leaf(repo, pr) for pr in pull_requests)
        except Exception as exc:
            pull_requests = []
            page_count = 0
            pr_complete = False
            errors.append(f"{repo_name}: {exc}")
        repo_receipts.append(
            RepositoryCensusV1(
                name_with_owner=repo_name,
                archived=bool(repo.get("isArchived")),
                default_branch=((repo.get("defaultBranchRef") or {}).get("name")),
                default_head=(((repo.get("defaultBranchRef") or {}).get("target") or {}).get("oid")),
                advertised_open_prs=advertised,
                observed_open_prs=len(pull_requests),
                complete=pr_complete,
                page_count=page_count,
            )
        )

    leaves.sort(key=lambda leaf: (leaf.repo.casefold(), leaf.number, leaf.head_oid or ""))
    work_keys = [leaf.work_key for leaf in leaves]
    if len(work_keys) != len(set(work_keys)):
        errors.append("duplicate repo#PR@head work keys detected")
    advertised_open_prs = sum(repo.advertised_open_prs for repo in repo_receipts)
    complete = (
        repositories_complete
        and len(repositories) == repository_total
        and advertised_open_prs == len(leaves)
        and all(repo.complete for repo in repo_receipts)
        and not errors
    )
    digest_payload = [leaf.model_dump(mode="json") for leaf in leaves]
    digest = canonical_hash(digest_payload)
    return PullRequestCensusV1(
        owner=owner,
        generated_at=generated_at,
        repository_total=repository_total,
        repositories_with_open_prs=sum(1 for repo in repo_receipts if repo.advertised_open_prs),
        advertised_open_prs=advertised_open_prs,
        observed_open_prs=len(leaves),
        complete=complete,
        errors=tuple(errors),
        repositories=tuple(repo_receipts),
        leaves=tuple(leaves),
        snapshot_digest=digest,
    )


def compare_censuses(previous: PullRequestCensusV1, current: PullRequestCensusV1) -> dict[str, Any]:
    prior = {leaf.work_key: leaf for leaf in previous.leaves}
    present = {leaf.work_key: leaf for leaf in current.leaves}
    prior_prs = {(leaf.repo, leaf.number): leaf.work_key for leaf in previous.leaves}
    present_prs = {(leaf.repo, leaf.number): leaf.work_key for leaf in current.leaves}
    moved = sorted(
        {
            key: {"previous": prior_prs[key], "current": present_prs[key]}
            for key in prior_prs.keys() & present_prs.keys()
            if prior_prs[key] != present_prs[key]
        }.items()
    )
    new_keys = sorted(present.keys() - prior.keys())
    missing_keys = sorted(prior.keys() - present.keys())
    return {
        "schema_version": "limen.pr_census_comparison.v1",
        "previous_digest": previous.snapshot_digest,
        "current_digest": current.snapshot_digest,
        "new_work_keys": new_keys,
        "missing_work_keys": missing_keys,
        "moved_heads": [{"repo_pr": f"{key[0]}#{key[1]}", **value} for key, value in moved],
        "zero_growth": current.complete and not new_keys and not moved,
        "byte_stable": previous.snapshot_digest == current.snapshot_digest,
    }


def campaign_packets(
    census: PullRequestCensusV1,
    *,
    conductor: AgentIdentityV1,
    deadline: datetime,
    spend_limit: int,
) -> tuple[WorkPacketV1, CampaignPacketFactory]:
    """Build a deterministic root plus a parent-id-aware cohort/leaf packet factory."""

    if not census.complete:
        raise ValueError("incomplete census cannot underwrite a campaign")
    if spend_limit <= 0:
        raise ValueError("campaign spend_limit must be positive and explicitly underwritten")
    eligible_by_repo: dict[str, list[PullRequestLeafV1]] = {}
    for leaf in census.leaves:
        if leaf.eligible_action:
            eligible_by_repo.setdefault(leaf.repo, []).append(leaf)
    root_work_id = f"pr-campaign-{census.owner}-{census.snapshot_digest[:20]}"
    receipt_path = f"docs/receipts/pr-campaign/{census.snapshot_digest}.json"
    root = WorkPacketV1(
        work_id=root_work_id,
        work_key=f"estate/{census.owner}/open-prs/{census.snapshot_digest}",
        intent={
            "kind": "pr-campaign.root",
            "owner": census.owner,
            "snapshot_digest": census.snapshot_digest,
            "open_prs": census.observed_open_prs,
        },
        execution={"adapter": "pr-campaign", "mode": "plan"},
        initiator=conductor,
        conductor=conductor,
        required_capabilities=frozenset({"conduct"}),
        resource_claims=(),
        predicate=(
            f"python3 scripts/conduct-pr-campaign.py validate --current {receipt_path} "
            f"--digest {census.snapshot_digest}"
        ),
        receipt_target=f"git:organvm/limen:{receipt_path}",
        work_loan=WorkLoanV1(
            source_origin="system_debt",
            horizon="present",
            value_case=f"Close exact-head lifecycle debt across the live {census.owner} pull-request census",
            budget_cost=spend_limit,
            owner_surface=f"github:{census.owner}",
        ),
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"pr.inspect", "pr.review", "pr.repair"}),
            repositories=frozenset(eligible_by_repo),
            may_delegate=True,
        ),
        deadline=deadline,
        spend=SpendEnvelopeV1(limit=spend_limit),
        retry=RetryPolicyV1(max_attempts=2),
        fanout=FanoutBoundsV1(
            max_children=max([len(eligible_by_repo), 3] + [len(leaves) for leaves in eligible_by_repo.values()]),
            max_depth=3,
        ),
        effect="read",
    )

    return root, CampaignPacketFactory(
        census=census,
        conductor=conductor,
        deadline=deadline,
        spend_limit=spend_limit,
        root_work_id=root_work_id,
        eligible_by_repo={repo: tuple(leaves) for repo, leaves in eligible_by_repo.items()},
        receipt_path=receipt_path,
    )


@dataclass(frozen=True)
class CampaignPacketFactory:
    """Create parent-aware cohorts and exact-head leaves without inventing run ids."""

    census: PullRequestCensusV1
    conductor: AgentIdentityV1
    deadline: datetime
    spend_limit: int
    root_work_id: str
    eligible_by_repo: Mapping[str, tuple[PullRequestLeafV1, ...]]
    receipt_path: str

    def __call__(self, root_run_id: str) -> Iterable[WorkPacketV1]:
        for repo in sorted(self.eligible_by_repo, key=str.casefold):
            leaves = sorted(self.eligible_by_repo[repo], key=lambda leaf: (leaf.number, leaf.head_oid or ""))
            cohort_id = "cohort-" + hashlib.sha256(f"{self.root_work_id}:{repo}".encode()).hexdigest()[:24]
            cohort = WorkPacketV1(
                root_run_id=root_run_id,
                parent_run_id=root_run_id,
                work_id=cohort_id,
                work_key=f"cohort/{repo}/{self.census.snapshot_digest}",
                intent={"kind": "pr-campaign.cohort", "repo": repo, "leaf_count": len(leaves)},
                execution={"adapter": "pr-campaign", "mode": "cohort"},
                initiator=self.conductor,
                conductor=self.conductor,
                required_capabilities=frozenset({"conduct"}),
                resource_claims=(),
                predicate=(
                    f"python3 scripts/conduct-pr-campaign.py validate --current {self.receipt_path} "
                    f"--digest {self.census.snapshot_digest} --repo {shlex.quote(repo)}"
                ),
                receipt_target=f"git:organvm/limen:{self.receipt_path}",
                work_loan=WorkLoanV1(
                    source_origin="system_debt",
                    horizon="present",
                    value_case=f"Route and close the live exact-head pull-request cohort for {repo}",
                    budget_cost=min(self.spend_limit, len(leaves)),
                    owner_surface=f"github:{repo}",
                ),
                authority=AuthorityEnvelopeV1(
                    actions=frozenset({"pr.inspect", "pr.review", "pr.repair"}),
                    repositories=frozenset({repo}),
                    may_delegate=True,
                ),
                deadline=self.deadline,
                spend=SpendEnvelopeV1(limit=min(self.spend_limit, len(leaves))),
                retry=RetryPolicyV1(max_attempts=2),
                depth=1,
                fanout=FanoutBoundsV1(max_children=max(len(leaves), 3), max_depth=3),
                effect="read",
            )
            yield cohort

    def leaves(self, cohort_run_id: str, cohort: WorkPacketV1) -> Iterable[WorkPacketV1]:
        repo = str(cohort.intent.get("repo") or "")
        if cohort.depth != 1 or repo not in self.eligible_by_repo:
            raise ValueError("cohort packet is not owned by this campaign")
        for leaf in sorted(
            self.eligible_by_repo[repo],
            key=lambda candidate: (candidate.number, candidate.head_oid or ""),
        ):
            if not leaf.head_oid:
                continue
            leaf_digest = hashlib.sha256(f"{self.root_work_id}:{leaf.work_key}:route".encode()).hexdigest()[:24]
            predicate = (
                f'test "$(gh pr view {leaf.number} --repo {shlex.quote(repo)} '
                f'--json headRefOid --jq .headRefOid)" = {shlex.quote(leaf.head_oid)}'
            )
            yield WorkPacketV1(
                root_run_id=cohort.root_run_id,
                parent_run_id=cohort_run_id,
                work_id=f"pr-route-{leaf_digest}",
                work_key=f"route/{repo}/{leaf.number}@{leaf.head_oid}",
                intent={
                    "kind": "pr-campaign.leaf",
                    "repo": repo,
                    "number": leaf.number,
                    "head": leaf.head_oid,
                    "disposition": leaf.disposition,
                    "eligible_action": leaf.eligible_action,
                },
                execution={
                    "adapter": "pr-campaign",
                    "mode": "inspect-route",
                    "observed_heads": {
                        f"pr/{repo}/{leaf.number}": leaf.head_oid,
                    },
                    "routing": {
                        "copilot_review": "active nontrivial exact head lacking Copilot receipt",
                        "same_branch_repair": ("review findings, branch-attributable CI, conflict, or stale base"),
                        "root_fix": "one packet for a shared-main failure",
                        "independent_peer": True,
                    },
                },
                initiator=self.conductor,
                conductor=self.conductor,
                required_capabilities=frozenset({"inspect"}),
                resource_claims=(
                    ResourceClaimV1(
                        key=f"pr/{repo}/{leaf.number}/review/campaign-route@{leaf.head_oid}",
                        mode="exclusive",
                    ),
                ),
                predicate=predicate,
                receipt_target=leaf.receipt_target,
                work_loan=WorkLoanV1(
                    source_origin="system_debt",
                    horizon="present",
                    value_case=f"Resolve or owner-route exact-head lifecycle debt for {repo}#{leaf.number}",
                    budget_cost=min(self.spend_limit, 1),
                    owner_surface=f"github:{repo}#{leaf.number}",
                ),
                authority=AuthorityEnvelopeV1(
                    actions=frozenset({"pr.inspect", "pr.review", "pr.repair"}),
                    repositories=frozenset({repo}),
                    may_delegate=True,
                ),
                deadline=self.deadline,
                spend=SpendEnvelopeV1(limit=min(self.spend_limit, 1)),
                retry=RetryPolicyV1(max_attempts=2),
                depth=2,
                fanout=FanoutBoundsV1(max_children=3, max_depth=3),
                effect="read",
            )


def write_census(path: Path, census: PullRequestCensusV1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(census.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_census(path: Path) -> PullRequestCensusV1:
    return PullRequestCensusV1.model_validate_json(path.read_text(encoding="utf-8"))
