# LEASH — Autonomy is Earned.

> **A circuit breaker for dangerous AI agent tools.**  
> When SigNoz observes downstream failures, LEASH automatically downgrades the agent before its next destructive action.

**Tagline**: *Trust is a metric, not a setting.*

---

<p align="center">
  <img src="docs/assets/leash-hero.png" width="760" alt="LEASH control room showing agent release-agent-01 demoted from T3 to T1 after SigNoz error budget breach with trace ID evidence" />
</p>

<p align="center">
  <em>Figure 1: The Arrest — The moment SigNoz detects downstream error budget depletion, fires a webhook, demotes the agent to T1 Read-Only, and intercepts destructive tool calls with HTTP 403.</em>
</p>

---

## 1. The Uncomfortable Insight

> **"Human-in-the-loop is a lie at scale. At production velocity, no one reviews hundreds of agent actions per hour. The only supervision that scales is the one SREs invented decades ago: error budgets and automated policy enforcement. LEASH makes autonomy itself an observable, continuously evaluated metric."**

Most teams use observability to explain what an AI agent did *after* production is broken:
> *"Why did `release-agent-01` drop the staging database at 3:00 AM?"*

LEASH turns observability into a load-bearing control plane input. It asks a more critical question *before* the next tool call:
> *"Based on what SigNoz just observed in real-time OpenTelemetry data, is this AI agent still allowed to perform a destructive operation?"*

**LEASH is not an AI safety policy written in English. It is an autonomy control loop enforced by telemetry.**

---

## 2. What LEASH Actually Does (The 30-Second Story)

1. **Trusted Start**: `release-agent-01` begins at **Tier T3 (Full Authority)**.
2. **Healthy Execution**: The agent reads release notes and applies a schema migration via the LEASH policy broker.
3. **Downstream Failure**: A downstream migration dependency is fault-injected and starts returning HTTP 502 errors.
4. **OTLP Telemetry Flow**: All four microservices emit OpenTelemetry spans, metrics, and logs directly to the SigNoz collector on port `:4317`.
5. **SigNoz Failure-Budget Alert**: SigNoz evaluates a 5-minute error budget query (`sum(leash_tool_calls_total{tool_name="apply_migration", outcome="error"}) >= 3`) and fires an alert.
6. **Automatic Demotion**: SigNoz POSTs an alert webhook to the LEASH broker (`/webhooks/signoz/demote`), instantly demoting the agent from **T3 → T1 (Read-Only)**.
7. **Destructive Tool Attempt**: The demoted agent attempts `delete_staging_table` (requires T3 authority).
8. **The Arrest**: LEASH intercepts the call and returns a hard policy denial containing exact trace-based proof:

```json
HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "error": "AUTONOMY_TIER_DENIED",
  "agent_id": "release-agent-01",
  "current_tier": "T1",
  "required_tier": "T3",
  "reason": "migration_error_budget_exhausted",
  "trace_id": "de4b97f1896593b813ca4cac9e280584"
}
```

This ensures complete auditability: the agent is not blocked by a prompt rule or LLM opinion, but by empirical reliability evidence recorded in SigNoz.

---

## 3. Control Loop Architecture

```mermaid
flowchart TB
    subgraph AGENT["  Agent Layer  "]
        AR["release-agent-01\nAgent Runner"]
    end

    subgraph BROKER["  Policy Broker Layer  "]
        B["LEASH Policy Broker\n/v1/tools/{tool_name}"]
        PS[("Policy Store\nSQLite — tier · version\ndemotion reason")]
        WH["Webhook Handler\n/webhooks/signoz/demote\nHMAC token auth"]
    end

    subgraph TOOLS["  Tool Layer (Downstream Services)  "]
        MT["Migration Tool\n/execute — fault-injectable"]
        RT["Resource Tool\n/read_release_notes\n/delete_staging_table"]
    end

    subgraph OTEL["  Observability Layer  "]
        OC["OTel Collector\nport 4317 gRPC"]
        SN["SigNoz Platform\nTraces · Metrics · Logs"]
        AL["Alert Engine\nleash_tool_calls_total\noutcome=error ≥ 3 in 5m"]
    end

    AR -->|"① Tool Request\nX-Agent-Id header"| B
    B <-->|"② Check + update tier"| PS
    B -->|"③ Brokered call\n(tier sufficient)"| MT
    B -->|"③ Brokered call\n(tier sufficient)"| RT
    B -.->|"✗ HTTP 403\nAUTONOMY_TIER_DENIED\n+ trace_id"| AR

    AR -->|"④ OTLP spans"| OC
    B -->|"④ policy.decision spans\nleash_agent_tier gauge"| OC
    MT -->|"④ tool.execute spans\nHTTP 502 errors"| OC
    RT -->|"④ tool.execute spans"| OC

    OC -->|"⑤ Telemetry ingest"| SN
    SN --> AL
    AL -->|"⑥ Alert fires\n5m window breach"| WH
    WH -->|"⑦ Demote T3 → T1\nwrite policy store"| PS
```

Seven numbered steps form one closed loop: agent calls the broker (①), broker checks policy (②), brokered tool call executes (③), every service emits OTLP telemetry (④), SigNoz ingests it (⑤), the alert engine evaluates the error budget query and fires (⑥), the webhook demotes the agent's tier before its next privileged call (⑦). The dashed line is the 403 denial path — the only moment the agent sees the enforcement.

---

## 5. Autonomy Trust Tiers

| Tier | Name | Permissions & Envelope | Reliability SLA |
| --- | --- | --- | --- |
| **T3** | Full Authority | Read, write, and disposable destructive cleanup (`delete_staging_table`) | ≥ 98% observed reliability |
| **T2** | Write Authority | Read and reversible writes (`apply_migration`) | ≥ 90% observed reliability |
| **T1** | Read-Only | Read-only inspection (`read_release_notes`) | Failure budget consumed / Demoted |
| **T0** | Quarantined | Zero tool execution permitted | Safety breach / Manual reset required |

---

## 6. Tech Stack

| Layer | Technology | Role |
|---|---|---|
| **Agent Runtime** | Python 3.12 + FastAPI | `release-agent-01` makes tool calls through the broker via HTTP |
| **Policy Broker** | FastAPI + SQLite | Evaluates tier vs. tool requirement; issues `HTTP 403` with trace evidence |
| **Policy Store** | SQLite (WAL mode) | Persists tier, version, demotion reason, and alert ID per agent |
| **Tool Services** | FastAPI ×2 | `migration-tool` and `resource-tool` — fault-injectable downstream services |
| **Instrumentation** | OpenTelemetry Python SDK | Traces, metrics, and structured logs on every policy decision and tool call |
| **Telemetry Backend** | SigNoz (self-hosted) | Ingests OTLP on `:4317`; hosts dashboards, alert rules, and webhook delivery |
| **Alert Transport** | SigNoz Webhook → HMAC-auth endpoint | SigNoz fires alert; broker demotes agent tier in < 10 s |
| **Fail Behavior** | Fail-open (by design) | If SigNoz is unreachable, agent retains its last known tier — no false lockouts |
| **Deployment (local)** | Foundry (`casting.yaml`) | Reproducible SigNoz environment; `casting.yaml.lock` committed for judges |
| **Deployment (cloud)** | Vercel Serverless Python | Unified ASGI entrypoint; live at [leash-beta.vercel.app](https://leash-beta.vercel.app) |
| **Test Suite** | pytest (20 tests) | Happy path, fault injection, demotion, 403 denial, and admin reset |
| **Frontend** | Vanilla JS + CSS | Instrument-panel UI — Fraunces + Inter + JetBrains Mono |

---

## 6. Why This Is a SigNoz Project

SigNoz is not a dashboard added after the product. Its traces, metrics, logs, query-backed alerts, and MCP integration are the evidence and actuator in LEASH's permission control loop.

### What SigNoz Actually Observes

| Signal | Example / Query | Why it matters |
| --- | --- | --- |
| **Distributed Trace** | `leash.policy.decision` & `leash.tool.execute` | Full execution waterfall and trace ID context before/after demotion |
| **Gauge Metric** | `leash_agent_tier` | Real-time gauge of active autonomy tier ($3 = \text{T3}, 1 = \text{T1}$) |
| **Counter Metric** | `leash_tool_calls_total` | Tracks tool outcomes (`success` vs `error`) and risk levels (`read`, `write`, `destructive`) |
| **Counter Metric** | `leash_policy_decisions_total` | Counts policy decisions (`allow` vs `deny`) across agent runs |
| **OTLP Structured Log** | `policy_decision deny` | Emits structured log payload carrying trace ID and failure reason |
| **SigNoz Alert** | `sum(leash_tool_calls_total{tool_name="apply_migration", outcome="error"}) >= 3` | Converts 5-minute sliding window error budget breach into a control signal |
| **Webhook Actuator** | `POST http://<HOST_GATEWAY>:18001/webhooks/signoz/demote` | Actuates policy demotion directly from SigNoz alert engine |
| **SigNoz MCP** | `signoz-mcp-server` integration | Enables coding agents to query live trace evidence during incident triage |

### Why a Generic LLM Wrapper Cannot Do This

A prompt can ask an agent to "be careful." An LLM guardrail can filter words in a prompt. **Neither can measure real downstream service behavior.**

A generic LLM wrapper cannot:
- Track downstream microservice HTTP 502 error rates across tool calls,
- Correlate agent actions with backend database failure spans,
- Evaluate a 5-minute sliding window error budget,
- Fire a query-backed alert from live telemetry,
- Or dynamically revoke tool execution privileges before the next action.

That requires OpenTelemetry signals and SigNoz acting directly inside the permission control loop.

---

## 7. The Control Room UI (Instrument Panel Aesthetic)

The LEASH Control Room is built around a **flight instrument panel printed on fine paper** design language (`DESIGN.md`):

<p align="center">
  <img src="docs/assets/leash-control-room.png" width="760" alt="LEASH Control Room UI showing Fraunces typography, 270 degree Error Budget Gauge, active Trust Tier badge, and live decision ledger" />
</p>

- **Typography**: Fraunces for editorial headlines, Inter for crisp UI controls, and JetBrains Mono for telemetry metadata.
- **Color Palette**: Warm paper background (`#FBF9F5`), iron ink text (`#1A1917`), and muted signal accents (brass, cinnabar, sage).
- **Error Budget Gauge**: A 270-degree SVG dial reflecting real-time budget state ($100\% \rightarrow 0\%$).
- **Restrained Motion**: On policy denial, the interface applies a precise 120ms horizontal micro-shake and drops an inline crimson alert banner carrying monospace trace evidence.

<p align="center">
  <img src="docs/assets/leash-ledger.png" width="760" alt="Broker Decision Ledger showing the complete demo narrative: ALLOWED healthy release, FAILED 3 downstream HTTP 502 migrations, REVOKED SigNoz alert demotion T3 to T1, DENIED destructive cleanup with real trace ID 97ad9ee7c6" />
</p>

<p align="center">
  <em>Figure 2: The Broker Decision Ledger — one view contains the complete enforcement story. Every row is a real policy decision backed by OTLP telemetry. The DENIED row carries trace ID <code>97ad9ee7c6…</code> — paste it into SigNoz to see the exact failure spans that caused it.</em>
</p>

---


## 8. Quick Start & Reproducibility

### 1. Run the SigNoz Stack (Foundry Deployment)

SigNoz is deployed via **Foundry** (listening on OTLP gRPC port `4317` and Web UI on port `8080`).

```bash
# Install foundryctl (Linux / WSL 2)
export PATH="$HOME/.local/bin:$PATH"

# Cast SigNoz deployment specification
foundryctl cast -f casting.yaml
```

> **Judges**: The repository includes the committed `casting.yaml.lock` file. Running `foundryctl cast -f casting.yaml` reproduces the exact SigNoz environment used during development.

### 2. Run LEASH Microservices

#### Linux / WSL 2:
```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/serve.py
```

#### Windows PowerShell:
```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\run-local.ps1 -BasePort 18000
```

Open [http://localhost:18000](http://localhost:18000) (or live at [https://leash-beta.vercel.app](https://leash-beta.vercel.app)) to access the Control Room UI. Keyboard keys `1–4` execute the live demo sequence.

---

## 9. Verification & Automated Test Suite

Run the full unit and contract test suite:

```bash
# Run pytest suite (20/20 test cases)
python3 -m pytest -v

# Run automated integration script
./scripts/integration-check.ps1 -BasePort 18000
```

The test suite validates:
- T3 happy path release execution,
- Migration fault injection and HTTP 502 error span generation,
- SigNoz demote webhook authentication token (`X-LEASH-WEBHOOK-TOKEN`) and tier demotion (T3 → T1),
- Hard `HTTP 403 AUTONOMY_TIER_DENIED` on destructive tool calls at T1,
- Admin policy reset back to T3.

---

## 10. Repository Guide

- [docs/LEASH_SPEC.md](docs/LEASH_SPEC.md) — Product and technical specification
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System architecture and telemetry contracts
- [docs/SIGNOZ_SETUP.md](docs/SIGNOZ_SETUP.md) — SigNoz dashboard, metric panels, and alert configuration
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — 150-second video demo presenter script
- [DESIGN.md](DESIGN.md) — Instrument panel design system

---

## 11. Demo Video & Article

- **Video Demo**: [Watch the 3-Minute Video Demo on YouTube](https://youtube.com)
- **Technical Article**: [Read the Full Technical Write-up on Dev.to](https://dev.to)

---

## 12. Track & Hackathon Submission

- **Hackathon**: Agents of SigNoz
- **Track**: Track 1: AI & Agent Observability
- **Core Thesis**: *Autonomy is an Error Budget.*

---

## 13. AI Disclosure

AI assistance was used for implementation, testing, documentation, and visual design. Declared in accordance with hackathon submission guidelines.
