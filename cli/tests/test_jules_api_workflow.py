"""Provider credentials are confined to an exact accepted default-branch checkout."""

import json
import unittest
from pathlib import Path

import yaml


class JulesWorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[2] / ".github/workflows/jules-api-contract.yml"
        cls.workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)

    def test_no_privileged_pr_trigger(self):
        events = self.workflow["on"]
        self.assertNotIn("pull_request_target", events)
        self.assertNotIn("workflow_run", events)
        self.assertEqual(events["push"]["branches"], ["main"])
        self.assertIn("workflow_dispatch", events)
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})

    def test_provider_readback_requires_default_branch_and_non_pr_event(self):
        job = self.workflow["jobs"]["account-readback"]
        self.assertEqual(
            job["if"],
            "(github.event_name == 'push' || github.event_name == 'workflow_dispatch') "
            "&& github.ref == format('refs/heads/{0}', github.event.repository.default_branch)",
        )
        self.assertEqual(job["needs"], "contract")
        checkout = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["ref"], "${{ github.sha }}")
        self.assertEqual(checkout["with"]["persist-credentials"], "false")

    def test_secret_is_only_supplied_to_the_observer_step(self):
        expression = "${{ secrets.JULES_API_KEY }}"
        self.assertEqual(json.dumps(self.workflow).count(expression), 1)
        job = self.workflow["jobs"]["account-readback"]
        steps = [step for step in job["steps"] if expression in json.dumps(step)]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["env"]["JULES_API_KEY"], expression)
        self.assertEqual(
            steps[0]["run"], "timeout 1320s python -m limen.jules_api observe > jules-api-observation.json"
        )
        self.assertEqual(job["timeout-minutes"], "24")
        for name, other in self.workflow["jobs"].items():
            if name != "account-readback":
                if name == "witness-contract":
                    # The private, immutable source checkout needs the existing
                    # source-read credential, never provider credentials.
                    checkout = other["steps"][0]
                    self.assertEqual(checkout["uses"], "actions/checkout@v4")
                    self.assertEqual(checkout["with"]["repository"], "4444J99/ops-witness")
                    self.assertEqual(checkout["with"]["ref"], "75af87fe7e47d76d005f985c19d5c20be09e6266")
                    self.assertEqual(checkout["with"]["persist-credentials"], "false")
                    expression = "${{ secrets.OPS_SOURCE_GITHUB_TOKEN }}"
                    self.assertEqual(checkout["with"]["token"], expression)
                    self.assertEqual(json.dumps(other).count(expression), 1)
                    self.assertNotIn("secrets.", json.dumps(other).replace(expression, ""))
                else:
                    self.assertNotIn("secrets.", json.dumps(other))

    def test_readback_errors_are_not_converted_to_success(self):
        job = self.workflow["jobs"]["account-readback"]
        self.assertNotIn("continue-on-error", job)
        for step in job["steps"]:
            self.assertNotIn("continue-on-error", step)
            self.assertNotIn("|| true", step.get("run", ""))
        upload = next(step for step in job["steps"] if step.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["with"]["path"], "jules-api-observation.json")

    def test_diagnostics_target_current_candidate_without_secrets(self):
        diagnostic = self.workflow["jobs"]["cli-first-failure"]
        rows = diagnostic["strategy"]["matrix"]["include"]
        candidate = next(row for row in rows if row["source"] == "api-head")
        self.assertEqual(candidate["ref"], "${{ github.event.pull_request.head.sha || github.sha }}")
        self.assertNotIn("secrets.", json.dumps(diagnostic))


if __name__ == "__main__":
    unittest.main()
