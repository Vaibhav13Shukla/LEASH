from __future__ import annotations

from enum import IntEnum


class Tier(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3


TOOL_TIERS: dict[str, Tier] = {
    "read_release_notes": Tier.T1,
    "apply_migration": Tier.T2,
    "delete_staging_table": Tier.T3,
}

TOOL_RISKS = {
    "read_release_notes": "read",
    "apply_migration": "write",
    "delete_staging_table": "destructive",
}


def tier_name(tier: Tier | int) -> str:
    return f"T{int(tier)}"
