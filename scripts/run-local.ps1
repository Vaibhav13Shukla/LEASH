param(
  [int]$BasePort = 18000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".env")) {
  Write-Error "Create .env from .env.example before running LEASH."
}

Get-Content .env | Where-Object { $_ -match "^\s*[^#].*=" } | ForEach-Object {
  $name, $value = $_ -split "=", 2
  Set-Item -Path "Env:$name" -Value $value
}

$env:PYTHONPATH = "."
$env:BROKER_URL = "http://localhost:$($BasePort + 1)"
$env:MIGRATION_TOOL_URL = "http://localhost:$($BasePort + 2)"
$env:RESOURCE_TOOL_URL = "http://localhost:$($BasePort + 3)"
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
  Write-Error "Create .venv and install requirements first."
}

$services = @(
  @{ Name = "leash-broker"; Module = "services.broker.main:app"; Port = $BasePort + 1 },
  @{ Name = "migration-tool"; Module = "services.migration.main:app"; Port = $BasePort + 2 },
  @{ Name = "resource-tool"; Module = "services.resource.main:app"; Port = $BasePort + 3 },
  @{ Name = "agent-runner"; Module = "services.agent_runner.main:app"; Port = $BasePort }
)

foreach ($service in $services) {
  Start-Process -FilePath $py -ArgumentList "-m", "uvicorn", $service.Module, "--host", "0.0.0.0", "--port", $service.Port -WorkingDirectory $root -WindowStyle Hidden
  Write-Host "Started $($service.Name) on port $($service.Port)"
}

Write-Host "LEASH control room: http://localhost:$BasePort"
Write-Host "SigNoz should receive OTLP on $env:OTEL_EXPORTER_OTLP_ENDPOINT"
