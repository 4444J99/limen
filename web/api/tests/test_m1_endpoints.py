"""
Tests for Milestone 1 Backend API endpoints: Decisions, Timelines, Webhooks Ingress, OAuth2, and SCIM 2.0.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

hashlib = __import__("hashlib")
hmac = __import__("hmac")
json = __import__("json")
time = __import__("time")
from fastapi.testclient import TestClient
import pytest

from main import app
import db


@pytest.fixture
def client():
    return TestClient(app)


def test_decisions_endpoint(client):
    db.db_create_task({"id": "task-01", "title": "Test Task 01"})
    db.db_create_decision({"id": "dec-test-01", "task_id": "task-01", "title": "Approve architecture", "status": "approved", "reasoning": "Meets criteria"})
    
    response = client.get("/api/decisions")
    assert response.status_code == 200
    data = response.json()
    assert "decisions" in data
    assert any(d["id"] == "dec-test-01" for d in data["decisions"])


def test_timelines_endpoint(client):
    db.db_create_task({"id": "task-01", "title": "Test Task 01"})
    db.db_create_timeline({"id": "evt-test-01", "task_id": "task-01", "event_type": "task.created", "payload": {"info": "test"}})

    response = client.get("/api/timelines")
    assert response.status_code == 200
    data = response.json()
    assert "timelines" in data
    assert any(t["id"] == "evt-test-01" for t in data["timelines"])


def test_webhook_ingress_endpoint(client):
    secret = "webhook-secret-key-12345"  # allow-secret
    ts = int(time.time())
    payload = {"event_type": "task.verified", "task_id": "task-100"}
    raw_body = json.dumps(payload, separators=(",", ":"))

    data_to_sign = f"{ts}.{raw_body}"
    sig = hmac.new(secret.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    signature_header = f"t={ts},v1={sig}"

    response = client.post(
        "/api/webhooks/ingress",
        headers={"X-Collab-Signature": signature_header, "X-Idempotency-Key": "idemp-001"},
        content=raw_body,
    )
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "accepted"
    assert "event_id" in res_data


def test_webhook_ingress_signature_mismatch(client):
    response = client.post(
        "/api/webhooks/ingress",
        headers={"X-Collab-Signature": "t=1700000000,v1=bad_sig"},
        content='{"test": 1}',
    )
    assert response.status_code == 400


def test_webhook_ingress_replay_rejection(client):
    secret = "webhook-secret-key-12345"  # allow-secret
    ts = int(time.time())
    payload = {"event_type": "task.verified", "task_id": "task-101"}
    raw_body = json.dumps(payload, separators=(",", ":"))

    data_to_sign = f"{ts}.{raw_body}"
    sig = hmac.new(secret.encode("utf-8"), data_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    signature_header = f"t={ts},v1={sig}"

    headers = {"X-Collab-Signature": signature_header, "X-Idempotency-Key": "idemp-replay-test"}

    res1 = client.post("/api/webhooks/ingress", headers=headers, content=raw_body)
    assert res1.status_code == 200

    res2 = client.post("/api/webhooks/ingress", headers=headers, content=raw_body)
    assert res2.status_code == 400
    assert "Replay attack" in res2.json()["detail"]


def test_oauth_client_credentials_grant(client):
    response = client.post(
        "/oauth/token?grant_type=client_credentials&client_id=client-id-01&client_secret=client-secret-01-super-secret-value-24-chars&scope=read"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "Bearer"
    assert data["access_token"].startswith("limen_at_")


def test_scim_user_provisioning_lifecycle(client):
    # 1. Create User
    create_payload = {
        "userName": "bob@example.com",
        "externalId": "bob-ext-01",
        "name": {"formatted": "Bob Marley"},
        "emails": [{"value": "bob@example.com"}],
        "active": True,
    }
    create_res = client.post("/scim/v2/Users", json=create_payload)
    assert create_res.status_code == 201
    user = create_res.json()
    assert user["userName"] == "bob@example.com"
    user_id = user["id"]

    # 2. Get User
    get_res = client.get(f"/scim/v2/Users/{user_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == user_id

    # 3. List Users
    list_res = client.get('/scim/v2/Users?filter=userName eq "bob@example.com"')
    assert list_res.status_code == 200
    assert list_res.json()["totalResults"] >= 1

    # 4. Update User (PUT & PATCH)
    put_res = client.put(f"/scim/v2/Users/{user_id}", json={"userName": "bob@example.com", "name": {"formatted": "Robert Marley"}})
    assert put_res.status_code == 200
    assert put_res.json()["name"]["formatted"] == "Robert Marley"

    patch_res = client.patch(f"/scim/v2/Users/{user_id}", json={"active": False})
    assert patch_res.status_code == 200
    assert patch_res.json()["active"] is False

    # 5. Duplicate User Create Failure (409)
    dup_res = client.post("/scim/v2/Users", json=create_payload)
    assert dup_res.status_code == 409

    # 6. Deactivate User
    del_res = client.delete(f"/scim/v2/Users/{user_id}")
    assert del_res.status_code == 204


def test_scim_group_lifecycle(client):
    db.db_create_user({"id": "usr-test-01", "user_name": "alice@example.com"})
    # 1. Create Group
    group_payload = {
        "displayName": "Engineering",
        "members": [{"value": "usr-test-01"}]
    }
    create_res = client.post("/scim/v2/Groups", json=group_payload)
    assert create_res.status_code == 201
    grp = create_res.json()
    assert grp["displayName"] == "Engineering"
    grp_id = grp["id"]

    # 2. Get Group by ID
    get_res = client.get(f"/scim/v2/Groups/{grp_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == grp_id

    # 3. List Groups with Filter
    list_res = client.get('/scim/v2/Groups?filter=displayName eq "Engineering"')
    assert list_res.status_code == 200
    assert list_res.json()["totalResults"] >= 1

    # 4. Duplicate Group Create Failure (409)
    dup_res = client.post("/scim/v2/Groups", json=group_payload)
    assert dup_res.status_code == 409

    # 5. Delete Group
    del_res = client.delete(f"/scim/v2/Groups/{grp_id}")
    assert del_res.status_code == 204

    # 6. Get Non-existent Group (404)
    get_404 = client.get(f"/scim/v2/Groups/{grp_id}")
    assert get_404.status_code == 404
