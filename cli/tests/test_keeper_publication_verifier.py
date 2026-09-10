"""The live canary must fail closed without repeating authenticated mutations."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "keeper_publication_verifier", ROOT / "scripts/verify-keeper-publication.py"
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
SHA = "a" * 40
FIRST = "b" * 40
SECOND = "c" * 40
UPDATES = [
    {
        "task_id": "CAMPAIGN",
        "amendment": "Finish implementation, deployment and all original live acceptance criteria.",
    },
    {
        "task_id": "CAMPAIGN",
        "amendment": "Preserve credential reuse across restart and plugin refresh without repeated login.",
    },
]


class Client:
    def __init__(self, *, deployed=SHA, publication=True, persist=True, rotate=False):
        self.deployed = deployed
        self.publication = publication
        self.persist = persist
        self.rotate = rotate
        self.packets = []
        self.task = {
            "id": "CAMPAIGN",
            "status": "open",
            "updated": "2026-09-08T00:00:00Z",
            "context": "private source intent",
        }

    def capabilities(self):
        return {
            "runtime_identity": {
                "git_sha": self.deployed,
                "deployment_id": "changed" if self.rotate and self.packets else "stable",
            },
            "sessions": [
                {
                    "session_id": "native-session",
                    "healthy": True,
                    "capabilities": ["task-submit"],
                    "identity": {"agent": "codex", "surface": "direct", "session_id": "native-session"},
                }
            ],
        }

    def private_board(self):
        return {"tasks": [copy.deepcopy(self.task)]}

    def submit(self, packet):
        self.packets.append(packet)
        assert packet.intent["expected_revision"] == self.task["updated"]
        assert set(packet.intent["patch"]) == {"context"}
        if self.persist:
            self.task["context"] = packet.intent["patch"]["context"]
            self.task["updated"] = f"2026-09-08T00:00:0{len(self.packets)}Z"
        projection = {
            "status": "committed",
            "mode": "private-canonical",
            "event_id": f"event-{len(self.packets)}",
            "task": self.task,
        }
        if self.publication:
            projection["publication"] = {
                "status": "committed",
                "mode": "public-aggregate",
                "sha": FIRST if len(self.packets) == 1 else SECOND,
            }
        return {"run_id": f"run-{len(self.packets)}", "projection_receipts": [projection]}


def github_read(path, **kwargs):
    if path.startswith("git/ref/"):
        return None
    assert path == f"compare/{FIRST}...{SECOND}"
    return {"status": "ahead", "merge_base_commit": {"sha": FIRST}}


def execute(tmp_path, client, **kwargs):
    return verifier.verify(
        client, SHA, "native-session", UPDATES, tmp_path / "receipt.json", github_read=github_read, **kwargs
    )


def test_two_real_amendments_have_bound_redacted_receipt(tmp_path):
    client = Client()
    receipt = execute(tmp_path, client)
    assert receipt["status"] == "passed"
    assert receipt["initial_ref_missing"] is True
    assert receipt["manual_ref_writes"] == 0
    assert len(client.packets) == 2
    assert all(packet.spend.limit == 0 for packet in client.packets)
    assert all(set(packet.authority.actions) == {"task.mutate"} for packet in client.packets)
    assert client.task["status"] == "open"
    assert client.task["context"].startswith("private source intent")
    assert [row["publication_sha"] for row in receipt["mutations"]] == [FIRST, SECOND]
    serialized = json.dumps(receipt)
    assert "private source intent" not in serialized
    assert all(update["amendment"] not in serialized for update in UPDATES)


def test_wrong_deployment_never_submits(tmp_path):
    client = Client(deployed="d" * 40)
    with pytest.raises(ValueError, match="captured merged SHA"):
        execute(tmp_path, client)
    assert not client.packets


@pytest.mark.parametrize("options", [{"publication": False}, {"persist": False}, {"rotate": True}])
def test_missing_receipt_or_failed_reread_never_submits_second(tmp_path, options):
    client = Client(**options)
    with pytest.raises(ValueError):
        execute(tmp_path, client)
    assert len(client.packets) == 1
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert receipt["status"] == "incomplete"
    with pytest.raises(ValueError, match="already exists"):
        execute(tmp_path, client)
    assert len(client.packets) == 1


def test_nonancestral_publications_fail(tmp_path):
    client = Client()
    with pytest.raises(ValueError, match="preserve"):
        verifier.verify(
            client,
            SHA,
            "native-session",
            UPDATES,
            tmp_path / "receipt.json",
            github_read=lambda path, **kwargs: None if path.startswith("git/ref/") else {"status": "diverged"},
        )
    assert len(client.packets) == 2


def test_repeated_context_cannot_manufacture_second_mutation(tmp_path):
    client = Client()
    client.task["context"] += UPDATES[0]["amendment"]
    with pytest.raises(ValueError, match="already recorded"):
        execute(tmp_path, client)
    assert not client.packets


def test_preexisting_receipt_fails_before_broker_access(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("interrupted evidence")
    with pytest.raises(ValueError, match="already exists"):
        verifier.verify(None, SHA, "native-session", UPDATES, receipt)
    assert receipt.read_text() == "interrupted evidence"


def test_identical_intent_is_not_two_mutations(tmp_path):
    with pytest.raises(ValueError, match="duplicate amendment"):
        verifier.verify(None, SHA, "native-session", [UPDATES[0], UPDATES[0]], tmp_path / "receipt.json")
