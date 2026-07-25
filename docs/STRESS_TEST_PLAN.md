# LEASH Stress Test Plan

## Objective

Prove that LEASH fails closed: unreliable agents lose authority, while malformed, duplicated, delayed, or hostile alert traffic cannot grant it back.

## Steady state

- `release-agent-01` is `T3` before a fault.
- Read and migration tools are brokered and return truthful downstream outcomes.
- A destructive tool requires `T3`.
- Every enforcement decision produces a trace span and policy decision metric.

## Blast radius and abort criteria

All experiments run against disposable SQLite and in-memory demo resources. There are no cloud credentials, production databases, or live deployments.

Abort any manual experiment if a test points at a non-local hostname, if `POLICY_DB_PATH` does not resolve inside the repository data directory, or if the collector endpoint is not the intended demo SigNoz instance.

## Scenario matrix

| Class | Scenario | Expected LEASH behavior | Automated |
|---|---|---|---|
| Best | New agent begins a healthy release | `T3`; read and write are allowed | Yes |
| Average | Three migration failures reach alert threshold | SigNoz alert can demote to `T1` | Integration script |
| Worst | Alert is delivered twice | Second delivery is idempotent; policy version does not change | Yes |
| Worst | Stolen webhook sends `T3` after demotion | Rejected with 400; no re-promotion | Yes |
| Worst | Webhook token is wrong | Rejected with 401; policy is unchanged | Yes |
| Worst | Tier is malformed or out of range | Rejected with 422; policy is unchanged | Yes |
| Worst | Agent requests unknown tool | Rejected with 404; no downstream request | Yes |
| Worst | Demoted agent requests delete | Rejected with 403 and trace ID | Yes |
| Worst | Demoted agent retries write | Rejected with 403 | Yes |
| Worst | Reset endpoint has wrong admin token | Rejected with 401 | Yes |
| Recovery | Authorized demo reset | Restores `T3`, clears last alert fields | Yes |
| Dependency | Migration endpoint returns 502 | Outcome is `error`, not self-reported success | Live integration |
| Collector | OTLP collector is temporarily unavailable | App continues enforcing; exporter retries in background | Manual exercise |
| Alert delay | Alert arrives after retries finish | Next dangerous action is still blocked after demotion | Live demo |

## Commands

```powershell
# Unit, contract, and adversarial policy suite (19 tests)
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest -q

# Run LEASH locally on ports 18000-18003
.\scripts\run-local.ps1 -BasePort 18000

# Validate the complete app loop. This uses the same broker webhook that SigNoz uses.
$env:LEASH_WEBHOOK_TOKEN = "the-value-from-your-env-file"
.\scripts\integration-check.ps1 -BasePort 18000
```

## Live SigNoz game-day sequence

1. Start at `T3`, run a healthy release, and open its trace in SigNoz.
2. Inject the migration failure.
3. Run three failed migrations.
4. Confirm the dashboard and alert condition see the actual error spans.
5. Wait for the configured alert to fire and verify the broker receives its webhook.
6. Request destructive cleanup. Confirm HTTP 403 and open its denial trace.
7. Reset only after the recording is complete.

## Learning loop, not fake RL

LEASH does not add a reinforcement-learning model. That would be irrelevant and unsafe in a 24-hour reliability demo. Its feedback loop is operational: downstream outcome -> telemetry -> alert -> policy update -> constrained next action. The demonstrable feedback signal is the autonomy tier, not a claimed learned policy.
