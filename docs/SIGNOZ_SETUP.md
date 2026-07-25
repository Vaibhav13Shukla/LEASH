# SigNoz Dashboard & Alert Setup Guide for LEASH

This guide provides step-by-step instructions to configure SigNoz for the LEASH demonstration.

---

## 1. Prerequisites & Installation

LEASH uses SigNoz self-hosted via **Foundry** (or any SigNoz instance listening on OTLP gRPC port `4317` and web UI on port `8080`).

### Starting SigNoz via Foundry (WSL 2 / Linux with Docker Engine)

```bash
curl -fsSL https://signoz.io/foundry.sh | bash
cd "/path/to/Agents of SigNoz"
foundryctl cast -f casting.yaml
```

This starts SigNoz containers and generates `casting.yaml.lock`.

---

## 2. Dashboard Setup: "LEASH - Autonomy Is Earned"

1. Open SigNoz UI (`http://localhost:8080`).
2. Navigate to **Dashboards** → **+ New Dashboard**.
3. Name the dashboard: `LEASH - Autonomy Is Earned`.
4. Create the following 6 panels:

### Panel 1: Current Autonomy Tier
- **Panel Type:** Value Widget
- **Query Type:** Metrics
- **Metric:** `leash_agent_tier`
- **Aggregation:** `last`
- **Description:** Enforced tier ($3 = \text{T3}, 1 = \text{T1}$)

### Panel 2: Migration Error Budget (Last 15m)
- **Panel Type:** Time Series / Gauge
- **Query Type:** Formula / Metrics
- **Query A:** `sum(rate(leash_tool_calls_total{tool_name="apply_migration", outcome="error"}[5m]))`
- **Query B:** `sum(rate(leash_tool_calls_total{tool_name="apply_migration"}[5m]))`
- **Formula:** `(A / B) * 100`
- **Unit:** Percent (%)

### Panel 3: Tool Calls by Outcome & Risk
- **Panel Type:** Bar / Time Series
- **Query Type:** Metrics
- **Metric:** `leash_tool_calls_total`
- **Group By:** `tool_name`, `outcome`, `tool_risk`

### Panel 4: Denied Dangerous Actions
- **Panel Type:** Value Widget / Counter
- **Query Type:** Metrics
- **Metric:** `leash_policy_decisions_total{decision="deny", required_tier="T3"}`
- **Aggregation:** `sum`

### Panel 5: Alert Webhook Delivery
- **Panel Type:** Time Series / Table
- **Query Type:** Metrics
- **Metric:** `leash_alert_webhooks_total`
- **Group By:** `outcome`

### Panel 6: Agent Task Trace Explorer
- **Panel Type:** Trace Table
- **Filter:** `serviceName = agent-runner AND name = leash.agent.task`
- **Columns:** `Timestamp`, `leash.task.id`, `leash.task.type`, `Duration`, `StatusCode`

---

## 3. Alert Rule Setup: "LEASH - migration reliability breached"

1. Navigate to **Alerts** → **+ New Alert Rule**.
2. Rule Name: `LEASH - migration reliability breached`.
3. Rule Type: **Traces / Metrics Alert**.

### Condition Configuration

```text
Target: Metric / Traces
Query:
  count(leash.tool.execute) where:
    leash.tool.name = "apply_migration" AND
    leash.tool.outcome = "error"
Evaluation Window: 5 minutes
Threshold: >= 3
```

### Notification / Webhook Action

```text
Channel Type: Webhook
URL: http://localhost:18001/webhooks/signoz/demote
  (Inside Docker Compose network: http://leash-broker:8000/webhooks/signoz/demote)

Headers:
  X-LEASH-WEBHOOK-TOKEN: <your LEASH_WEBHOOK_TOKEN from .env>
  Content-Type: application/json

Payload:
{
  "agent_id": "release-agent-01",
  "target_tier": "T1",
  "reason": "migration_error_budget_exhausted"
}
```

---

## 4. Verifying the Control Loop in SigNoz

1. In LEASH Control Room, click **"1. Run healthy release"**. Look at SigNoz Trace Explorer: search `serviceName = leash-broker`. Observe `leash.policy.decision` span with `leash.decision = allow`.
2. Click **"2. Inject failure"** and **"3. Run failed migrations"**.
3. In SigNoz, view traces for `serviceName = migration-tool`. Observe 3 spans with `leash.tool.outcome = error` and HTTP 502.
4. Watch the SigNoz Alert Rule switch to **Firing**.
5. Observe the Webhook delivery log confirming HTTP 200 from `/webhooks/signoz/demote`.
6. In LEASH Control Room, click **"4. Request destructive cleanup"**.
7. In SigNoz Trace Explorer, search for `leash.decision = deny`. Click the trace to inspect `current_tier = T1`, `required_tier = T3`, and the associated trace ID.
