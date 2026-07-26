from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import metrics, trace

from services.broker import events_api
from services.broker.policy_store import PolicyStore
from services.common.contracts import TOOL_RISKS, TOOL_TIERS, Tier, tier_name
from services.common.settings import ADMIN_TOKEN, MIGRATION_TOOL_URL, POLICY_DB_PATH, RESOURCE_TOOL_URL, WEBHOOK_TOKEN
from services.common.telemetry import instrument_app, meter, trace_id

app = FastAPI(title="LEASH Policy Broker", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
instrument_app(app, "leash-broker")
tracer = trace.get_tracer("leash-broker")
store = PolicyStore(POLICY_DB_PATH)
tool_calls = meter("leash-broker").create_counter("leash_tool_calls_total")
policy_decisions = meter("leash-broker").create_counter("leash_policy_decisions_total")
webhook_calls = meter("leash-broker").create_counter("leash_alert_webhooks_total")

# Mount events API and share the store instance
events_api.store = store
app.include_router(events_api.router)


def observe_agent_tier(_options):
    state = store.get("release-agent-01")
    return [metrics.Observation(int(state["current_tier"][1:]), {"agent_id": "release-agent-01"})]


meter("leash-broker").create_observable_gauge(
    "leash_agent_tier",
    callbacks=[observe_agent_tier],
    description="Current enforced LEASH autonomy tier for the demo agent.",
)

TOOL_URLS = {
    "read_release_notes": f"{RESOURCE_TOOL_URL}/read_release_notes",
    "apply_migration": f"{MIGRATION_TOOL_URL}/execute",
    "delete_staging_table": f"{RESOURCE_TOOL_URL}/delete_staging_table",
}


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/v1/agents/{agent_id}/policy")
def get_policy(agent_id: str) -> dict:
    return store.get(agent_id)


@app.post("/v1/tools/{tool_name}")
async def execute_tool(tool_name: str, request: Request, x_agent_id: str = Header(...)) -> dict:
    if tool_name not in TOOL_TIERS:
        raise HTTPException(status_code=404, detail="Unknown tool")
    task = await request.json()
    policy = store.get(x_agent_id)
    current = Tier(int(policy["current_tier"][1:]))
    required = TOOL_TIERS[tool_name]
    # Fail-open: if SigNoz / webhook is unreachable the agent retains its last
    # persisted tier rather than being locked out by an observability outage.

    with tracer.start_as_current_span("leash.policy.decision") as span:
        span.set_attributes(
            {
                "leash.agent.id": x_agent_id,
                "leash.tool.name": tool_name,
                "leash.tool.risk": TOOL_RISKS[tool_name],
                "leash.current_tier": tier_name(current),
                "leash.required_tier": tier_name(required),
                "leash.policy_version": policy["policy_version"],
            }
        )
        if current < required:
            span.set_attribute("leash.decision", "deny")
            policy_decisions.add(1, {"decision": "deny", "current_tier": tier_name(current), "required_tier": tier_name(required)})
            logging.warning("policy_decision deny tool=%s agent=%s trace_id=%s", tool_name, x_agent_id, trace_id())
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "AUTONOMY_TIER_DENIED",
                    "agent_id": x_agent_id,
                    "current_tier": tier_name(current),
                    "required_tier": tier_name(required),
                    "reason": policy["last_demote_reason"] or "Tool requires a higher autonomy tier",
                    "trace_id": trace_id(),
                },
            )

        span.set_attribute("leash.decision", "allow")
        policy_decisions.add(1, {"decision": "allow", "current_tier": tier_name(current), "required_tier": tier_name(required)})
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(TOOL_URLS[tool_name], json=task, headers={"X-Agent-Id": x_agent_id})
        outcome = "success" if response.is_success else "error"
        span.set_attribute("leash.tool.outcome", outcome)
        span.set_attribute("http.response.status_code", response.status_code)
        tool_calls.add(1, {"tool_name": tool_name, "tool_risk": TOOL_RISKS[tool_name], "outcome": outcome})
        return {"tool": tool_name, "outcome": outcome, "status_code": response.status_code, "policy": store.get(x_agent_id), "result": response.json()}


@app.post("/webhooks/signoz/demote")
async def demote_from_alert(payload: dict, x_leash_webhook_token: str = Header(...)) -> dict:
    if x_leash_webhook_token != WEBHOOK_TOKEN:
        webhook_calls.add(1, {"outcome": "unauthorized"})
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    agent_id = payload.get("agent_id", "release-agent-01")
    try:
        target_tier = Tier(int(str(payload.get("target_tier", "T1")).replace("T", "")))
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="target_tier must be T0, T1, T2, or T3") from error
    alert_id = payload.get("alert_id", "manual-demo-alert")
    reason = payload.get("reason", "migration_error_budget_exhausted")
    with tracer.start_as_current_span("leash.autonomy.demote") as span:
        current = Tier(int(store.get(agent_id)["current_tier"][1:]))
        if target_tier > current:
            webhook_calls.add(1, {"outcome": "invalid_promotion"})
            raise HTTPException(status_code=400, detail="Alert webhooks may only reduce autonomy")
        state = store.demote(agent_id, target_tier, alert_id, reason)
        span.set_attributes({"leash.agent.id": agent_id, "leash.to_tier": state["current_tier"], "leash.alert.id": alert_id, "leash.demote.reason": reason})
        webhook_calls.add(1, {"outcome": "success"})
        return state


@app.post("/v1/admin/reset")
def reset(agent_id: str = "release-agent-01", x_admin_token: str = Header(...)) -> dict:
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return store.reset(agent_id)
