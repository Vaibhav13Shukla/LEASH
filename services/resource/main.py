from __future__ import annotations

from fastapi import FastAPI, Header
from opentelemetry import trace

from services.common.telemetry import instrument_app, meter

app = FastAPI(title="LEASH Resource Tool")
instrument_app(app, "resource-tool")
tracer = trace.get_tracer("resource-tool")
calls = meter("resource-tool").create_counter("leash_tool_calls_total")
staging_table_present = True


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "staging_table_present": staging_table_present}


@app.post("/read_release_notes")
def read_release_notes(payload: dict, x_agent_id: str = Header(...)) -> dict:
    with tracer.start_as_current_span("leash.tool.execute") as span:
        span.set_attributes({"leash.agent.id": x_agent_id, "leash.tool.name": "read_release_notes", "leash.tool.risk": "read", "leash.tool.outcome": "success"})
        calls.add(1, {"tool_name": "read_release_notes", "tool_risk": "read", "outcome": "success"})
        return {"release": "2026.07.25", "notes": "Schema migration is reversible. Staging cleanup requires Tier 3."}


@app.post("/delete_staging_table")
def delete_staging_table(payload: dict, x_agent_id: str = Header(...)) -> dict:
    global staging_table_present
    with tracer.start_as_current_span("leash.tool.execute") as span:
        staging_table_present = False
        span.set_attributes({"leash.agent.id": x_agent_id, "leash.tool.name": "delete_staging_table", "leash.tool.risk": "destructive", "leash.tool.outcome": "success"})
        calls.add(1, {"tool_name": "delete_staging_table", "tool_risk": "destructive", "outcome": "success"})
        return {"status": "deleted", "resource": "staging_table", "task_id": payload.get("task_id")}
