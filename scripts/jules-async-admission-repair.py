#!/usr/bin/env python3
"""One-shot branch repair for PR #2687; deletes itself after verified application."""

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement target, found {count}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "cli/src/limen/fanout_executor.py",
    '''            if node.get("execution_admission"):\n                if not getattr(adapter, "enforces_deadline", False):\n                    raise FanoutExecutionError(f"{adapter.name}: provider hard-deadline enforcement unavailable")\n                packet = {**packet, "deadline": node["execution_admission"]["attempt_deadline"]}\n                if datetime.fromisoformat(packet["deadline"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):\n                    raise FanoutExecutionError("execution attempt deadline exhausted before provider launch")\n''',
    '''            if node.get("execution_admission"):\n                admission_deadline = str(node["execution_admission"]["attempt_deadline"])\n                if datetime.fromisoformat(admission_deadline.replace("Z", "+00:00")) <= datetime.now(timezone.utc):\n                    raise FanoutExecutionError("execution attempt deadline exhausted before provider launch")\n                if getattr(adapter, "enforces_deadline", False):\n                    packet = {**packet, "deadline": admission_deadline}\n                elif getattr(adapter, "fenced_async_submission", False):\n                    # Async providers may outlive Limen's execution lease. Admission therefore\n                    # bounds the create call, while the exact provider identity remains owned\n                    # and late output requires a separately admitted recovery/integration pass.\n                    packet = {**packet, "submission_deadline": admission_deadline}\n                else:\n                    raise FanoutExecutionError(f"{adapter.name}: provider hard-deadline enforcement unavailable")\n''',
)
replace_once(
    "cli/src/limen/fanout_executor.py",
    '''        deadline = datetime.fromisoformat(str(packet["deadline"]).replace("Z", "+00:00"))\n''',
    '''        deadline_values = [datetime.fromisoformat(str(packet["deadline"]).replace("Z", "+00:00"))]\n        execution_admission = node.get("execution_admission")\n        if isinstance(execution_admission, dict) and execution_admission.get("attempt_deadline"):\n            deadline_values.append(\n                datetime.fromisoformat(str(execution_admission["attempt_deadline"]).replace("Z", "+00:00"))\n            )\n        deadline = min(deadline_values)\n''',
)
replace_once(
    "cli/src/limen/fanout_executor.py",
    '''            else "campaign deadline reached without an exact provider receipt"\n''',
    '''            else "execution boundary reached; provider identity retained for separately admitted recovery"\n''',
)

replace_once(
    "cli/src/limen/jules_api.py",
    '''    def create(self, *, source: str, branch: str, prompt: str, title: str, auto_create_pr: bool = False) -> dict:\n''',
    '''    def create(\n        self,\n        *,\n        source: str,\n        branch: str,\n        prompt: str,\n        title: str,\n        auto_create_pr: bool = False,\n        timeout: float | None = None,\n    ) -> dict:\n''',
)
replace_once(
    "cli/src/limen/jules_api.py",
    '''        row = self._request("POST", "sessions", payload)\n''',
    '''        row = self._request("POST", "sessions", payload, timeout=timeout)\n''',
)

replace_once(
    "cli/src/limen/jules_api_adapter.py",
    '''from pathlib import Path\nfrom typing import Any\n''',
    '''from datetime import datetime, timezone\nfrom pathlib import Path\nfrom typing import Any\n''',
)
replace_once(
    "cli/src/limen/jules_api_adapter.py",
    '''    enforces_deadline = False\n''',
    '''    enforces_deadline = False\n    # The REST API is asynchronous and has no documented remote cancellation.\n    # Limen may bound only submission, persist the accepted session identity, and\n    # fence late integration behind a separately admitted recovery pass.\n    fenced_async_submission = True\n''',
)
replace_once(
    "cli/src/limen/jules_api_adapter.py",
    '''        try:\n            observed = observe(self.client.sessions())\n            # These are conservative observed guards, NOT a vendor balance.\n''',
    '''        try:\n            submission_deadline = packet.get("submission_deadline")\n            parsed_deadline = None\n            if submission_deadline is not None:\n                try:\n                    parsed_deadline = datetime.fromisoformat(str(submission_deadline).replace("Z", "+00:00"))\n                except ValueError:\n                    raise FanoutExecutionError("invalid Jules submission deadline") from None\n                if parsed_deadline <= datetime.now(timezone.utc):\n                    raise FanoutExecutionError("Jules submission deadline exhausted before account observation")\n            observed = observe(self.client.sessions())\n            # These are conservative observed guards, NOT a vendor balance.\n''',
)
replace_once(
    "cli/src/limen/jules_api_adapter.py",
    '''            prompt = _provider_prompt(packet, attempt_id)\n            row = self.client.create(\n                source=source, branch=branch, prompt=prompt, title=f"[limen-fanout:{attempt_id}]", auto_create_pr=False\n            )\n''',
    '''            prompt = _provider_prompt(packet, attempt_id)\n            create_timeout = None\n            if parsed_deadline is not None:\n                remaining = (parsed_deadline - datetime.now(timezone.utc)).total_seconds()\n                if remaining <= 0:\n                    raise FanoutExecutionError("Jules submission deadline exhausted before create")\n                create_timeout = min(float(self.client.timeout), remaining)\n            row = self.client.create(\n                source=source,\n                branch=branch,\n                prompt=prompt,\n                title=f"[limen-fanout:{attempt_id}]",\n                auto_create_pr=False,\n                timeout=create_timeout,\n            )\n''',
)

replace_once(
    "cli/tests/test_jules_api_adapter.py",
    '''from datetime import datetime, timezone\n''',
    '''from datetime import datetime, timedelta, timezone\n''',
)
replace_once(
    "cli/tests/test_jules_api_adapter.py",
    '''    value.create.return_value = {\n''',
    '''    value.timeout = 15.0\n    value.create.return_value = {\n''',
)
replace_once(
    "cli/tests/test_jules_api_adapter.py",
    '''    def test_no_fictional_hard_deadline(self):\n        self.assertIs(JulesApiExecutionAdapter.enforces_deadline, False)\n''',
    '''    def test_no_fictional_hard_deadline(self):\n        self.assertIs(JulesApiExecutionAdapter.enforces_deadline, False)\n        self.assertIs(JulesApiExecutionAdapter.fenced_async_submission, True)\n''',
)
replace_once(
    "cli/tests/test_jules_api_adapter.py",
    '''    def test_changed_source_head_stops_before_create(self):\n''',
    '''    def test_submission_deadline_bounds_create_without_claiming_remote_cancellation(self):\n        remote = client()\n        value = packet()\n        value["submission_deadline"] = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()\n        adapter = JulesApiExecutionAdapter(remote)\n        with (\n            patch("limen.jules_api_adapter._default_branch", return_value="main"),\n            patch("limen.jules_api_adapter.remote_branch_head", return_value=HEAD),\n        ):\n            adapter.launch(value, "attempt-abc-1")\n        timeout = remote.create.call_args.kwargs["timeout"]\n        self.assertGreater(timeout, 0)\n        self.assertLessEqual(timeout, remote.timeout)\n\n    def test_expired_submission_deadline_stops_before_provider_reads(self):\n        remote = client()\n        value = packet()\n        value["submission_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()\n        with self.assertRaises(FanoutExecutionError):\n            JulesApiExecutionAdapter(remote).launch(value, "attempt-abc-1")\n        remote.sessions.assert_not_called()\n        remote.create.assert_not_called()\n\n    def test_changed_source_head_stops_before_create(self):\n''',
)
replace_once(
    "cli/tests/test_fanout.py",
    '''def test_worker_restart_without_original_deadline_cannot_get_fresh_allowance(tmp_path, monkeypatch):\n''',
    '''def test_admitted_outcome_allows_explicit_fenced_async_submission(\n    tmp_path, monkeypatch, approved_execution_policy\n):\n    approved_execution_policy("campaign/v1")\n    payload = manifest_payload()\n    payload["leaves"][0]["retry"]["max_attempts"] = 1\n    manifest = FanoutManifestV1.model_validate(payload)\n    keeper = LocalConductClient(tmp_path / "fenced-async.sqlite")\n    adapter = FakeExecutionAdapter()\n    adapter.enforces_deadline = False\n    adapter.fenced_async_submission = True\n    monkeypatch.setattr("limen.fanout_executor.remote_default_head", lambda repo: BASE)\n    started = start_manifest(manifest, client=keeper, allow_development_keeper=True, execution_adapters=(adapter,))\n    assert len(adapter.launches) == 1\n    graph = keeper.graph(started["root_run_id"])\n    leaf = next(node for node in graph["nodes"] if node["packet"]["work_id"] == "leaf-a")\n    assert leaf["attempts"][-1]["status"] == "submitted"\n    assert leaf["attempts"][-1]["provider_run_id"] == "provider-run-1"\n\n\ndef test_worker_restart_without_original_deadline_cannot_get_fresh_allowance(tmp_path, monkeypatch):\n''',
)
