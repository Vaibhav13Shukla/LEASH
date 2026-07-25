from services.common.contracts import TOOL_RISKS, TOOL_TIERS, Tier, tier_name


def test_dangerous_tool_requires_full_tier():
    assert TOOL_TIERS["delete_staging_table"] is Tier.T3
    assert TOOL_RISKS["delete_staging_table"] == "destructive"


def test_tier_names_remain_stable_for_telemetry_filters():
    assert [tier_name(tier) for tier in Tier] == ["T0", "T1", "T2", "T3"]
