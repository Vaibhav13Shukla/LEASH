from __future__ import annotations

import os

WEBHOOK_TOKEN = os.getenv("LEASH_WEBHOOK_TOKEN", "local-demo-webhook-token")
ADMIN_TOKEN    = os.getenv("LEASH_ADMIN_TOKEN",   "local-demo-admin-token")
BROKER_URL          = os.getenv("BROKER_URL",          "http://localhost:8001")
MIGRATION_TOOL_URL  = os.getenv("MIGRATION_TOOL_URL",  "http://localhost:8002")
RESOURCE_TOOL_URL   = os.getenv("RESOURCE_TOOL_URL",   "http://localhost:8003")
_default_db = "/tmp/leash.db" if os.getenv("VERCEL") or not os.access(".", os.W_OK) else "./data/leash.db"
POLICY_DB_PATH = os.getenv("POLICY_DB_PATH", _default_db)
