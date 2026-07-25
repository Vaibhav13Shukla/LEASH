from __future__ import annotations

import itertools
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace

from services.common.settings import ADMIN_TOKEN, BROKER_URL, MIGRATION_TOOL_URL, WEBHOOK_TOKEN
from services.common.telemetry import instrument_app, meter

AGENT_ID = "release-agent-01"
task_counter = itertools.count(1)

app = FastAPI(title="LEASH Demo Control Room")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
instrument_app(app, "agent-runner")
tracer = trace.get_tracer("agent-runner")
tasks = meter("agent-runner").create_counter("leash_agent_tasks_total")

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


def task_id() -> str:
    return f"release-demo-{next(task_counter):03d}"


async def broker_call(tool_name: str, current_task_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{BROKER_URL}/v1/tools/{tool_name}",
            headers={"X-Agent-Id": AGENT_ID},
            json={"task_id": current_task_id},
        )
    if response.status_code >= 400:
        return {"tool": tool_name, "ok": False, "status_code": response.status_code, "detail": response.json().get("detail", response.text)}
    return {"tool": tool_name, "ok": True, "status_code": response.status_code, "result": response.json()}


@app.get("/")
def control_room() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
async def status() -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{BROKER_URL}/v1/agents/{AGENT_ID}/policy")
    response.raise_for_status()
    return response.json()


@app.get("/api/events")
async def events(limit: int = 50) -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{BROKER_URL}/v1/agents/{AGENT_ID}/events", params={"limit": limit})
    response.raise_for_status()
    return response.json()


@app.post("/api/demo/run-healthy")
async def run_healthy() -> dict:
    current_task_id = task_id()
    with tracer.start_as_current_span("leash.agent.task") as span:
        span.set_attributes({"leash.agent.id": AGENT_ID, "leash.task.id": current_task_id, "leash.task.type": "healthy_release"})
        outcomes = [
            await broker_call("read_release_notes", current_task_id),
            await broker_call("apply_migration", current_task_id),
        ]
        tasks.add(1, {"task_type": "healthy_release", "outcome": "success" if all(item["ok"] for item in outcomes) else "error"})
        return {"task_id": current_task_id, "outcomes": outcomes}


@app.post("/api/demo/inject-migration-failure")
async def inject_migration_failure() -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(f"{MIGRATION_TOOL_URL}/demo/failure", json={"enabled": True})
    response.raise_for_status()
    return response.json()


@app.post("/api/demo/run-failures")
async def run_failures(attempts: int = 3) -> dict:
    if attempts < 1 or attempts > 5:
        raise HTTPException(status_code=400, detail="Attempts must be between 1 and 5")
    current_task_id = task_id()
    with tracer.start_as_current_span("leash.agent.task") as span:
        span.set_attributes({"leash.agent.id": AGENT_ID, "leash.task.id": current_task_id, "leash.task.type": "migration_retry"})
        outcomes = [await broker_call("apply_migration", current_task_id) for _ in range(attempts)]
        tasks.add(1, {"task_type": "migration_retry", "outcome": "error"})
        return {"task_id": current_task_id, "outcomes": outcomes}


@app.post("/api/demo/request-delete")
async def request_delete() -> dict:
    current_task_id = task_id()
    with tracer.start_as_current_span("leash.agent.task") as span:
        span.set_attributes({"leash.agent.id": AGENT_ID, "leash.task.id": current_task_id, "leash.task.type": "destructive_cleanup"})
        outcome = await broker_call("delete_staging_table", current_task_id)
        tasks.add(1, {"task_type": "destructive_cleanup", "outcome": "success" if outcome["ok"] else "denied"})
        return {"task_id": current_task_id, "outcome": outcome}


@app.post("/api/demo/simulate-alert")
async def simulate_alert() -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            f"{BROKER_URL}/webhooks/signoz/demote",
            headers={"X-LEASH-WEBHOOK-TOKEN": WEBHOOK_TOKEN},
            json={
                "agent_id": AGENT_ID,
                "target_tier": "T1",
                "alert_id": "simulated-signoz-alert",
                "reason": "migration_error_budget_exhausted",
            },
        )
    response.raise_for_status()
    return response.json()


@app.post("/api/demo/reset")
async def reset_demo() -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            f"{BROKER_URL}/v1/admin/reset",
            headers={"X-ADMIN-TOKEN": ADMIN_TOKEN},
            params={"agent_id": AGENT_ID},
        )
    response.raise_for_status()
    return response.json()
