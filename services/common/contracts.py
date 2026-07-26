from __future__ import annotations

from enum import IntEnum


class Tier(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3


# Single source of truth: (required_tier, risk_label) per tool.
# No parallel dicts to drift.
TOOLS: dict[str, tuple["Tier", str]] = {
    "read_release_notes":  (Tier.T1, "read"),
    "apply_migration":     (Tier.T2, "write"),
    "delete_staging_table": (Tier.T3, "destructive"),
}

# Convenience views kept for backwards-compat with callers.
TOOL_TIERS: dict[str, Tier] = {k: v[0] for k, v in TOOLS.items()}
TOOL_RISKS: dict[str, str]  = {k: v[1] for k, v in TOOLS.items()}

AGENT_ID = "release-agent-01"  # shared constant — avoid magic string duplication


def tier_name(tier: "Tier | int") -> str:
    return f"T{int(tier)}"
