"""Opt-in REST adapter for the EXISTING conduct/fanout lifecycle.

The broker still records/claims the attempt before launch. This module neither
creates a second queue nor declares a provider hard deadline it cannot enforce.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from limen.fanout_executor import (
    AmbiguousProviderLaunchError,
    CODE_RECEIPT_CAPABILITIES,
    FanoutExecutionError,
    PatchLandingMixin,
    ProviderLaunch,
    ProviderState,
    _checked,
    _default_branch,
    _provider_prompt,
    remote_branch_head,
)
from limen.jules_api import JulesApiClient, JulesApiError, JulesMutationUnknown, observe, session_identity, STATES


class JulesApiExecutionAdapter(PatchLandingMixin):
    name = "jules-api"
    transport = "jules-rest-v1alpha"
    local_heavy = False
    receipt_quality = 0.95
    cost_per_run = 0.0
    quota_remaining = None
    capabilities = CODE_RECEIPT_CAPABILITIES | frozenset({"jules-api"})
    conduct_token_env = "LIMEN_CONDUCT_TOKEN_JULES"
    worker_env_allowlist = frozenset({"JULES_API_KEY", "LIMEN_ENABLE_JULES_API", "LIMEN_JULES_API_CONCURRENCY"})
    # The public API has no documented remote cancellation/deadline operation.
    # launch_ready_nodes MUST retain its hard-deadline admission rejection.
    enforces_deadline = False
    # The REST API is asynchronous and has no documented remote cancellation.
    # Limen may bound only submission, persist the accepted session identity, and
    # fence late integration behind a separately admitted recovery pass.
    fenced_async_submission = True

    def __init__(self, client: JulesApiClient | None, *, concurrency: int = 1):
        if type(concurrency) is not int or not 1 <= concurrency <= 15:
            raise FanoutExecutionError("Jules API concurrency must be between 1 and 15")
        self.client = client
        self.concurrency = concurrency
        self.sources: dict[str, str] = {}
        if client is not None:
            for row in client.sources().items:
                repo = row.get("githubRepo", {})
                if not isinstance(repo, dict):
                    raise JulesApiError("invalid_github_source")
                owner, name = repo.get("owner"), repo.get("repo")
                if not isinstance(owner, str) or not isinstance(name, str):
                    raise JulesApiError("invalid_github_source")
                slug = owner + "/" + name
                if row["name"] != "sources/github/" + slug:
                    raise JulesApiError("inconsistent_github_source")
                if slug in self.sources and self.sources[slug] != row["name"]:
                    raise JulesApiError("duplicate_github_source")
                self.sources[slug] = row["name"]

    def eligible(self, packet: dict[str, Any]) -> bool:
        # The entry-point discovery probe does not carry effect/capabilities.
        return (
            self.client is not None
            and packet.get("effect", "write") == "write"
            and packet.get("execution", {}).get("owner_repository") in self.sources
        )

    @staticmethod
    def _launch_record(row: dict) -> ProviderLaunch:
        name = session_identity(row)
        url = row.get("url", "")
        if not isinstance(url, str) or not re.fullmatch(
            r"https://jules\.google\.com/(?:session|task)/[A-Za-z0-9_-]+", url
        ):
            url = "https://jules.googleapis.com/v1alpha/" + name
        return ProviderLaunch(name.split("/")[1], url)

    def launch(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch:
        if not self.eligible(packet) or self.client is None:
            raise FanoutExecutionError("Jules API source is unavailable")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", attempt_id):
            raise FanoutExecutionError("invalid Jules attempt identity")
        repository = packet["execution"]["owner_repository"]
        expected = packet["execution"]["exact_base"]
        if not re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", expected):
            raise FanoutExecutionError("Jules API requires an exact base")
        try:
            submission_deadline = packet.get("submission_deadline")
            parsed_deadline = None
            if submission_deadline is not None:
                try:
                    parsed_deadline = datetime.fromisoformat(str(submission_deadline).replace("Z", "+00:00"))
                except ValueError:
                    raise FanoutExecutionError("invalid Jules submission deadline") from None
                if parsed_deadline <= datetime.now(timezone.utc):
                    raise FanoutExecutionError("Jules submission deadline exhausted before account observation")
            observed = observe(self.client.sessions())
            # These are conservative observed guards, NOT a vendor balance.
            # Shared reservations and all other callers remain broker-owned.
            if observed["observed_rolling_starts"] >= 100 or observed["nonterminal_sessions"] >= 15:
                raise FanoutExecutionError("Jules account observation has no safe launch headroom")
            branch = _default_branch(repository)
            if remote_branch_head(repository, branch) != expected:
                raise FanoutExecutionError("Jules source branch moved from the admitted exact base")
            source = self.sources[repository]
            prompt = _provider_prompt(packet, attempt_id)
            create_timeout = None
            if parsed_deadline is not None:
                remaining = (parsed_deadline - datetime.now(timezone.utc)).total_seconds()
                if remaining <= 0:
                    raise FanoutExecutionError("Jules submission deadline exhausted before create")
                create_timeout = min(float(self.client.timeout), remaining)
            row = self.client.create(
                source=source,
                branch=branch,
                prompt=prompt,
                title=f"[limen-fanout:{attempt_id}]",
                auto_create_pr=False,
                timeout=create_timeout,
            )
            # PatchLandingMixin, not Jules, owns exact-head PR creation here.
            return self._launch_record(row)
        except JulesMutationUnknown as exc:
            raise AmbiguousProviderLaunchError(exc.code) from None
        except JulesApiError as exc:
            raise FanoutExecutionError(exc.code) from None

    def recover(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch | None:
        if self.client is None:
            return None
        source = self.sources.get(packet.get("execution", {}).get("owner_repository"))
        if source is None:
            return None
        try:
            row = self.client.find_attempt(marker=f"[limen-fanout:{attempt_id}]", source=source)
            return self._launch_record(row) if row is not None else None
        except JulesApiError:
            # The existing broker leaves a launching attempt pending on None;
            # it does NOT create another session. Unknown never becomes absent.
            return None

    def probe(self, provider_run_id: str) -> ProviderState:
        if self.client is None:
            return ProviderState("submitted", "Jules observation unavailable; last ownership retained")
        try:
            row = self.client.session(provider_run_id)
        except JulesApiError as exc:
            return ProviderState("submitted", "Jules observation unavailable: " + exc.code)
        state = row.get("state", "STATE_UNSPECIFIED")
        if state == "COMPLETED":
            return ProviderState("succeeded", "Provider completed; exact-head landing still required")
        if state == "FAILED":
            return ProviderState("failed", "Jules FAILED; preserve evidence and owned work", "permanent")
        # Waiting/paused is not a terminal failure: preserve the same session so
        # bounded sendMessage/approvePlan can resume it instead of duplicating it.
        if not isinstance(state, str) or state not in STATES:
            return ProviderState("submitted", "Jules state unrecognized; ownership retained")
        status = "running" if state in {"IN_PROGRESS", "PLANNING"} else "submitted"
        return ProviderState(status, "Jules state: " + state)

    def apply_result(self, provider_run_id: str, worktree: Path) -> None:
        if self.client is None:
            raise FanoutExecutionError("Jules API unavailable for landing")
        try:
            remote = _checked(["git", "remote", "get-url", "origin"], cwd=worktree).strip()
            match = re.fullmatch(
                r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", remote
            )
            source = self.sources.get(match.group(1)) if match else None
            if source is None:
                raise FanoutExecutionError("Jules result repository is not an authorized source")
            head = _checked(["git", "rev-parse", "HEAD"], cwd=worktree).strip()
            patch = self.client.completed_patch(provider_run_id, source=source, exact_base=head)
            _checked(["git", "apply", "--index", "--whitespace=error-all", "-"], cwd=worktree, input_text=patch)
            # The existing landing implementation now checks allowed paths,
            # runs the exact-head predicate, creates the PR and records custody.
        except JulesApiError as exc:
            raise FanoutExecutionError(exc.code) from None


def create_adapter() -> JulesApiExecutionAdapter:
    """No network request or alternative provider when the REST lane is unarmed."""
    if os.environ.get("LIMEN_ENABLE_JULES_API") != "1":
        return JulesApiExecutionAdapter(None)
    try:
        concurrency = int(os.environ.get("LIMEN_JULES_API_CONCURRENCY", "1"))
        return JulesApiExecutionAdapter(JulesApiClient.from_env(), concurrency=concurrency)
    except (ValueError, JulesApiError, FanoutExecutionError):
        # Read-only `limen-jules-api observe` reports the actual error separately.
        return JulesApiExecutionAdapter(None)
