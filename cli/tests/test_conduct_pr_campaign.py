from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen.conduct.campaign import (
    PULL_REQUESTS_QUERY,
    REPOSITORIES_QUERY,
    build_census,
    campaign_packets,
    compare_censuses,
)
from limen.conduct.models import AgentIdentityV1

NOW = datetime(2026, 7, 18, 15, 0, tzinfo=UTC)


class FakeGraphQL:
    def __init__(self, repos: dict[str, int]):
        self.repos = repos
        self.calls = []

    def __call__(self, query, variables):
        self.calls.append((query, dict(variables)))
        if query == REPOSITORIES_QUERY:
            names = sorted(self.repos)
            start = int(variables.get("cursor") or 0)
            page = names[start : start + 100]
            end = start + len(page)
            return {
                "organization": {
                    "repositories": {
                        "totalCount": len(names),
                        "pageInfo": {
                            "hasNextPage": end < len(names),
                            "endCursor": str(end) if end < len(names) else None,
                        },
                        "nodes": [
                            {
                                "nameWithOwner": name,
                                "isArchived": name.endswith("archived"),
                                "defaultBranchRef": {"name": "main", "target": {"oid": f"base-{name}"}},
                                "pullRequests": {"totalCount": self.repos[name]},
                            }
                            for name in page
                        ],
                    }
                }
            }
        if query == PULL_REQUESTS_QUERY:
            name = f"{variables['owner']}/{variables['name']}"
            total = self.repos[name]
            start = int(variables.get("cursor") or 0)
            numbers = range(start + 1, min(start + 100, total) + 1)
            end = min(start + 100, total)
            return {
                "repository": {
                    "pullRequests": {
                        "totalCount": total,
                        "pageInfo": {"hasNextPage": end < total, "endCursor": str(end) if end < total else None},
                        "nodes": [
                            {
                                "number": number,
                                "title": f"PR {number}",
                                "url": f"https://github.com/{name}/pull/{number}",
                                "isDraft": False,
                                "createdAt": NOW.isoformat(),
                                "updatedAt": NOW.isoformat(),
                                "headRefName": f"branch-{number}",
                                "headRefOid": f"head-{name}-{number}",
                                "baseRefName": "main",
                                "baseRefOid": f"base-{name}",
                                "mergeable": "MERGEABLE",
                                "mergeStateStatus": "CLEAN",
                                "reviewDecision": None,
                                "additions": 2,
                                "deletions": 1,
                                "changedFiles": 1,
                                "author": {"login": "bot"},
                            }
                            for number in numbers
                        ],
                    }
                }
            }
        raise AssertionError("unexpected query")


def test_full_pagination_beyond_one_thousand_and_one_hundred_per_repo() -> None:
    repos = {f"organvm/repo-{index:03d}": 9 for index in range(111)}
    repos["organvm/large"] = 104
    graphql = FakeGraphQL(repos)
    census = build_census("organvm", graphql=graphql, generated_at=NOW)
    assert census.complete is True
    assert census.repository_total == 112
    assert census.advertised_open_prs == 1103
    assert census.observed_open_prs == 1103
    assert len(census.leaves) == 1103
    assert next(repo for repo in census.repositories if repo.name_with_owner == "organvm/large").page_count == 2
    repo_pages = [call for call in graphql.calls if call[0] == REPOSITORIES_QUERY]
    assert len(repo_pages) == 2


def test_incomplete_connection_fails_closed() -> None:
    graphql = FakeGraphQL({"organvm/one": 101})
    census = build_census("organvm", graphql=graphql, generated_at=NOW, max_pages=1)
    assert census.complete is False
    assert census.observed_open_prs == 100


def test_zero_growth_distinguishes_stability_from_moved_head() -> None:
    graphql = FakeGraphQL({"organvm/one": 2})
    first = build_census("organvm", graphql=graphql, generated_at=NOW)
    second = build_census("organvm", graphql=graphql, generated_at=NOW + timedelta(minutes=1))
    assert compare_censuses(first, second)["zero_growth"] is True
    mutated = second.model_copy(
        update={
            "leaves": (
                second.leaves[0].model_copy(
                    update={
                        "head_oid": "moved",
                        "work_key": "organvm/one#1@moved",
                    }
                ),
                second.leaves[1],
            )
        }
    )
    comparison = compare_censuses(first, mutated)
    assert comparison["zero_growth"] is False
    assert comparison["moved_heads"][0]["repo_pr"] == "organvm/one#1"


def test_campaign_packet_decomposition_is_deterministic_and_bounded() -> None:
    census = build_census("organvm", graphql=FakeGraphQL({"organvm/two": 2}), generated_at=NOW)
    conductor = AgentIdentityV1(agent="codex", surface="cli", session_id="session")
    root, children = campaign_packets(
        census,
        conductor=conductor,
        deadline=NOW + timedelta(hours=1),
        spend_limit=10,
    )
    cohorts = list(children("run-root"))
    assert root.work_key.endswith(census.snapshot_digest)
    assert root.work_loan is not None
    assert root.work_loan.budget_cost == root.spend.limit == 10
    assert len(cohorts) == 1
    assert cohorts[0].parent_run_id == "run-root"
    assert cohorts[0].authority.repositories == frozenset({"organvm/two"})
    assert cohorts[0].fanout.max_children == 3
    assert cohorts[0].work_loan is not None
    assert cohorts[0].work_loan.owner_surface == "github:organvm/two"
    leaves = list(children.leaves("run-cohort", cohorts[0]))
    assert [leaf.intent["number"] for leaf in leaves] == [1, 2]
    assert all(leaf.parent_run_id == "run-cohort" for leaf in leaves)
    assert all(leaf.intent["head"] in leaf.predicate for leaf in leaves)
    assert all(leaf.resource_claims[0].key.endswith(f"@{leaf.intent['head']}") for leaf in leaves)
    assert all(leaf.work_loan is not None and leaf.work_loan.budget_cost == 1 for leaf in leaves)
