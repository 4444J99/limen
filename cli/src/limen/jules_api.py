"""Bounded Jules REST transport. No scheduler, queue, lease issuer, or merge authority.

Mutating methods are for already-admitted executors. A failed observation after a
POST is indeterminate, never evidence that another session may safely be created.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

API = "https://jules.googleapis.com/v1alpha/"
TERMINAL = frozenset({"COMPLETED", "FAILED"})
STATES = TERMINAL | frozenset(
    {"QUEUED", "PLANNING", "AWAITING_PLAN_APPROVAL", "AWAITING_USER_FEEDBACK", "IN_PROGRESS", "PAUSED"}
)
_RESOURCE = re.compile(r"sessions/[A-Za-z0-9_-]{1,128}\Z")
_SOURCE = re.compile(r"sources/github/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?(?:Z|[+-]\d\d:\d\d)\Z")


class JulesApiError(RuntimeError):
    """Only a bounded classification is exposed; provider bodies can contain secrets."""

    def __init__(self, code: str, status: int | None = None):
        self.code = code
        self.status = status
        super().__init__(code + (f" (HTTP {status})" if status is not None else ""))


class JulesMutationUnknown(JulesApiError):
    """The provider may have accepted a mutation. Reconcile; do not blindly retry."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _transport(method: str, path: str, key: str, payload: dict | None, timeout: float, ceiling: int) -> dict:
    body = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=body,
        method=method,
        headers={
            "X-Goog-Api-Key": key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            raw = response.read(ceiling + 1)
    except urllib.error.HTTPError as exc:
        # Never reflect the response body, request headers or exception URL.
        cls = JulesMutationUnknown if method != "GET" and (exc.code >= 500 or exc.code in {408, 425}) else JulesApiError
        raise cls("provider_rejected" if cls is JulesApiError else "mutation_outcome_unknown", exc.code) from None
    except (OSError, TimeoutError, urllib.error.URLError):
        cls = JulesApiError if method == "GET" else JulesMutationUnknown
        raise cls("transport_unavailable" if method == "GET" else "mutation_outcome_unknown") from None
    if len(raw) > ceiling:
        cls = JulesApiError if method == "GET" else JulesMutationUnknown
        raise cls("response_limit_exceeded")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object) if raw else {}
        if not isinstance(value, dict) or "error" in value:
            raise ValueError
    except (ValueError, UnicodeError):
        cls = JulesApiError if method == "GET" else JulesMutationUnknown
        raise cls("invalid_response") from None
    return value


def timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not _STAMP.fullmatch(value):
        raise JulesApiError("invalid_provider_timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        raise JulesApiError("invalid_provider_timestamp") from None


def session_name(value: str) -> str:
    name = value if value.startswith("sessions/") else "sessions/" + value
    if not _RESOURCE.fullmatch(name):
        raise JulesApiError("invalid_session_name")
    return name


def session_identity(row: dict) -> str:
    name = row.get("name", "")
    if not isinstance(name, str) or not _RESOURCE.fullmatch(name):
        raise JulesApiError("invalid_session_identity")
    if row.get("id", name.split("/")[1]) != name.split("/")[1]:
        raise JulesApiError("inconsistent_session_identity")
    return name


@dataclass(frozen=True)
class Catalog:
    items: tuple[dict, ...]
    pages: int
    observed_at: str
    # True means pagination completed; NOT a transactional snapshot or billing ledger.
    pagination_complete: bool = True


class JulesApiClient:
    def __init__(
        self,
        key: str,
        *,
        transport: Callable = _transport,
        timeout: float = 15,
        total_timeout: float = 90,
        max_pages: int = 100,
        max_bytes: int = 4 * 1024 * 1024,
    ):
        if not isinstance(key, str) or not key.strip() or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise JulesApiError("jules_api_key_missing_or_invalid")
        if not (
            0 < timeout <= 60
            and 0 < total_timeout <= 600
            and 1 <= max_pages <= 1000
            and 1024 <= max_bytes <= 16 * 1024 * 1024
        ):
            raise JulesApiError("invalid_transport_limits")
        self._key = key
        self._transport = transport
        self.timeout, self.total_timeout = timeout, total_timeout
        self.max_pages, self.max_bytes = max_pages, max_bytes

    @classmethod
    def from_env(cls):
        return cls(os.environ.get("JULES_API_KEY", ""))

    def _request(self, method: str, path: str, payload: dict | None = None, *, timeout: float | None = None) -> dict:
        # Only closed resource paths constructed below reach this transport.
        if not re.fullmatch(
            r"(?:sessions(?:/[A-Za-z0-9_-]+)?(?::(?:approvePlan|sendMessage)|/activities)?|sources(?:/github/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?)(?:\?[^\r\n]*)?",
            path,
        ):
            raise JulesApiError("invalid_resource_path")
        return self._transport(method, path, self._key, payload, timeout or self.timeout, self.max_bytes)

    def _list(self, path: str, field: str) -> Catalog:
        deadline = time.monotonic() + self.total_timeout
        token = ""
        seen_tokens: set[str] = set()
        rows: dict[str, dict] = {}
        for page in range(1, self.max_pages + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JulesApiError("pagination_deadline_exceeded")
            query: dict[str, int | str] = {"pageSize": 100}
            if token:
                query["pageToken"] = token
            result = self._request(
                "GET", path + "?" + urllib.parse.urlencode(query), timeout=min(self.timeout, remaining)
            )
            batch = result.get(field, [])
            if not isinstance(batch, list) or any(not isinstance(row, dict) for row in batch):
                raise JulesApiError("invalid_catalog")
            for row in batch:
                name = row.get("name")
                if not isinstance(name, str) or not name:
                    raise JulesApiError("invalid_catalog_identity")
                if field == "sessions":
                    session_identity(row)
                elif field == "sources" and not _SOURCE.fullmatch(name):
                    raise JulesApiError("unsupported_source")
                elif field == "activities" and not re.fullmatch(
                    re.escape(path.removesuffix("/activities")) + r"/activities/[A-Za-z0-9_-]+", name
                ):
                    raise JulesApiError("invalid_activity_identity")
                if name in rows and rows[name] != row:
                    raise JulesApiError("catalog_changed_during_pagination")
                rows[name] = row
            token = result.get("nextPageToken", "")
            if not isinstance(token, str) or len(token) > 8192:
                raise JulesApiError("invalid_page_token")
            if not token:
                return Catalog(tuple(rows.values()), page, datetime.now(timezone.utc).isoformat())
            if token in seen_tokens:
                raise JulesApiError("repeated_page_token")
            seen_tokens.add(token)
        raise JulesApiError("pagination_limit_exceeded")

    def sources(self) -> Catalog:
        return self._list("sources", "sources")

    def sessions(self) -> Catalog:
        return self._list("sessions", "sessions")

    def activities(self, name: str) -> Catalog:
        return self._list(session_name(name) + "/activities", "activities")

    def session(self, name: str) -> dict:
        expected = session_name(name)
        row = self._request("GET", expected)
        if session_identity(row) != expected:
            raise JulesApiError("wrong_session_returned")
        return row

    def create(
        self,
        *,
        source: str,
        branch: str,
        prompt: str,
        title: str,
        auto_create_pr: bool = False,
        timeout: float | None = None,
    ) -> dict:
        if not isinstance(source, str) or not _SOURCE.fullmatch(source):
            raise JulesApiError("invalid_source")
        if not isinstance(branch, str) or not branch or len(branch) > 1024 or any(ord(c) < 32 for c in branch):
            raise JulesApiError("invalid_branch")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 262144:
            raise JulesApiError("invalid_prompt")
        if not isinstance(title, str) or not title.strip() or len(title) > 256:
            raise JulesApiError("invalid_title")
        payload = {
            "prompt": prompt,
            "title": title,
            "requirePlanApproval": False,
            "sourceContext": {"source": source, "githubRepoContext": {"startingBranch": branch}},
        }
        if auto_create_pr:
            payload["automationMode"] = "AUTO_CREATE_PR"
        row = self._request("POST", "sessions", payload, timeout=timeout)
        try:
            session_identity(row)
            if row.get("sourceContext", {}).get("source", source) != source:
                raise JulesApiError("wrong_source_returned")
        except (JulesApiError, AttributeError, TypeError):
            raise JulesMutationUnknown("create_acceptance_unconfirmed") from None
        return row

    def approve_plan(self, name: str) -> dict:
        return self._request("POST", session_name(name) + ":approvePlan", {})

    def send_message(self, name: str, prompt: str) -> dict:
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode("utf-8")) > 262144:
            raise JulesApiError("invalid_prompt")
        return self._request("POST", session_name(name) + ":sendMessage", {"prompt": prompt})

    def completed_patch(self, name: str, *, source: str, exact_base: str) -> str:
        session = self.session(name)
        context = session.get("sourceContext")
        if session.get("state") != "COMPLETED" or not isinstance(context, dict) or context.get("source") != source:
            raise JulesApiError("result_not_completed_for_source")
        finals = []
        for activity in self.activities(name).items:
            if "sessionCompleted" not in activity:
                continue
            artifacts = activity.get("artifacts", [])
            if not isinstance(artifacts, list):
                raise JulesApiError("invalid_result_artifacts")
            for artifact in artifacts:
                change = artifact.get("changeSet", {}) if isinstance(artifact, dict) else {}
                if not isinstance(change, dict):
                    raise JulesApiError("invalid_result_artifacts")
                git_patch = change.get("gitPatch", {})
                if not isinstance(git_patch, dict):
                    raise JulesApiError("invalid_result_artifacts")
                if change.get("source") != source or git_patch.get("baseCommitId") != exact_base:
                    continue
                value = git_patch.get("unidiffPatch")
                if value:
                    if not isinstance(value, str) or len(value.encode("utf-8")) > self.max_bytes:
                        raise JulesApiError("invalid_result_patch")
                    finals.append((timestamp(activity.get("createTime")), value))
        if not finals:
            raise JulesApiError("no_completed_patch_for_exact_source_base")
        finals.sort(key=lambda item: item[0])
        if len({value for stamp, value in finals if stamp == finals[-1][0]}) != 1:
            raise JulesApiError("ambiguous_completed_patch")
        return finals[-1][1]

    def find_attempt(self, *, marker: str, source: str) -> dict | None:
        matches = [
            row
            for row in self.sessions().items
            if str(row.get("prompt", "")).splitlines()[:1] == [marker]
            and isinstance(row.get("sourceContext"), dict)
            and row["sourceContext"].get("source") == source
        ]
        if len(matches) > 1:
            raise JulesMutationUnknown("duplicate_provider_attempts")
        return matches[0] if matches else None


def observe(catalog: Catalog, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not catalog.pagination_complete:
        raise JulesApiError("incomplete_observation")
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(hours=24)
    counts: dict[str, int] = {}
    launches = 0
    nonterminal = 0
    for row in catalog.items:
        session_identity(row)
        created = timestamp(row.get("createTime"))
        if created > now:
            raise JulesApiError("future_provider_timestamp")
        state = row.get("state", "STATE_UNSPECIFIED")
        if not isinstance(state, str) or state not in STATES:
            raise JulesApiError("unknown_provider_state")
        counts[state] = counts.get(state, 0) + 1
        nonterminal += state not in TERMINAL
        # Include the exact boundary conservatively (RFC3339 supports nanoseconds).
        launches += cutoff <= created <= now
    return {
        "schema_version": "limen.jules_api_observation.v1",
        "status": "observed",
        "observed_at": now.isoformat(),
        "window_start": cutoff.isoformat(),
        "pagination_complete": True,
        "pages": catalog.pages,
        "sessions_observed": len(catalog.items),
        "observed_rolling_starts": launches,
        "nonterminal_sessions": nonterminal,
        "states": counts,
        "vendor_quota_remaining": None,
        "history_is_billing_ledger": False,
        "provider_completed_is_merged": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read Jules API evidence; this command never dispatches or merges.")
    parser.add_argument("command", choices=["observe"])
    parser.parse_args()
    try:
        client = JulesApiClient.from_env()
        sources = client.sources()
        result = observe(client.sessions())
        result["sources_observed"] = len(sources.items)
    except JulesApiError as exc:
        print(
            json.dumps(
                {
                    "schema_version": "limen.jules_api_observation.v1",
                    "status": "unavailable",
                    "error_code": exc.code,
                    "http_status": exc.status,
                    "observed_rolling_starts": None,
                    "nonterminal_sessions": None,
                    "vendor_quota_remaining": None,
                }
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
