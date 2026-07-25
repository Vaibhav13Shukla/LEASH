import pytest
from fastapi.testclient import TestClient

from services.broker import main as broker
from services.broker.policy_store import PolicyStore

AGENT = "release-agent-01"
WEBHOOK_HEADERS = {"X-LEASH-WEBHOOK-TOKEN": "local-demo-webhook-token"}
ADMIN_HEADERS = {"X-ADMIN-TOKEN": "local-demo-admin-token"}


@pytest.fixture()
def client(tmp_path):
    broker.store = PolicyStore(str(tmp_path / "stress.db"))
    return TestClient(broker.app)


def demote(client: TestClient, target: str = "T1", alert_id: str = "alert-1"):
    return client.post(
        "/webhooks/signoz/demote",
        headers=WEBHOOK_HEADERS,
        json={"agent_id": AGENT, "target_tier": target, "alert_id": alert_id, "reason": "migration_error_budget_exhausted"},
    )


def test_best_case_agent_starts_at_full_authority(client):
    assert client.get(f"/v1/agents/{AGENT}/policy").json()["current_tier"] == "T3"


def test_average_case_single_alert_demotes_to_read_only(client):
    response = demote(client)
    assert response.status_code == 200
    assert response.json()["current_tier"] == "T1"


def test_worst_case_duplicate_alert_is_idempotent(client):
    first = demote(client, alert_id="retry-safe-alert")
    second = demote(client, alert_id="retry-safe-alert")
    assert first.json()["policy_version"] == second.json()["policy_version"]
    assert second.json()["current_tier"] == "T1"


def test_worst_case_valid_token_cannot_promote_demoted_agent(client):
    demote(client)
    response = demote(client, target="T3", alert_id="malicious-promotion")
    assert response.status_code == 400
    assert client.get(f"/v1/agents/{AGENT}/policy").json()["current_tier"] == "T1"


@pytest.mark.parametrize("target", ["T9", "invalid", "", None])
def test_worst_case_invalid_tier_is_rejected_without_state_change(client, target):
    response = client.post(
        "/webhooks/signoz/demote",
        headers=WEBHOOK_HEADERS,
        json={"agent_id": AGENT, "target_tier": target, "alert_id": "bad-tier", "reason": "bad-input"},
    )
    assert response.status_code == 422
    assert client.get(f"/v1/agents/{AGENT}/policy").json()["current_tier"] == "T3"


def test_worst_case_unauthorized_webhook_cannot_change_policy(client):
    response = client.post(
        "/webhooks/signoz/demote",
        headers={"X-LEASH-WEBHOOK-TOKEN": "wrong"},
        json={"agent_id": AGENT, "target_tier": "T1"},
    )
    assert response.status_code == 401
    assert client.get(f"/v1/agents/{AGENT}/policy").json()["current_tier"] == "T3"


def test_worst_case_unknown_tool_is_not_routable(client):
    response = client.post("/v1/tools/format_production_disk", headers={"X-AGENT-ID": AGENT}, json={"task_id": "bad"})
    assert response.status_code == 404


def test_worst_case_demoted_agent_cannot_call_destructive_tool(client):
    demote(client)
    response = client.post("/v1/tools/delete_staging_table", headers={"X-AGENT-ID": AGENT}, json={"task_id": "dangerous"})
    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["error"] == "AUTONOMY_TIER_DENIED"
    assert detail["trace_id"]


def test_worst_case_demoted_agent_cannot_retry_write_tool(client):
    demote(client)
    response = client.post("/v1/tools/apply_migration", headers={"X-AGENT-ID": AGENT}, json={"task_id": "retry"})
    assert response.status_code == 403
    assert response.json()["detail"]["required_tier"] == "T2"


def test_admin_reset_requires_independent_token(client):
    demote(client)
    denied = client.post("/v1/admin/reset", headers={"X-ADMIN-TOKEN": "wrong"})
    allowed = client.post("/v1/admin/reset", headers=ADMIN_HEADERS)
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["current_tier"] == "T3"
