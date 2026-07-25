from __future__ import annotations

import os
import subprocess
import sys
import time

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, root)

base_port = 18000
env = os.environ.copy()
env["PYTHONPATH"] = root
env["BROKER_URL"] = f"http://localhost:{base_port + 1}"
env["MIGRATION_TOOL_URL"] = f"http://localhost:{base_port + 2}"
env["RESOURCE_TOOL_URL"] = f"http://localhost:{base_port + 3}"
env["LEASH_WEBHOOK_TOKEN"] = env.get("LEASH_WEBHOOK_TOKEN", "local-leash-webhook-2026")
env["LEASH_ADMIN_TOKEN"] = env.get("LEASH_ADMIN_TOKEN", "local-leash-admin-2026")

python_exe = sys.executable

services = [
    ("leash-broker", "services.broker.main:app", base_port + 1),
    ("migration-tool", "services.migration.main:app", base_port + 2),
    ("resource-tool", "services.resource.main:app", base_port + 3),
    ("agent-runner", "services.agent_runner.main:app", base_port),
]

processes = []

print("[LEASH] Starting LEASH microservices...")
for name, module, port in services:
    cmd = [python_exe, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port)]
    proc = subprocess.Popen(cmd, cwd=root, env=env)
    processes.append((name, proc))
    print(f"  - Started {name} on http://localhost:{port}")

print(f"\n[LEASH] Control Room Live: http://localhost:{base_port}\n")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nStopping services...")
    for name, proc in processes:
        proc.terminate()
    sys.exit(0)
