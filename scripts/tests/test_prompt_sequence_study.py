"""Regression checks for prompt preservation and source-bound cache verification."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "prompt_sequence_study", Path(__file__).resolve().parents[1] / "prompt-sequence-study.py"
)
STUDY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STUDY)


def user(uid, text):
    return {"type": "user", "uuid": uid, "message": {"content": text}}


def assistant(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


class PromptSequenceStudyTests(unittest.TestCase):
    def test_quoted_markup_keeps_surrounding_request(self):
        text = "Review this example: <command-name>/ship</command-name> do not execute it."
        self.assertEqual(STUDY.normalized(text), text)

    def test_native_wrapper_normalizes_with_arguments(self):
        text = "<command-message>verify</command-message>\n<command-name>/verify</command-name>\n<command-args>closure</command-args>"
        self.assertEqual(STUDY.normalized(text), "/verify closure")

    def extract(self, records):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "session.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            return STUDY.extract(path, root, time.monotonic() + 5)

    def test_echo_pairs_once_and_later_invocation_survives(self):
        result = self.extract(
            [
                user("opener", "initial"),
                user("typed", "/compact"),
                user("echo", "<command-name>/compact</command-name>"),
                assistant("First command finished."),
                user("later", "<command-name>/compact</command-name>"),
            ]
        )
        self.assertEqual([p["uuid"] for p in result["prompts"]], ["opener", "typed", "later"])
        self.assertEqual(len(result["prompts"][1]["echo_records"]), 1)

    def test_response_separates_independent_invocations(self):
        result = self.extract(
            [
                user("opener", "initial"),
                user("typed", "/verify"),
                assistant("First verification finished."),
                user("later", "<command-name>/verify</command-name>"),
            ]
        )
        self.assertEqual(len(result["prompts"]), 3)

    def test_repeated_wrapper_invocations_are_not_echoes(self):
        result = self.extract(
            [
                user("opener", "initial"),
                user("first", "<command-name>/verify</command-name>"),
                user("second", "<command-name>/verify</command-name>"),
            ]
        )
        self.assertEqual(len(result["prompts"]), 3)

    def test_prefix_capture_does_not_include_later_append(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "session.jsonl"
            first = json.dumps(user("first", "initial")) + "\n"
            path.write_text(first + json.dumps(user("later", "new turn")) + "\n")
            result = STUDY.extract(path, root, time.monotonic() + 5, byte_limit=len(first.encode()))
            self.assertEqual([p["uuid"] for p in result["prompts"]], ["first"])

    def cache_fixture(self, root):
        source = root / "sources"
        source.mkdir()
        path = source / "session.jsonl"
        path.write_text(json.dumps(user("first", "initial")) + "\n")
        sessions = [STUDY.extract(path, source, time.monotonic() + 5)]
        data = {"sessions": sessions, "summary": STUDY.summarize(sessions), "focus": []}
        output = root / "cache"
        output.mkdir()
        self.write_cache(output, data)
        return source, output, data

    def write_cache(self, output, data):
        (output / "sequences.json").write_text(json.dumps(data))
        (output / "coverage.json").write_text(json.dumps(STUDY.coverage_for(data)))
        STUDY.render(data, output)

    def test_check_replays_prefix_after_source_append(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output, _data = self.cache_fixture(Path(directory))
            with (source / "session.jsonl").open("a") as stream:
                stream.write(json.dumps(user("later", "new turn")) + "\n")
            self.assertEqual(STUDY.check_cache(output, source)["retained_prompts"], 1)

    def test_check_rejects_internally_consistent_prompt_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output, data = self.cache_fixture(Path(directory))
            data["sessions"][0]["prompts"][0]["text"] = "changed request"
            self.write_cache(output, data)
            with self.assertRaisesRegex(ValueError, "Source replay differs"):
                STUDY.check_cache(output, source)

    def test_check_rejects_html_prompt_omission(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output, _data = self.cache_fixture(Path(directory))
            page = output / "index.html"
            page.write_text(page.read_text().replace('"text": "initial"', '"text": ""'))
            with self.assertRaisesRegex(ValueError, "HTML data differs"):
                STUDY.check_cache(output, source)

    def test_check_rejects_coverage_count_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output, data = self.cache_fixture(Path(directory))
            coverage = STUDY.coverage_for(data)
            coverage["summary"]["retained_prompts"] = 123
            (output / "coverage.json").write_text(json.dumps(coverage))
            with self.assertRaisesRegex(ValueError, "Coverage differs"):
                STUDY.check_cache(output, source)

    def test_check_rejects_source_content_change(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output, _data = self.cache_fixture(Path(directory))
            path = source / "session.jsonl"
            path.write_text(path.read_text().replace("initial", "altered"))
            with self.assertRaisesRegex(ValueError, "Source replay differs"):
                STUDY.check_cache(output, source)

    def test_tool_only_response_separates_invocations(self):
        result = self.extract(
            [
                user("opener", "initial"),
                user("typed", "/verify"),
                {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read"}]}},
                user("later", "<command-name>/verify</command-name>"),
            ]
        )
        self.assertEqual(len(result["prompts"]), 3)

    def test_missing_and_empty_roots_fail_without_creating_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source in (root / "missing", root):
                output = root / "output"
                run = subprocess.run(
                    [sys.executable, str(SPEC.origin), "--source-root", str(source), "--output", str(output)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(run.returncode, 0)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
