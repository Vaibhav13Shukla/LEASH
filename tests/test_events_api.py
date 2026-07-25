import pytest
from fastapi.testclient import TestClient

from services.broker import main as broker
from services.broker.policy_store import PolicyStore

AGENT = "release-agent-01"
WEBHOOK_HEADERS = {"X-LEASH-WEBHOOK-TOKEN": "local-demo-webhook-token"}
ADMIN_HEADERS = {"X-ADMIN-TOKEN": "local-demo-admin-token"}


@pytest.fixture()
def client(tmp_path):
    broker.store = PolicyStore(str(tmp_path / "events.db"))
    from services.broker import events_api
    events_api.store = broker.store
    return TestClient(broker.app)


def test_events_api_returns_audit_trail(client):
    # Initial state should have empty events or get events
    res = client.get(f"/v1/agents/{AGENT}/events")
    assert res.status_code == 200
    assert res.json()["events"] == []

    # Demote agent
    client.post(
        "/webhooks/signoz/demote",
        headers=WEBHOOK_HEADERS,
        json={"agent_id": AGENT, "target_tier": "T1", "alert_id": "alert-events-1", "reason": "test_failure"},
    )

    # Check events list
    res = client.get(f"/v1/agents/{AGENT}/events")
    assert res.status_code == 200
    events = res.json()["events"]
    assert len(events) == 1
    assert events[0]["event_type"] == "demotion"
    assert events[0]["from_tier"] == 3
    assert events[0]["to_tier"] == 1
    assert events[0]["alert_id"] == "alert-events-1"
    assert events[0]["reason"] == "test_failure"

    # Reset agent
    client.post("/v1/admin/reset", headers=ADMIN_HEADERS, params={"agent_id": AGENT})

    # Check events list again
    res = client.get(f"/v1/agents/{AGENT}/events")
    assert res.status_code == 200
    events = res.json()["events"]
    assert len(events) == 2
    assert events[0]["event_type"] == "manual_reset"
    assert events[0]["to_tier"] == 3
