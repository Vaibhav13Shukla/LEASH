from __future__ import annotations

import os


def env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


WEBHOOK_TOKEN = env("LEASH_WEBHOOK_TOKEN", "local-demo-webhook-token")
ADMIN_TOKEN = env("LEASH_ADMIN_TOKEN", "local-demo-admin-token")
BROKER_URL = env("BROKER_URL", "http://localhost:8001")
MIGRATION_TOOL_URL = env("MIGRATION_TOOL_URL", "http://localhost:8002")
RESOURCE_TOOL_URL = env("RESOURCE_TOOL_URL", "http://localhost:8003")
POLICY_DB_PATH = env("POLICY_DB_PATH", "./data/leash.db")
