from services.broker.policy_store import PolicyStore
from services.common.contracts import Tier


def test_new_agent_starts_with_full_demo_authority(tmp_path):
    store = PolicyStore(str(tmp_path / "leash.db"))

    state = store.get("release-agent-01")

    assert state["current_tier"] == "T3"
    assert state["policy_version"] == 1


def test_alert_demotion_persists_reason_and_version(tmp_path):
    store = PolicyStore(str(tmp_path / "leash.db"))

    state = store.demote("release-agent-01", Tier.T1, "alert-123", "migration_error_budget_exhausted")

    assert state["current_tier"] == "T1"
    assert state["policy_version"] == 2
    assert state["last_alert_id"] == "alert-123"
    assert state["last_demote_reason"] == "migration_error_budget_exhausted"


def test_manual_reset_restores_only_demo_full_authority(tmp_path):
    store = PolicyStore(str(tmp_path / "leash.db"))
    store.demote("release-agent-01", Tier.T1, "alert-123", "migration_error_budget_exhausted")

    state = store.reset("release-agent-01")

    assert state["current_tier"] == "T3"
    assert state["last_alert_id"] is None
