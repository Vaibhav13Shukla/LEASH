param(
  [int]$BasePort = 18000
)

$ErrorActionPreference = "Stop"
$agent = "http://localhost:$BasePort"
$broker = "http://localhost:$($BasePort + 1)"
$token = $env:LEASH_WEBHOOK_TOKEN

if (-not $token) { throw "LEASH_WEBHOOK_TOKEN must be set." }

$healthy = Invoke-RestMethod -Method Post -Uri "$agent/api/demo/run-healthy"
Invoke-RestMethod -Method Post -Uri "$agent/api/demo/inject-migration-failure" | Out-Null
$failures = Invoke-RestMethod -Method Post -Uri "$agent/api/demo/run-failures?attempts=3"
$payload = @{ agent_id = "release-agent-01"; target_tier = "T1"; alert_id = "manual-integration-check"; reason = "migration_error_budget_exhausted" } | ConvertTo-Json
$demoted = Invoke-RestMethod -Method Post -Uri "$broker/webhooks/signoz/demote" -Headers @{ "X-LEASH-WEBHOOK-TOKEN" = $token } -ContentType "application/json" -Body $payload
$denial = Invoke-RestMethod -Method Post -Uri "$agent/api/demo/request-delete"

if ($demoted.current_tier -ne "T1") { throw "Expected T1 after demotion." }
if ($denial.outcome.status_code -ne 403) { throw "Expected broker to deny destructive action." }

[PSCustomObject]@{
  healthy_tools = $healthy.outcomes.Count
  failed_tools = $failures.outcomes.Count
  demoted_to = $demoted.current_tier
  denied_status = $denial.outcome.status_code
}
