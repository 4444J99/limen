#!/usr/bin/env python3
"""Adversarial audit responses and independent CI ownership."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("npm_audit_gate", ROOT / "scripts/npm-audit-gate.py")
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def report(severity=None):
    counts = dict.fromkeys(("info", "low", "moderate", "high", "critical", "total"), 0)
    vulnerabilities = {}
    if severity:
        counts[severity] = counts["total"] = 1
        vulnerabilities["example"] = {
            "severity": severity,
            "via": [{"url": "https://github.com/advisories/GHSA-rgj7-g3m4-5g8c"}],
        }
    return {"auditReportVersion": 2, "metadata": {"vulnerabilities": counts}, "vulnerabilities": vulnerabilities}


class AuditResponseTests(unittest.TestCase):
    def test_valid_reports(self):
        for severity in (None, "info", "low", "moderate", "high", "critical"):
            with self.subTest(severity=severity):
                self.assertEqual(m.validate_report(report(severity), 0), report(severity))

    def test_incomplete_error_and_inconsistent_payloads(self):
        examples = [
            {},
            [],
            {"error": {"code": "ENOAUDIT"}},
            report() | {"auditReportVersion": 1},
            report() | {"metadata": {}},
            report() | {"vulnerabilities": []},
        ]
        d = report("high")
        d["metadata"]["vulnerabilities"]["high"] = 0
        examples.append(d)
        d = report()
        d["metadata"]["vulnerabilities"]["total"] = False
        examples.append(d)
        d = report("high")
        d["vulnerabilities"]["example"]["via"] = ["missing"]
        examples.append(d)
        d = report("high")
        d["vulnerabilities"]["example"]["via"] = ["example"]
        examples.append(d)
        d = report("high")
        d["vulnerabilities"]["example"]["via"] = [{"url": "https://attacker.invalid/GHSA-rgj7-g3m4-5g8c"}]
        examples.append(d)
        for payload in examples:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                m.validate_report(payload, 1)
        with self.assertRaises(ValueError):
            m.validate_report(report(), 2)

    def test_transitive_chain(self):
        d = report("high")
        d["vulnerabilities"]["parent"] = {"severity": "high", "via": ["example"]}
        d["metadata"]["vulnerabilities"].update(high=2, total=2)
        self.assertEqual(m.validate_report(d, 1), d)

    def test_main_fails_closed_and_preserves_blocking_result(self):
        for stdout, code, expected in (
            (json.dumps(report()), 0, 0),
            (json.dumps(report()), 1, 1),
            (json.dumps(report("moderate")), 1, 1),
            ("{}", 1, 1),
            ("", 1, 1),
            (json.dumps(report("high")), 1, 1),
        ):
            with (
                self.subTest(stdout=stdout),
                patch.object(sys, "argv", ["audit", "web/worker"]),
                patch.object(m.subprocess, "run", return_value=subprocess.CompletedProcess([], code, stdout, "")),
            ):
                self.assertEqual(m.main(), expected)

    def test_ci_audit_and_compatibility_are_independent(self):
        jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
        self.assertFalse(jobs["npm-audit"]["strategy"]["fail-fast"])
        self.assertEqual(set(jobs["npm-audit"]["strategy"]["matrix"]["package-directory"]), {"web/app", "web/worker"})
        for name in ("web", "worker"):
            self.assertFalse(jobs[name].get("needs"))
            self.assertFalse(any("npm-audit-gate" in step.get("run", "") for step in jobs[name]["steps"]))
        self.assertIn("npm-audit", jobs["verify"]["needs"])


if __name__ == "__main__":
    unittest.main()
