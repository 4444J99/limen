"""Read-only native schedule adapters and an append-only private evidence cache.

Only derived metadata enters SQLite. These records attest neither authority nor
truth of provider prose, and this module never launches or evaluates that prose.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import sqlite3
import stat
import subprocess
from datetime import datetime, timezone
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "limen.schedule_observation.v1"
SNAPSHOT_SCHEMA = "limen.schedule_snapshot.v1"
_VOLATILE = {"observation_id", "observed_at", "first_observed_at", "last_observed_at"}
_TIMES = {"started_at", "completed_at", "scheduled_for", "artifact_created_at", "artifact_completed_at",
          "artifact_scheduled_for", "gmail_internal_date"}
_ARTIFACT = {"sha256", "byte_count", "coverage", "ref", "run_id", "scheduled_for", "truncated"}
_ROW_KEYS = {"schema", "observation_id", "provider", "surface", "account_ref",
             "owner_ref", "source_ref", "native_task_id", "native_run_id",
             "native_artifact_id", "execution_status", "times", "artifact",
             "attribution_state", "attribution_evidence", "collection_state",
             "acceptance_state", "delivery_state", "capacity_state", "next_action",
             "observed_at", "gmail_thread_id", "native_links"}
_ROW_KEYS.add("native_run_ref")


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _ref(value, *, required=False):
    if value is None and not required:
        return None
    if (not isinstance(value, str) or not value.strip() or len(value) > 2048
            or any(ord(char) < 32 for char in value)):
        raise ValueError("invalid reference field")
    return value


def _provider_ref(value):
    """Preserve supported native identity without storing objects or URL secrets."""
    if isinstance(value, dict):
        if (set(value) != {"id", "type"} or value.get("type") not in ("chatgpt", "codex")
                or not isinstance(value.get("id"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", value["id"])):
            raise ValueError("invalid native chat reference")
        return f"native:{value['type']}:chat:{value['id']}"
    value = _ref(value)
    if value is not None and "://" in value:
        try:
            url = urlsplit(value)
            if (url.scheme != "https" or not url.hostname or url.username is not None
                    or url.password is not None or url.query or url.fragment):
                raise ValueError
        except ValueError:
            raise ValueError("unsafe provider URL reference") from None
    return value


def _time(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _observed(value):
    if _time(value) is None:
        raise ValueError("observation time requires a timezone")
    return value


def _content(value):
    if not isinstance(value, (str, bytes)):
        raise ValueError("artifact content must be text or bytes")
    return value.encode("utf-8") if isinstance(value, str) else value


def _coverage(value):
    if value not in ("complete", "partial", "unknown"):
        raise ValueError("invalid artifact coverage")
    return value


def _base(*, provider, surface, account_ref, owner_ref, source_ref, observed_at):
    return {
        "schema": SCHEMA, "provider": _ref(provider, required=True),
        "surface": _ref(surface, required=True),
        "account_ref": _ref(account_ref, required=True),
        "owner_ref": _ref(owner_ref, required=True),
        "source_ref": _ref(source_ref, required=True),
        "native_task_id": None, "native_run_id": None, "native_run_ref": None,
        "native_artifact_id": None,
        "execution_status": "unknown", "times": dict.fromkeys(sorted(_TIMES)),
        "artifact": {"sha256": None, "byte_count": None, "coverage": "unknown",
                     "ref": None, "run_id": None, "scheduled_for": None, "truncated": None},
        "attribution_state": "unresolved", "attribution_evidence": None,
        "collection_state": "unavailable", "acceptance_state": "unassessed",
        "delivery_state": "unknown", "capacity_state": "unknown",
        "next_action": "retrieve_attributable_native_output",
        "observed_at": _observed(observed_at), "gmail_thread_id": None,
        "native_links": [],
    }


def _canonical(row):
    return {key: value for key, value in row.items() if key not in _VOLATILE}


def _finish(row):
    row["observation_id"] = _hash(_canonical(row))
    _validate_row(row)
    return row


def _chatgpt_correlated(row):
    started = _time(row["times"]["started_at"])
    created = _time(row["times"]["artifact_created_at"])
    scheduled = _time(row["times"]["scheduled_for"])
    artifact_scheduled = _time(row["times"]["artifact_scheduled_for"])
    return bool(row["native_run_id"] and row["native_run_id"] == row["artifact"]["run_id"]
                and started is not None and created is not None and created >= started
                and scheduled is not None and artifact_scheduled == scheduled
                and _time(row["artifact"]["scheduled_for"]) == artifact_scheduled)


def _attach(row, content, coverage, ref):
    data = _content(content)
    row["artifact"].update(sha256=hashlib.sha256(data).hexdigest(),
                           byte_count=len(data), coverage=_coverage(coverage), ref=_ref(ref))
    row["collection_state"] = "complete" if coverage == "complete" else "partial"


def normalize_chatgpt(task: dict, *, observed_at: str, account_ref: str,
                      owner_ref: str) -> dict:
    """Preserve independent current-attempt and latest-artifact identities."""
    if not isinstance(task, dict):
        raise ValueError("invalid native task")
    task_id = _ref(task.get("id"), required=True)
    row = _base(provider="chatgpt", surface="tasks", account_ref=account_ref,
                owner_ref=owner_ref,
                source_ref=_provider_ref(task.get("source_ref")) or f"chatgpt:task:{task_id}",
                observed_at=observed_at)
    row["native_task_id"] = task_id
    details = task.get("run_details", task)
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise ValueError("invalid native run details")
    run, result = details.get("last_run") or {}, details.get("latest_result") or {}
    if not isinstance(run, dict) or not isinstance(result, dict):
        raise ValueError("invalid native run or artifact")
    row["native_run_id"] = _ref(run.get("id"))
    row["native_run_ref"] = _provider_ref(run.get("chat_ref"))
    row["execution_status"] = _ref(run.get("recorded_status", run.get("status"))) or "unknown"
    for key in ("started_at", "completed_at", "scheduled_for"):
        row["times"][key] = _ref(run.get(key))
    row["native_artifact_id"] = _ref(result.get("id"))
    row["artifact"]["run_id"] = _ref(result.get("run_id"))
    row["artifact"]["scheduled_for"] = _ref(result.get("scheduled_for"))
    row["times"]["artifact_created_at"] = _ref(result.get("created_at"))
    row["times"]["artifact_completed_at"] = _ref(result.get("completed_at"))
    row["times"]["artifact_scheduled_for"] = _ref(result.get("scheduled_for"))
    content = result.get("content_text", result.get("content"))
    truncated = result.get("content_truncated")
    if "content_truncated" in result and type(truncated) is not bool:
        raise ValueError("native truncation flag must be boolean")
    row["artifact"]["truncated"] = truncated
    artifact_ref = (_provider_ref(result.get("source_ref"))
                    or _provider_ref(result.get("chat_ref")))
    if content is not None:
        artifact_ref = artifact_ref or (
            f"chatgpt:artifact:{row['native_artifact_id']}" if row["native_artifact_id"]
            else f"chatgpt:result:{row['artifact']['run_id']}:{row['times']['artifact_created_at']}")
        coverage = _coverage(result.get("coverage", "complete" if truncated is False else "unknown"))
        if truncated is True:
            coverage = "partial"
        _attach(row, content, coverage, artifact_ref)
    if _chatgpt_correlated(row):
        row["attribution_state"] = "correlated"
        row["attribution_evidence"] = "native:run_id+created_at+scheduled_for"
        row["next_action"] = ("owner_assessment_required" if row["artifact"]["coverage"] == "complete"
                              else "retrieve_complete_native_output")
    return _finish(row)


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self.hidden = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if not self.hidden:
            if tag == "a":
                self.links.extend(value for key, value in attrs if key == "href" and value)
            if tag in ("p", "div", "br", "li"):
                self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        elif not self.hidden and tag in ("p", "div", "li"):
            self.text.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def _safe_link(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme == "https" and parsed.netloc == "grok.com"
                and not parsed.query and not parsed.fragment
                and re.fullmatch(r"/chat/[A-Za-z0-9_-]{1,256}", parsed.path)):
            return value
    except ValueError:
        pass
    return None


def _mime_parts(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid MIME structure")
    mime = payload.get("mime_type", payload.get("mimeType", ""))
    if mime in ("text/plain", "text/html"):
        body = payload.get("body") or {}
        if not isinstance(body, dict):
            raise ValueError("invalid MIME body")
        text = body.get("content")
        encoded = body.get("base64_url_content", body.get("data"))
        if text is not None:
            if not isinstance(text, str):
                raise ValueError("invalid MIME content")
            yield mime, text
        elif encoded is not None:
            if not isinstance(encoded, str):
                raise ValueError("invalid MIME encoding")
            try:
                data = base64.b64decode(encoded + "=" * (-len(encoded) % 4),
                                        altchars=b"-_", validate=True).decode("utf-8")
            except (ValueError, UnicodeError, binascii.Error):
                raise ValueError("invalid MIME encoding") from None
            yield mime, data
    parts = payload.get("parts", [])
    if parts is None:
        parts = []
    if not isinstance(parts, list):
        raise ValueError("invalid MIME structure")
    for part in parts:
        yield from _mime_parts(part)


def normalize_grok_email(message: dict, *, observed_at: str, account_ref: str,
                         owner_ref: str) -> dict:
    """Collect a verified vendor notification without inventing native run facts."""
    if not isinstance(message, dict) or not isinstance(message.get("payload"), dict):
        raise ValueError("invalid Gmail message")
    payload = message["payload"]
    headers = payload.get("headers", [])
    if not isinstance(headers, list) or any(not isinstance(h, dict) for h in headers):
        raise ValueError("invalid sender headers")
    senders = [h.get("value") for h in headers if str(h.get("name", "")).lower() == "from"]
    if (len(senders) != 1 or not isinstance(senders[0], str)
            or [address for _, address in getaddresses(senders)] != ["noreply@x.ai"]):
        raise ValueError("unverified vendor sender")
    message_id = _ref(message.get("id"), required=True)
    row = _base(provider="grok", surface="automations_email", account_ref=account_ref,
                owner_ref=owner_ref, source_ref=f"gmail:message:{message_id}", observed_at=observed_at)
    row["native_artifact_id"] = message_id
    row["gmail_thread_id"] = _ref(message.get("thread_id", message.get("threadId")), required=True)
    internal_date = message.get("internal_date", message.get("internalDate"))
    if not isinstance(internal_date, str) or not re.fullmatch(r"[0-9]{1,20}", internal_date):
        raise ValueError("invalid Gmail internal date")
    row["times"]["gmail_internal_date"] = internal_date
    parts = list(_mime_parts(payload))
    plain = [body for mime, body in parts if mime == "text/plain"]
    html = [body for mime, body in parts if mime == "text/html"]
    links = []
    if plain:
        body = "\n".join(plain)
        links = re.findall(r"https://[^\s<>\"']+", body)
    elif html:
        parser = _HTML()
        parser.feed("\n".join(html))
        body = re.sub(r"\s+", " ", "".join(parser.text)).strip()
        links = parser.links
    else:
        body = None
    row["native_links"] = sorted({link for link in links if _safe_link(link)})
    if body is not None:
        _attach(row, body, "partial", row["source_ref"])
    row["next_action"] = "retrieve_complete_native_output_with_occurrence_identity"
    return _finish(row)


def normalize_artifact(payload: dict, *, observed_at: str) -> dict:
    """Normalize explicit provenance supplied by an external supported collector."""
    if not isinstance(payload, dict):
        raise ValueError("invalid artifact payload")
    row = _base(**{key: payload.get(key) for key in
                   ("provider", "surface", "account_ref", "owner_ref", "source_ref")},
                observed_at=observed_at)
    for key in ("native_task_id", "native_run_id", "native_artifact_id", "attribution_evidence"):
        row[key] = _ref(payload.get(key))
    row["execution_status"] = _ref(payload.get("execution_status")) or "unknown"
    times = payload.get("times", {})
    if not isinstance(times, dict) or set(times) - _TIMES:
        raise ValueError("invalid artifact times")
    row["times"].update({key: _ref(value) for key, value in times.items()})
    _attach(row, payload.get("content"), payload.get("coverage"),
            payload.get("artifact_ref") or row["source_ref"])
    row["artifact"]["run_id"] = row["native_run_id"]
    row["artifact"]["scheduled_for"] = row["times"]["scheduled_for"]
    if row["native_run_id"] and row["native_artifact_id"] and row["attribution_evidence"]:
        row["attribution_state"] = "correlated"
        row["next_action"] = ("owner_assessment_required" if row["artifact"]["coverage"] == "complete"
                              else "retrieve_complete_native_output")
    return _finish(row)


def _validate_row(row):
    if (not isinstance(row, dict) or not _ROW_KEYS <= set(row)
            or set(row) - _VOLATILE != _ROW_KEYS - _VOLATILE):
        raise ValueError("invalid observation fields")
    if row.get("schema") != SCHEMA or row.get("observation_id") != _hash(_canonical(row)):
        raise ValueError("conflicting observation identity")
    for key in _ROW_KEYS - {"times", "artifact", "native_links"} - _VOLATILE:
        _ref(row[key], required=key in {"provider", "surface", "account_ref", "owner_ref", "source_ref"})
    _observed(row["observed_at"])
    if not isinstance(row["times"], dict) or set(row["times"]) != _TIMES:
        raise ValueError("invalid observation times")
    for value in row["times"].values():
        _ref(value)
    artifact = row["artifact"]
    if not isinstance(artifact, dict) or set(artifact) != _ARTIFACT:
        raise ValueError("invalid artifact metadata")
    for key in ("ref", "run_id", "scheduled_for"):
        _ref(artifact[key])
    _coverage(artifact["coverage"])
    if artifact["sha256"] is not None:
        if (not isinstance(artifact["sha256"], str)
                or not re.fullmatch("[0-9a-f]{64}", artifact["sha256"])
                or type(artifact["byte_count"]) is not int or artifact["byte_count"] < 0):
            raise ValueError("invalid artifact digest")
    elif artifact["byte_count"] is not None or artifact["coverage"] != "unknown":
        raise ValueError("missing artifact digest")
    if (row["attribution_state"] not in ("unresolved", "correlated")
            or row["collection_state"] not in ("unavailable", "partial", "complete")
            or row["acceptance_state"] != "unassessed" or row["delivery_state"] != "unknown"
            or row["capacity_state"] != "unknown"):
        raise ValueError("invalid evidence state")
    truncated = artifact["truncated"]
    if truncated is not None and type(truncated) is not bool:
        raise ValueError("invalid artifact truncation metadata")
    expected_collection = ("unavailable" if artifact["sha256"] is None else
                           "complete" if artifact["coverage"] == "complete" else "partial")
    if (row["collection_state"] != expected_collection
            or (truncated is True and artifact["sha256"] is not None
                and artifact["coverage"] != "partial")):
        raise ValueError("contradictory collection or coverage metadata")
    if row["attribution_state"] == "correlated":
        if (not row["native_run_id"] or row["native_run_id"] != artifact["run_id"]
                or not row["attribution_evidence"]
                or row["attribution_evidence"].lower() in ("unknown", "unverified", "unresolved")):
            raise ValueError("correlation requires explicit occurrence and attribution evidence")
        if row["provider"] == "chatgpt" and row["surface"] == "tasks":
            if (not row["native_task_id"] or not _chatgpt_correlated(row)
                    or row["attribution_evidence"] != "native:run_id+created_at+scheduled_for"):
                raise ValueError("contradictory native ChatGPT attribution")
        elif not row["native_artifact_id"]:
            raise ValueError("correlation requires native artifact identity")
    if row["provider"] == "chatgpt" and row["surface"] == "tasks":
        for value in (row["source_ref"], row["native_run_ref"], artifact["ref"]):
            _provider_ref(value)
    if row["provider"] == "grok" and row["surface"] == "automations_email":
        if (row["attribution_state"] != "unresolved" or artifact["coverage"] == "complete"
                or row["native_run_id"] is not None or artifact["run_id"] is not None
                or row["times"]["started_at"] is not None or row["times"]["completed_at"] is not None
                or not row["native_artifact_id"] or not row["gmail_thread_id"]
                or row["source_ref"] != f"gmail:message:{row['native_artifact_id']}"):
            raise ValueError("notification email cannot establish complete native occurrence evidence")
    if (not isinstance(row["native_links"], list)
            or any(not isinstance(link, str) or not _safe_link(link) for link in row["native_links"])):
        raise ValueError("invalid native links")


def _private_path(path, *, create=True):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("private cache cannot use symlinks")
    if path.exists() and not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("private cache requires a regular file")
    if path.parent.exists() and stat.S_IMODE(path.parent.stat().st_mode) != 0o700:
        raise ValueError("existing cache parent must be owner-only; use a dedicated private directory")
    ancestor = path.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    probe = subprocess.run(["git", "-C", str(ancestor), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, check=False)
    if probe.returncode == 0:
        root = Path(probe.stdout.strip())
        relative = str(path.relative_to(root))
        tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
                                 capture_output=True, check=False)
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", relative],
                                 capture_output=True, check=False)
        if tracked.returncode != 1 or ignored.returncode != 0:
            raise ValueError("private cache requires an ignored untracked path")
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for parent in reversed(missing):
        parent.mkdir(mode=0o700)
    if not create:
        return path
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.fchmod(descriptor, 0o600)
    os.close(descriptor)
    return path


class EvidenceStore:
    """Transactional metadata history, separate from all native launch authorities."""

    def __init__(self, path: Path):
        self.path = _private_path(path)
        self._db = sqlite3.connect(self.path)
        self._db.execute("PRAGMA journal_mode=DELETE")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                first_observed_at TEXT NOT NULL, last_observed_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS assessments (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checkpoints (
                source_id TEXT NOT NULL, revision INTEGER NOT NULL, cursor TEXT NOT NULL,
                PRIMARY KEY(source_id, revision));
        """)

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _ingest(self, observations):
        if not isinstance(observations, list):
            raise ValueError("observations must be a list")
        inserted = 0
        for row in observations:
            _validate_row(row)
            first = _observed(row.get("first_observed_at", row["observed_at"]))
            last = _observed(row.get("last_observed_at", row["observed_at"]))
            if not _time(first) <= _time(row["observed_at"]) <= _time(last):
                raise ValueError("invalid observation window")
            payload = _json(_canonical(row))
            existing = self._db.execute("SELECT payload,first_observed_at,last_observed_at "
                                        "FROM observations WHERE id=?", (row["observation_id"],)).fetchone()
            if existing:
                if existing[0] != payload:
                    raise ValueError("conflicting observation identity")
                first = min(first, existing[1], key=_time)
                last = max(last, existing[2], key=_time)
                self._db.execute("UPDATE observations SET first_observed_at=?,last_observed_at=? WHERE id=?",
                                 (first, last, row["observation_id"]))
            else:
                self._db.execute("INSERT INTO observations VALUES (?,?,?,?)",
                                 (row["observation_id"], payload, first, last))
                inserted += 1
        return {"inserted": inserted, "deduplicated": len(observations) - inserted}

    def ingest(self, observations: list[dict]) -> dict:
        with self._db:
            return self._ingest(observations)

    def export(self) -> dict:
        # SAVEPOINT starts a real transaction even for SELECT-only callers. Its first SELECT
        # pins all three tables to one committed state; an outer transaction remains owned
        # by the caller. A connection context manager alone does not begin a SELECT snapshot.
        self._db.execute("SAVEPOINT schedule_export")
        try:
            rows = []
            for identity, payload, first, last in self._db.execute("SELECT * FROM observations ORDER BY id"):
                rows.append(dict(json.loads(payload), observation_id=identity, observed_at=first,
                                 first_observed_at=first, last_observed_at=last))
            assessments = [json.loads(row[0]) for row in self._db.execute(
                "SELECT payload FROM assessments ORDER BY rowid")]
            checkpoints = [dict(source_id=source, revision=revision, cursor=json.loads(cursor))
                           for source, revision, cursor in self._db.execute(
                               "SELECT * FROM checkpoints ORDER BY source_id,revision")]
            return {"schema": SNAPSHOT_SCHEMA, "observations": rows,
                    "assessments": assessments, "checkpoints": checkpoints}
        except BaseException:
            self._db.execute("ROLLBACK TO SAVEPOINT schedule_export")
            raise
        finally:
            self._db.execute("RELEASE SAVEPOINT schedule_export")

    def _assessment(self, observation_id, *, status, owner_ref, predicate, evidence_ref,
                    artifact_sha256, destination_ref=None):
        if status not in ("accepted", "delivered"):
            raise ValueError("invalid assessment status")
        for value in (owner_ref, predicate, evidence_ref, artifact_sha256):
            _ref(value, required=True)
        _ref(destination_ref, required=status == "delivered")
        stored = self._db.execute("SELECT payload,first_observed_at FROM observations WHERE id=?",
                                  (observation_id,)).fetchone()
        if not stored:
            raise ValueError("unknown observation")
        row = json.loads(stored[0])
        _validate_row(dict(row, observation_id=observation_id, observed_at=stored[1]))
        if (row["artifact"]["coverage"] != "complete" or row["attribution_state"] != "correlated"
                or not row["artifact"]["sha256"] or row["artifact"]["sha256"] != artifact_sha256
                or owner_ref != row["owner_ref"]):
            raise ValueError("assessment lacks exact complete attributed artifact")
        if status == "delivered":
            prior = [json.loads(record[0]) for record in self._db.execute("SELECT payload FROM assessments")]
            if not any(record["observation_id"] == observation_id and record["status"] == "accepted"
                       and record["artifact_sha256"] == artifact_sha256 for record in prior):
                raise ValueError("delivery requires prior acceptance")
        record = dict(schema="limen.schedule_assessment.v1", observation_id=observation_id,
                      status=status, owner_ref=owner_ref, predicate=predicate, evidence_ref=evidence_ref,
                      artifact_sha256=artifact_sha256, destination_ref=destination_ref)
        record["assessment_id"] = _hash(record)
        self._db.execute("INSERT OR IGNORE INTO assessments VALUES (?,?)",
                         (record["assessment_id"], _json(record)))
        return record

    def assess(self, observation_id: str, *, status: str, owner_ref: str, predicate: str,
               evidence_ref: str, artifact_sha256: str, destination_ref: str | None = None) -> dict:
        with self._db:
            return self._assessment(observation_id, status=status, owner_ref=owner_ref,
                                    predicate=predicate, evidence_ref=evidence_ref,
                                    artifact_sha256=artifact_sha256, destination_ref=destination_ref)

    @staticmethod
    def _cursor(source_id, cursor):
        _ref(source_id, required=True)
        if not isinstance(cursor, dict) or len(cursor) > 32:
            raise ValueError("invalid checkpoint cursor")
        for key, value in cursor.items():
            _ref(key, required=True)
            if value is not None and type(value) not in (str, int, bool):
                raise ValueError("invalid checkpoint cursor")
            if isinstance(value, str):
                _ref(value)
        return _json(cursor)

    def checkpoint(self, source_id: str, cursor: dict, *, complete: bool) -> bool:
        if type(complete) is not bool:
            raise ValueError("checkpoint completeness must be explicit")
        if not complete:
            return False
        encoded = self._cursor(source_id, cursor)
        with self._db:
            previous = self._db.execute("SELECT revision,cursor FROM checkpoints WHERE source_id=? "
                                        "ORDER BY revision DESC LIMIT 1", (source_id,)).fetchone()
            if not previous or previous[1] != encoded:
                self._db.execute("INSERT INTO checkpoints VALUES (?,?,?)",
                                 (source_id, previous[0] + 1 if previous else 1, encoded))
        return True

    def import_snapshot(self, snapshot: dict) -> dict:
        if (not isinstance(snapshot, dict) or set(snapshot) != {
                "schema", "observations", "assessments", "checkpoints"}
                or snapshot["schema"] != SNAPSHOT_SCHEMA
                or any(not isinstance(snapshot[key], list) for key in
                       ("observations", "assessments", "checkpoints"))):
            raise ValueError("invalid evidence snapshot")
        with self._db:
            result = self._ingest(snapshot["observations"])
            # Replay in supplied order: delivery before acceptance fails closed.
            for assessment in snapshot["assessments"]:
                if not isinstance(assessment, dict) or set(assessment) != {
                        "schema", "assessment_id", "observation_id", "status", "owner_ref",
                        "predicate", "evidence_ref", "artifact_sha256", "destination_ref"}:
                    raise ValueError("invalid assessment snapshot")
                expected = _hash({key: value for key, value in assessment.items() if key != "assessment_id"})
                if (assessment["schema"] != "limen.schedule_assessment.v1"
                        or expected != assessment["assessment_id"]):
                    raise ValueError("conflicting assessment identity")
                self._assessment(**{key: value for key, value in assessment.items()
                                    if key not in ("schema", "assessment_id")})
            incoming = {}
            for checkpoint in snapshot["checkpoints"]:
                if not isinstance(checkpoint, dict) or set(checkpoint) != {"source_id", "revision", "cursor"}:
                    raise ValueError("invalid checkpoint snapshot")
                source, revision = checkpoint["source_id"], checkpoint["revision"]
                cursor = self._cursor(source, checkpoint["cursor"])
                if type(revision) is not int or revision < 1:
                    raise ValueError("invalid checkpoint revision")
                incoming[source] = max(incoming.get(source, 0), revision)
                previous = self._db.execute("SELECT cursor FROM checkpoints WHERE source_id=? AND revision=?",
                                            (source, revision)).fetchone()
                if previous and previous[0] != cursor:
                    raise ValueError("conflicting checkpoint history")
                self._db.execute("INSERT OR IGNORE INTO checkpoints VALUES (?,?,?)", (source, revision, cursor))
            for source, revision in incoming.items():
                current = self._db.execute("SELECT MAX(revision) FROM checkpoints WHERE source_id=?",
                                           (source,)).fetchone()[0]
                if revision < current:
                    raise ValueError("checkpoint import would regress committed cursor")
        return result
