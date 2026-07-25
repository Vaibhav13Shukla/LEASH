from __future__ import annotations

from fastapi import APIRouter
from services.broker.policy_store import PolicyStore

router = APIRouter()

# The store instance is injected by main.py after mount.
store: PolicyStore | None = None


@router.get("/v1/agents/{agent_id}/events")
def get_events(agent_id: str, limit: int = 50) -> dict:
    """Return the policy event audit trail for an agent."""
    if store is None:
        return {"agent_id": agent_id, "events": []}
    return {"agent_id": agent_id, "events": store.get_events(agent_id, limit)}
