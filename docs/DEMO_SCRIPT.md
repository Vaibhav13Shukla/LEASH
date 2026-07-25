# LEASH 150-Second Demo Presenter Script

**Target Duration:** 2 minutes 30 seconds (150 seconds)
**Track:** Track 01 — AI & Agent Observability
**Core Thesis:** *An AI agent must earn destructive permissions from observed reliability — and lose them when SigNoz observes downstream failure.*

---

## Timeline & Talking Points

```
[0:00 - 0:20] THE HOOK & SYSTEM SETUP
[0:20 - 0:45] ESTABLISHING TRUST (TIER T3)
[0:45 - 1:15] FAILURE ACCUMULATION & SIGNOZ TRACES
[1:15 - 1:45] SIGNOZ ALERT & AUTOMATIC DEMOTION
[1:45 - 2:15] THE DENIAL MOMENT (HTTP 403)
[2:15 - 2:30] WHY SIGNOZ & REPRODUCIBILITY CLOSE
```

---

### Step 1: The Hook & System Setup (0:00 - 0:20)

**Presenter Action:**
Open browser to `http://localhost:18000`. Show the LEASH Live Control Room.

**Talking Script:**
> "Most teams use observability to explain an agent failure *after* the damage is done. LEASH turns observability into a load-bearing control input. It continuously observes downstream tool reliability in **SigNoz** and dynamically calculates what an AI agent is allowed to do next."

---

### Step 2: Establish Trust — Healthy Release (0:20 - 0:45)

**Presenter Action:**
Click **"1. Run healthy release"** (or press key `1`). Point to the green status lights and the Tier T3 display.

**Talking Script:**
> "Our release agent starts at Tier **T3** — full authority. It reads release notes and applies a schema migration. Both tool calls pass through the LEASH broker and succeed, emitting OpenTelemetry spans directly to SigNoz. At T3, all permissions — read, write, and delete — are granted."

---

### Step 3: Inject Fault & Burn Error Budget (0:45 - 1:15)

**Presenter Action:**
Click **"2. Inject migration failure"** (key `2`), then click **"3. Run failed migrations"** (key `3`). Switch tab to SigNoz UI showing the live trace view and dashboard.

**Talking Script:**
> "Now a downstream database dependency breaks. We trigger three migration attempts. Notice the agent itself doesn't decide if its tool calls succeeded — the downstream services report truthful error spans. In SigNoz, we see three consecutive `apply_migration` spans return HTTP 502 with `leash.tool.outcome = error`."

---

### Step 4: SigNoz Alert Fires & Demotes Policy (1:15 - 1:45)

**Presenter Action:**
Show the SigNoz Alert rule *"LEASH - migration reliability breached"*. Point to the firing status and webhook delivery log. Switch back to the LEASH control room.

**Talking Script:**
> "SigNoz observes the error budget exhaustion in real-time. Its trace-based alert fires and POSTs a demotion payload to the LEASH broker webhook. Watch the control room: the agent's autonomy tier drops instantly from **T3** to **T1 — Read Only**."

---

### Step 5: The Arrest — Destructive Cleanup Denied (1:45 - 2:15)

**Presenter Action:**
Click **"4. Request destructive cleanup"** (key `4`). Point to the screen shake, red toast, and `HTTP 403 AUTONOMY_TIER_DENIED` in the decision ledger.

**Talking Script:**
> "Now the agent attempts a cleanup routine: `delete_staging_table`. Under traditional static prompt or IAM permissions, this would execute. But LEASH checks the brokered policy state in SQLite and returns a hard **HTTP 403 AUTONOMY_TIER_DENIED**. The denial includes the current tier and a SigNoz trace ID linking directly back to the root cause evidence."

---

### Step 6: Why SigNoz & Closing (2:15 - 2:30)

**Presenter Action:**
Click **"Simulate SigNoz alert"** or **"Reset to T3"** to demonstrate reproducibility.

**Talking Script:**
> "SigNoz wasn't just displaying a post-mortem chart — it supplied the aggregate evidence and alert trigger that constrained the agent before it could do harm. Autonomy is not a static prompt setting. **Autonomy is an error budget.** Thank you."

---

## Checklist for Demo Recording

- [ ] Clear browser cache or click **Reset to T3** before recording.
- [ ] SigNoz running on port `8080` / collector on `4317`.
- [ ] LEASH running on port `18000`.
- [ ] Mouse cursor visible during button clicks.
- [ ] Audio crisp and pace steady.
