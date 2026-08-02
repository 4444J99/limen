#!/usr/bin/env python3
"""Portable regression tests for Danse's delivery-trunk interfaces."""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DELIVER = load("danse_deliver_test", ROOT / "apps/danse/render/deliver.py")
SCORE = load("danse_score_test", ROOT / "apps/danse/sound/score.py")
CHECK = load("danse_submission_check_test", ROOT / "apps/danse/submission/check.py")
BROWSER = load("danse_browser_test", ROOT / "apps/danse/render/browser.py")
SPAN = {
    "t0": 0.0,
    "t1": 312.54,
    "duration": 312.54,
    "seed": 0xAF6B7BE5,
    "river_seed": 20170620,
    "passage": 0,
    "capture": "passage",
}


class DeliveryContractTest(unittest.TestCase):
    def test_span_queries_are_metadata_only(self) -> None:
        payload = {
            **SPAN,
            "seed": 20170620,
            "passage": 0,
            "passageSeed": SPAN["seed"],
            "origin": "IMG_1594",
        }
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
        with mock.patch.object(DELIVER, "sh", return_value=completed) as run:
            span = DELIVER.query_capture_span("passage", start=120.0)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--rate") + 1], "0")
        self.assertEqual(span["origin"], "IMG_1594")

    def test_score_forwards_absolute_start_to_control(self) -> None:
        payload = {"capture": "passage", "t0": 120.0, "t1": 432.54, "duration": 312.54}
        completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(payload), stderr="")
        with mock.patch.object(SCORE.subprocess, "run", return_value=completed) as run:
            self.assertEqual(SCORE.control_track("passage", 123, 30, 120.0), payload)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--from") + 1], "120.0")
        self.assertEqual(command[command.index("--seed") + 1], "123")

    def test_capture_roots_do_not_mix_start_offsets(self) -> None:
        root = Path("/render")
        first = DELIVER.capture_root(root, SPAN, 0.0)
        later = DELIVER.capture_root(root, {**SPAN, "seed": 7}, 120.25)
        self.assertNotEqual(first, later)
        self.assertEqual(first.parent, root)
        self.assertEqual(later.parent, root)

    def test_only_text_never_invokes_picture_or_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "render"
            argv = ["deliver.py", "--only", "text", "--out", str(out)]
            forbidden = mock.Mock(side_effect=AssertionError("render dependency invoked"))
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(DELIVER, "query_capture_span", return_value=SPAN),
                mock.patch.object(DELIVER, "passage_picture", forbidden),
                mock.patch.object(DELIVER, "passage_sound", forbidden),
                mock.patch.object(DELIVER, "probe", return_value=None),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(DELIVER.main(), 0)
            self.assertFalse(forbidden.called)
            self.assertTrue((out / "package/text/synopsis_short.txt").is_file())
            attest = yaml.safe_load((out / "package/attest.yaml").read_text())
            self.assertTrue(attest)
            self.assertTrue(all(value is None for value in attest.values()))

    def test_only_origin_copies_source_bytes_under_stills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "IMG_1594.JPG"
            source.write_bytes(b"camera-original")
            out = root / "render"
            argv = ["deliver.py", "--only", "origin", "--out", str(out)]
            forbidden = mock.Mock(side_effect=AssertionError("render dependency invoked"))
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(DELIVER, "ORIGIN", source),
                mock.patch.object(DELIVER, "query_capture_span", return_value=SPAN),
                mock.patch.object(DELIVER, "passage_picture", forbidden),
                mock.patch.object(DELIVER, "passage_sound", forbidden),
                mock.patch.object(DELIVER, "probe", return_value=None),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(DELIVER.main(), 0)
            copied = out / "package/stills/origin-2017.jpg"
            self.assertEqual(copied.read_bytes(), source.read_bytes())
            self.assertFalse(forbidden.called)
            register = yaml.safe_load((ROOT / "apps/danse/submission/screendance-2027.yaml").read_text())
            report = CHECK.Report()
            CHECK.check_origin_still(register["package"]["origin_still"], out / "package", report)
            self.assertEqual(report.failures, 0)

    def test_text_preflight_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "absent"
            argv = ["deliver.py", "--preflight", "--only", "text", "--out", str(out)]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(DELIVER, "query_capture_span", return_value=SPAN),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(DELIVER.main(), 0)
            self.assertFalse(out.exists())

    def test_attestations_are_cumulative_by_owned_phase(self) -> None:
        reg = yaml.safe_load((ROOT / "apps/danse/submission/screendance-2027.yaml").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "attest.yaml").write_text("final-cut-only: true\n")
            expected = {"package": 3, "uploaded": 5, "submitted": 6}
            for phase, count in expected.items():
                report = CHECK.Report()
                CHECK.check_attestations(reg, root, phase, report)
                self.assertEqual(len(report.rows), count)
                self.assertEqual(report.failures, count - 1)

    def test_projection_probe_returns_page_self_test_status(self) -> None:
        class Locator:
            def inner_text(self) -> str:
                return "SELF-TEST PASS\nmax Δ 0/255"

        page = mock.Mock()
        page.gl_renderer = "ANGLE Metal Renderer"
        page.evaluate.return_value = True
        page.locator.return_value = Locator()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(BROWSER.run_probe(page, "http://example.test"), 0)
        page.goto.assert_called_once_with("http://example.test/probe.html", wait_until="load")


if __name__ == "__main__":
    unittest.main()
