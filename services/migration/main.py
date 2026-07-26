from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from opentelemetry import trace

from services.common.telemetry import instrument_app, meter

app = FastAPI(title="LEASH Migration Tool")
instrument_app(app, "migration-tool")
tracer = trace.get_tracer("migration-tool")
calls = meter("migration-tool").create_counter("leash_tool_calls_total")
failure_enabled = False


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "failure_enabled": failure_enabled}


@app.post("/demo/failure")
def set_failure(payload: dict) -> dict:
    global failure_enabled
    failure_enabled = payload.get("enabled", False)
    return {"failure_enabled": failure_enabled}


@app.post("/execute")
def execute(payload: dict, x_agent_id: str = Header(...)) -> dict:
    with tracer.start_as_current_span("leash.tool.execute") as span:
        span.set_attributes({"leash.agent.id": x_agent_id, "leash.tool.name": "apply_migration", "leash.tool.risk": "write"})
        if failure_enabled:
            span.set_attribute("leash.tool.outcome", "error")
            calls.add(1, {"tool_name": "apply_migration", "tool_risk": "write", "outcome": "error"})
            raise HTTPException(status_code=502, detail={"error": "MIGRATION_DEPENDENCY_UNAVAILABLE", "task_id": payload.get("task_id")})
        span.set_attribute("leash.tool.outcome", "success")
        calls.add(1, {"tool_name": "apply_migration", "tool_risk": "write", "outcome": "success"})
        return {"status": "applied", "task_id": payload.get("task_id"), "migration": "20260725_add_audit_column"}
