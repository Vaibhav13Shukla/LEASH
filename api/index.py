from __future__ import annotations

import itertools
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import metrics, trace

from services.broker import events_api
from services.broker.policy_store import PolicyStore
from services.common.contracts import TOOL_RISKS, TOOL_TIERS, Tier, tier_name
from services.common.settings import ADMIN_TOKEN, POLICY_DB_PATH, WEBHOOK_TOKEN
from services.common.telemetry import instrument_app, meter, trace_id

# Initialize main unified FastAPI app for Vercel
app = FastAPI(title="LEASH — Autonomy Error Budget Gateway", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Instrument telemetry
instrument_app(app, "leash-unified")
tracer = trace.get_tracer("leash-unified")
broker_meter = meter("leash-broker")

# Initialize Policy Store
store = PolicyStore(POLICY_DB_PATH)
events_api.store = store
app.include_router(events_api.router)

# Metrics
tool_calls = broker_meter.create_counter("leash_tool_calls_total")
policy_decisions = broker_meter.create_counter("leash_policy_decisions_total")
webhook_calls = broker_meter.create_counter("leash_alert_webhooks_total")
agent_tasks = meter("agent-runner").create_counter("leash_agent_tasks_total")


def observe_agent_tier(_options):
    state = store.get("release-agent-01")
    return [metrics.Observation(int(state["current_tier"][1:]), {"agent_id": "release-agent-01"})]


broker_meter.create_observable_gauge(
    "leash_agent_tier",
    callbacks=[observe_agent_tier],
    description="Current enforced LEASH autonomy tier for the demo agent.",
)

# State variables
AGENT_ID = "release-agent-01"
task_counter = itertools.count(1)
migration_failure_enabled = False
staging_table_present = True


def task_id() -> str:
    return f"release-demo-{next(task_counter):03d}"


# Mount static web UI files if present
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
if WEB_DIR.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


# --- Health check ---
@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


# --- Static Frontend Serving ---
@app.get("/")
def control_room():
    if WEB_DIR.exists() and (WEB_DIR / "index.html").exists():
        return FileResponse(WEB_DIR / "index.html")
    return {"message": "LEASH API is live"}


# --- Downstream Service Endpoints (Migration & Resource) ---
@app.post("/demo/failure")
def set_failure(payload: dict) -> dict:
    global migration_failure_enabled
    migration_failure_enabled = bool(payload.get("enabled", False))
    return {"failure_enabled": migration_failure_enabled}


@app.post("/execute")
def execute_migration(payload: dict, x_agent_id: str = Header("release-agent-01")) -> dict:
    with tracer.start_as_current_span("leash.tool.execute") as span:
        span.set_attributes({"leash.agent.id": x_agent_id, "leash.tool.name": "apply_migration", "leash.tool.risk": "write"})
        if migration_failure_enabled:
            span.set_attribute("leash.tool.outcome", "error")
            tool_calls.add(1, {"tool_name": "apply_migration", "tool_risk": "write", "outcome": "error"})
            raise HTTPException(status_code=502, detail={"error": "MIGRATION_DEPENDENCY_UNAVAILABLE", "task_id": payload.get("task_id")})
        span.set_attribute("leash.tool.outcome", "success")
        tool_calls.add(1, {"tool_name": "apply_migration", "tool_risk": "write", "outcome": "success"})
        return {"status": "applied", "task_id": payload.get("task_id"), "migration": "20260725_add_audit_column"}


@app.post("/read_release_notes")
def read_release_notes(payload: dict, x_agent_id: str = Header("release-agent-01")) -> dict:
    with tracer.start_as_current_span("leash.tool.execute") as span:
        span.set_attributes({"leash.agent.id": x_agent_id, "leash.tool.name": "read_release_notes", "leash.tool.risk": "read", "leash.tool.outcome": "success"})
        tool_calls.add(1, {"tool_name": "read_release_notes", "tool_risk": "read", "outcome": "success"})
        return {"release": "2026.07.25", "notes": "Schema migration is reversible. Staging cleanup requires Tier 3."}


@app.post("/delete_staging_table")
def delete_staging_table(payload: dict, x_agent_id: str = Header("release-agent-01")) -> dict:
    global staging_table_present
    with tracer.start_as_current_span("leash.tool.execute") as span:
        staging_table_present = False
        span.set_attributes({"leash.agent.id": x_agent_id, "leash.tool.name": "delete_staging_table", "leash.tool.risk": "destructive", "leash.tool.outcome": "success"})
        tool_calls.add(1, {"tool_name": "delete_staging_table", "tool_risk": "destructive", "outcome": "success"})
        return {"status": "deleted", "resource": "staging_table", "task_id": payload.get("task_id")}


# --- LEASH Policy Broker Endpoints ---
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

        # Dispatch internal call to downstream tool implementation directly
        if tool_name == "read_release_notes":
            res = read_release_notes(task, x_agent_id)
            return {"tool": tool_name, "outcome": "success", "status_code": 200, "policy": store.get(x_agent_id), "result": res}
        elif tool_name == "apply_migration":
            try:
                res = execute_migration(task, x_agent_id)
                return {"tool": tool_name, "outcome": "success", "status_code": 200, "policy": store.get(x_agent_id), "result": res}
            except HTTPException as e:
                return {"tool": tool_name, "outcome": "error", "status_code": e.status_code, "policy": store.get(x_agent_id), "result": {"detail": e.detail}}
        elif tool_name == "delete_staging_table":
            res = delete_staging_table(task, x_agent_id)
            return {"tool": tool_name, "outcome": "success", "status_code": 200, "policy": store.get(x_agent_id), "result": res}
        else:
            raise HTTPException(status_code=404, detail="Tool not implemented")


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


# --- Demo Control Room Frontend API Endpoints ---
async def internal_broker_call(tool_name: str, current_task_id: str) -> dict:
    policy = store.get(AGENT_ID)
    current = Tier(int(policy["current_tier"][1:]))
    required = TOOL_TIERS[tool_name]
    if current < required:
        reason = policy["last_demote_reason"] or "Tool requires a higher autonomy tier"
        detail = {
            "error": "AUTONOMY_TIER_DENIED",
            "agent_id": AGENT_ID,
            "current_tier": tier_name(current),
            "required_tier": tier_name(required),
            "reason": reason,
            "trace_id": trace_id() or "policy-denial-trace-id",
        }
        policy_decisions.add(1, {"decision": "deny", "current_tier": tier_name(current), "required_tier": tier_name(required)})
        return {"tool": tool_name, "ok": False, "status_code": 403, "detail": detail}

    policy_decisions.add(1, {"decision": "allow", "current_tier": tier_name(current), "required_tier": tier_name(required)})
    if tool_name == "read_release_notes":
        res = read_release_notes({"task_id": current_task_id}, AGENT_ID)
        return {"tool": tool_name, "ok": True, "status_code": 200, "result": {"tool": tool_name, "outcome": "success", "status_code": 200, "policy": policy, "result": res}}
    elif tool_name == "apply_migration":
        try:
            res = execute_migration({"task_id": current_task_id}, AGENT_ID)
            return {"tool": tool_name, "ok": True, "status_code": 200, "result": {"tool": tool_name, "outcome": "success", "status_code": 200, "policy": policy, "result": res}}
        except HTTPException as e:
            return {"tool": tool_name, "ok": False, "status_code": e.status_code, "result": {"tool": tool_name, "outcome": "error", "status_code": e.status_code, "policy": policy, "result": {"detail": e.detail}}}
    elif tool_name == "delete_staging_table":
        res = delete_staging_table({"task_id": current_task_id}, AGENT_ID)
        return {"tool": tool_name, "ok": True, "status_code": 200, "result": {"tool": tool_name, "outcome": "success", "status_code": 200, "policy": policy, "result": res}}
    return {"tool": tool_name, "ok": False, "status_code": 404, "detail": "Unknown tool"}


@app.get("/api/status")
def status() -> dict:
    return store.get(AGENT_ID)


@app.get("/api/events")
def events(limit: int = 50) -> dict:
    return store.get_events(AGENT_ID, limit=limit)


@app.post("/api/demo/run-healthy")
async def run_healthy() -> dict:
    current_task_id = task_id()
    with tracer.start_as_current_span("leash.agent.task") as span:
        span.set_attributes({"leash.agent.id": AGENT_ID, "leash.task.id": current_task_id, "leash.task.type": "healthy_release"})
        outcomes = [
            await internal_broker_call("read_release_notes", current_task_id),
            await internal_broker_call("apply_migration", current_task_id),
        ]
        agent_tasks.add(1, {"task_type": "healthy_release", "outcome": "success" if all(item["ok"] for item in outcomes) else "error"})
        return {"task_id": current_task_id, "outcomes": outcomes}


@app.post("/api/demo/inject-migration-failure")
def inject_migration_failure() -> dict:
    return set_failure({"enabled": True})


@app.post("/api/demo/run-failures")
async def run_failures(attempts: int = 3) -> dict:
    if attempts < 1 or attempts > 5:
        raise HTTPException(status_code=400, detail="Attempts must be between 1 and 5")
    current_task_id = task_id()
    with tracer.start_as_current_span("leash.agent.task") as span:
        span.set_attributes({"leash.agent.id": AGENT_ID, "leash.task.id": current_task_id, "leash.task.type": "migration_retry"})
        outcomes = [await internal_broker_call("apply_migration", current_task_id) for _ in range(attempts)]
        agent_tasks.add(1, {"task_type": "migration_retry", "outcome": "error"})
        return {"task_id": current_task_id, "outcomes": outcomes}


@app.post("/api/demo/request-delete")
async def request_delete() -> dict:
    current_task_id = task_id()
    with tracer.start_as_current_span("leash.agent.task") as span:
        span.set_attributes({"leash.agent.id": AGENT_ID, "leash.task.id": current_task_id, "leash.task.type": "destructive_cleanup"})
        outcome = await internal_broker_call("delete_staging_table", current_task_id)
        agent_tasks.add(1, {"task_type": "destructive_cleanup", "outcome": "success" if outcome["ok"] else "denied"})
        return {"task_id": current_task_id, "outcome": outcome}


@app.post("/api/demo/simulate-alert")
async def simulate_alert() -> dict:
    return await demote_from_alert(
        {
            "agent_id": AGENT_ID,
            "target_tier": "T1",
            "alert_id": "simulated-signoz-alert",
            "reason": "migration_error_budget_exhausted",
        },
        x_leash_webhook_token=WEBHOOK_TOKEN,
    )


@app.post("/api/demo/reset")
def reset_demo() -> dict:
    global migration_failure_enabled, staging_table_present
    migration_failure_enabled = False
    staging_table_present = True
    return reset(agent_id=AGENT_ID, x_admin_token=ADMIN_TOKEN)
