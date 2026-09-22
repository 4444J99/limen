"""Offline REST contract tests. No provider credentials or live sessions are used."""

import io
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest.mock import patch

from limen.jules_api import (
    Catalog,
    JulesApiClient,
    JulesApiError,
    JulesMutationUnknown,
    _NoRedirect,
    _transport,
    main,
    observe,
    session_identity,
    session_name,
    timestamp,
)

NOW = datetime(2026, 9, 21, 20, 0, tzinfo=timezone.utc)
SOURCE = "sources/github/owner/repo"


def session(i="123456789012", state="COMPLETED", created="2026-09-21T17:00:00Z", **extra):
    return {"name": "sessions/" + i, "id": i, "state": state, "createTime": created, **extra}


class Wire:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if not self.responses:
            raise AssertionError("unexpected extra request (possible blind retry)")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class ApiTests(unittest.TestCase):
    def test_requires_key(self):
        for key in ["", "  ", "hello\nworld"]:
            with self.assertRaises(JulesApiError):
                JulesApiClient(key)

    def test_paginated_sessions_include_later_newer_rows(self):
        wire = Wire(
            {"sessions": [session(created="2020-01-01T00:00:00Z")], "nextPageToken": "cursor/with + chars"},
            {"sessions": [session("223456789012")]},
        )
        got = JulesApiClient("synthetic-key", transport=wire).sessions()
        self.assertEqual(len(got.items), 2)
        self.assertEqual(got.pages, 2)
        self.assertIn("cursor%2Fwith+%2B+chars", wire.calls[1][1])
        self.assertEqual(observe(got, NOW)["observed_rolling_starts"], 1)

    def test_empty_page_with_cursor_is_not_end(self):
        wire = Wire({"nextPageToken": "next"}, {"sessions": [session()]})
        self.assertEqual(len(JulesApiClient("key", transport=wire).sessions().items), 1)

    def test_empty_catalog(self):
        self.assertEqual(JulesApiClient("key", transport=Wire({})).sessions().items, ())

    def test_repeated_cursor_is_error(self):
        with self.assertRaisesRegex(JulesApiError, "repeated_page_token"):
            JulesApiClient("key", transport=Wire({"nextPageToken": "x"}, {"nextPageToken": "x"})).sessions()

    def test_page_cap_is_not_success(self):
        with self.assertRaisesRegex(JulesApiError, "pagination_limit"):
            JulesApiClient("key", max_pages=1, transport=Wire({"nextPageToken": "x"})).sessions()

    def test_duplicate_identical_sessions_not_double_counted(self):
        wire = Wire({"sessions": [session()], "nextPageToken": "x"}, {"sessions": [session()]})
        self.assertEqual(len(JulesApiClient("key", transport=wire).sessions().items), 1)

    def test_conflicting_duplicate_is_not_snapshot(self):
        wire = Wire({"sessions": [session()], "nextPageToken": "x"}, {"sessions": [session(state="IN_PROGRESS")]})
        with self.assertRaisesRegex(JulesApiError, "catalog_changed"):
            JulesApiClient("key", transport=wire).sessions()

    def test_malformed_catalog(self):
        for value in [{"sessions": "bad"}, {"sessions": [None]}, {"sessions": [{}]}, {"nextPageToken": 8}]:
            with self.assertRaises(JulesApiError):
                JulesApiClient("key", transport=Wire(value)).sessions()

    def test_sessions_get_checks_requested_identity(self):
        with self.assertRaisesRegex(JulesApiError, "wrong_session_returned"):
            JulesApiClient("key", transport=Wire(session("223456789012"))).session("123456789012")

    def test_opaque_session_resource_validation(self):
        self.assertEqual(session_name("123456789012"), "sessions/123456789012")
        for invalid in ["../../secrets", "https://evil.example/", "1?key=x", ""]:
            with self.assertRaises(JulesApiError):
                session_name(invalid)

    def test_session_id_must_match_name(self):
        with self.assertRaises(JulesApiError):
            session_identity(session(id="different"))

    def test_sources(self):
        row = {"name": SOURCE, "githubRepo": {"owner": "owner", "repo": "repo"}}
        self.assertEqual(JulesApiClient("key", transport=Wire({"sources": [row]})).sources().items, (row,))

    def test_cross_session_activity_refused(self):
        with self.assertRaisesRegex(JulesApiError, "invalid_activity_identity"):
            JulesApiClient("key", transport=Wire({"activities": [{"name": "sessions/wrong/activities/1"}]})).activities(
                "123456789012"
            )

    def test_activities_paginate(self):
        row = {"name": "sessions/123456789012/activities/x"}
        result = JulesApiClient("key", transport=Wire({"nextPageToken": "x"}, {"activities": [row]})).activities(
            "123456789012"
        )
        self.assertEqual(result.pages, 2)

    def test_create_records_real_id_and_no_auto_pr_by_default(self):
        wire = Wire(session())
        result = JulesApiClient("key", transport=wire).create(
            source=SOURCE, branch="main", prompt="Fix verified issue", title="Scoped repair"
        )
        self.assertEqual(result["id"], "123456789012")
        payload = wire.calls[0][3]
        self.assertFalse(payload["requirePlanApproval"])
        self.assertNotIn("automationMode", payload)
        self.assertEqual(payload["sourceContext"]["githubRepoContext"]["startingBranch"], "main")

    def test_auto_pr_is_explicit(self):
        wire = Wire(session())
        JulesApiClient("key", transport=wire).create(
            source=SOURCE, branch="main", prompt="x", title="y", auto_create_pr=True
        )
        self.assertEqual(wire.calls[0][3]["automationMode"], "AUTO_CREATE_PR")

    def test_create_missing_identity_is_indeterminate(self):
        with self.assertRaises(JulesMutationUnknown):
            JulesApiClient("key", transport=Wire({})).create(source=SOURCE, branch="main", prompt="x", title="y")

    def test_create_wrong_source_is_indeterminate(self):
        wire = Wire(session(sourceContext={"source": "sources/github/other/repo"}))
        with self.assertRaises(JulesMutationUnknown):
            JulesApiClient("key", transport=wire).create(source=SOURCE, branch="main", prompt="x", title="y")

    def test_post_never_blindly_retried(self):
        wire = Wire(JulesMutationUnknown("mutation_outcome_unknown"))
        with self.assertRaises(JulesMutationUnknown):
            JulesApiClient("key", transport=wire).create(source=SOURCE, branch="main", prompt="x", title="y")
        self.assertEqual(len(wire.calls), 1)

    def test_find_attempt_uses_source_and_exact_first_line(self):
        rows = [
            session(prompt="prefix [marker]", sourceContext={"source": SOURCE}),
            session("223456789012", prompt="[marker]\nbody", sourceContext={"source": SOURCE}),
            session("323456789012", prompt="[marker]\nbody", sourceContext={"source": "sources/github/other/repo"}),
        ]
        got = JulesApiClient("key", transport=Wire({"sessions": rows})).find_attempt(marker="[marker]", source=SOURCE)
        self.assertEqual(got["id"], "223456789012")

    def test_find_attempt_duplicate_refuses_to_pick_one(self):
        rows = [session(i, prompt="[marker]", sourceContext={"source": SOURCE}) for i in ["1", "2"]]
        with self.assertRaisesRegex(JulesMutationUnknown, "duplicate_provider_attempts"):
            JulesApiClient("key", transport=Wire({"sessions": rows})).find_attempt(marker="[marker]", source=SOURCE)

    def test_send_message_empty_ack_is_not_completion(self):
        wire = Wire({})
        self.assertEqual(JulesApiClient("key", transport=wire).send_message("123456789012", "Fix failing test"), {})
        self.assertTrue(wire.calls[0][1].endswith(":sendMessage"))

    def test_approve_is_explicit(self):
        wire = Wire({})
        JulesApiClient("key", transport=wire).approve_plan("123456789012")
        self.assertEqual(wire.calls[0][:2], ("POST", "sessions/123456789012:approvePlan"))

    def test_window_uses_utc_offsets_and_boundary(self):
        rows = [
            session("1", created="2026-09-20T16:00:00-04:00"),
            session("2", created="2026-09-20T19:59:59Z"),
            session("3", state="IN_PROGRESS", created="2026-09-21T19:59:59.123456789Z"),
        ]
        got = observe(Catalog(tuple(rows), 1, NOW.isoformat()), NOW)
        self.assertEqual(got["observed_rolling_starts"], 2)
        self.assertEqual(got["nonterminal_sessions"], 1)
        self.assertIsNone(got["vendor_quota_remaining"])

    def test_waiting_and_paused_keep_occupancy(self):
        rows = [
            session(str(i), state=s)
            for i, s in enumerate(["QUEUED", "PAUSED", "AWAITING_PLAN_APPROVAL", "AWAITING_USER_FEEDBACK"])
        ]
        self.assertEqual(observe(Catalog(tuple(rows), 1, ""), NOW)["nonterminal_sessions"], 4)

    def test_unknown_state_is_not_free_capacity(self):
        with self.assertRaisesRegex(JulesApiError, "unknown_provider_state"):
            observe(Catalog((session(state="NEW_UNKNOWN_STATE"),), 1, ""), NOW)

    def test_future_or_naive_time_refused(self):
        for stamp in ["2026-09-22T00:00:00Z", "2026-09-21T00:00:00"]:
            with self.assertRaises(JulesApiError):
                observe(Catalog((session(created=stamp),), 1, ""), NOW)

    def test_invalid_timestamp(self):
        for value in [None, "2026-02-30T12:00:00Z", "yesterday"]:
            with self.assertRaises(JulesApiError):
                timestamp(value)

    def test_incomplete_not_empty(self):
        with self.assertRaisesRegex(JulesApiError, "incomplete_observation"):
            observe(Catalog((), 1, "", False), NOW)

    def test_http_error_redacts_body_and_key(self):
        key = "SYNTHETIC-SECRET-DO-NOT-PRINT"
        for method, status, exception in [
            ("GET", 401, JulesApiError),
            ("POST", 503, JulesMutationUnknown),
            ("POST", 429, JulesApiError),
        ]:
            failure = urllib.error.HTTPError("https://evil.example/" + key, status, key, {}, io.BytesIO(key.encode()))
            with patch("urllib.request.build_opener") as opener:
                opener.return_value.open.side_effect = failure
                with self.assertRaises(exception) as caught:
                    _transport(method, "sessions", key, {}, 1, 1024)
                self.assertNotIn(key, str(caught.exception))

    def test_no_redirect_for_secret_header(self):
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.example"))

    def test_duplicate_json_key_is_rejected(self):
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = (
                b'{"sessions":[],"sessions":[]}'
            )
            with self.assertRaisesRegex(JulesApiError, "invalid_response"):
                _transport("GET", "sessions", "key", None, 1, 1024)

    def test_response_bound(self):
        with patch("urllib.request.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = b"x" * 1025
            with self.assertRaisesRegex(JulesMutationUnknown, "response_limit_exceeded"):
                _transport("POST", "sessions", "key", {}, 1, 1024)

    def test_missing_key_cli_returns_unknown_counts_and_nonzero(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("sys.argv", ["limen-jules-api", "observe"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            code = main()
        result = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertIsNone(result["observed_rolling_starts"])
        self.assertEqual(result["status"], "unavailable")

    def test_cli_exposes_no_mutating_command(self):
        with patch("sys.argv", ["limen-jules-api", "dispatch"]), patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)


class ResultTests(unittest.TestCase):
    def final(
        self, *, source=SOURCE, base="a" * 40, value="diff content", i="x", stamp="2026-09-21T17:00:00Z", completed=True
    ):
        result = {
            "name": "sessions/123456789012/activities/" + i,
            "createTime": stamp,
            "artifacts": [{"changeSet": {"source": source, "gitPatch": {"baseCommitId": base, "unidiffPatch": value}}}],
        }
        if completed:
            result["sessionCompleted"] = {}
        return result

    def client(self, activities, **session_extra):
        row = session(sourceContext={"source": SOURCE}, **session_extra)
        return JulesApiClient("key", transport=Wire(row, {"activities": activities}))

    def test_final_patch(self):
        client = self.client([self.final()])
        self.assertEqual(client.completed_patch("123456789012", source=SOURCE, exact_base="a" * 40), "diff content")

    def test_older_progress_patch_not_final(self):
        with self.assertRaisesRegex(JulesApiError, "no_completed_patch"):
            self.client([self.final(completed=False)]).completed_patch(
                "123456789012", source=SOURCE, exact_base="a" * 40
            )

    def test_cross_repository_patch_refused(self):
        with self.assertRaisesRegex(JulesApiError, "no_completed_patch"):
            self.client([self.final(source="sources/github/other/repo")]).completed_patch(
                "123456789012", source=SOURCE, exact_base="a" * 40
            )

    def test_stale_base_patch_refused(self):
        with self.assertRaisesRegex(JulesApiError, "no_completed_patch"):
            self.client([self.final(base="b" * 40)]).completed_patch("123456789012", source=SOURCE, exact_base="a" * 40)

    def test_empty_patch_not_success(self):
        with self.assertRaisesRegex(JulesApiError, "no_completed_patch"):
            self.client([self.final(value="")]).completed_patch("123456789012", source=SOURCE, exact_base="a" * 40)

    def test_pending_session_not_landed(self):
        with self.assertRaisesRegex(JulesApiError, "result_not_completed"):
            self.client([], state="IN_PROGRESS").completed_patch("123456789012", source=SOURCE, exact_base="a" * 40)

    def test_ambiguous_finals_refused(self):
        with self.assertRaisesRegex(JulesApiError, "ambiguous_completed_patch"):
            self.client([self.final(), self.final(i="y", value="different")]).completed_patch(
                "123456789012", source=SOURCE, exact_base="a" * 40
            )

    def test_latest_final_selected_by_timestamp_not_page_order(self):
        rows = [self.final(i="later", stamp="2026-09-21T18:00:00Z", value="last"), self.final()]
        self.assertEqual(self.client(rows).completed_patch("123456789012", source=SOURCE, exact_base="a" * 40), "last")

    def test_null_create_context_is_indeterminate(self):
        with self.assertRaises(JulesMutationUnknown):
            JulesApiClient("key", transport=Wire(session(sourceContext=None))).create(
                source=SOURCE, branch="main", prompt="x", title="y"
            )

    def test_unknown_structured_state_is_refused(self):
        with self.assertRaises(JulesApiError):
            observe(Catalog((session(state={"oops": True}),), 1, ""), NOW)


if __name__ == "__main__":
    unittest.main()
