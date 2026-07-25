from fastapi.testclient import TestClient

from services.broker import main as broker
from services.broker.policy_store import PolicyStore


def test_alert_webhook_can_demote_but_never_promote(tmp_path):
    broker.store = PolicyStore(str(tmp_path / "broker.db"))
    client = TestClient(broker.app)
    headers = {"X-LEASH-WEBHOOK-TOKEN": "local-demo-webhook-token"}

    demotion = client.post(
        "/webhooks/signoz/demote",
        headers=headers,
        json={"agent_id": "release-agent-01", "target_tier": "T1", "alert_id": "alert-1", "reason": "failed_tools"},
    )
    promotion = client.post(
        "/webhooks/signoz/demote",
        headers=headers,
        json={"agent_id": "release-agent-01", "target_tier": "T3", "alert_id": "attacker", "reason": "promote"},
    )

    assert demotion.status_code == 200
    assert demotion.json()["current_tier"] == "T1"
    assert promotion.status_code == 400
