"""Shared visibility intent; migration intent never authorizes a blind flip."""
from __future__ import annotations


def visibility_intent(estate: dict, full: str, class_visibility: str | None, facts: dict | None = None):
    override = (estate.get("repo_overrides") or {}).get(full) or {}
    candidate = bool(override.get("publish_candidate"))
    policy = estate.get("personal_consolidation") or {}
    owner = full.partition("/")[0]
    scope = [policy.get("target"), *(policy.get("sources") or [])]
    if policy.get("enabled") is True and owner in scope:
        desired = policy["default_visibility"]
        for exception in policy.get("public_exceptions") or []:
            repo_id = (facts or {}).get("id")
            matches = (repo_id == exception.get("repository_id") if repo_id is not None
                       else full in exception.get("coordinates", []))
            if matches:
                desired = "public"
                break
        return desired, False, True
    return ("public" if candidate else class_visibility), candidate, False
