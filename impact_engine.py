"""
Schema-Change Impact Simulator — Core Engine

Provides mocked lineage data, risk scoring, and English summary generation.
Designed with a pluggable interface so `get_downstream_assets()` can later
call Atlan's APIs / MDLH GOLD layer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

CHANGE_TYPES = [
    "Drop column",
    "Rename column",
    "Change data type",
    "Deprecate table",
]

ASSET_TYPES = ["Dashboard", "Report", "ML Model", "dbt Model", "View", "Scheduled Query"]

RISK_WEIGHTS = {
    "Drop column": 1.0,
    "Rename column": 0.7,
    "Change data type": 0.6,
    "Deprecate table": 1.0,
}

CRITICALITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.75,
    "medium": 0.5,
    "low": 0.25,
}


@dataclass
class DownstreamAsset:
    name: str
    asset_type: str
    owner: str
    criticality: str  # critical | high | medium | low
    direct: bool = True  # direct vs transitive dependency
    last_queried_days_ago: int = 1
    description: str = ""


@dataclass
class ImpactResult:
    source_asset: str
    change_type: str
    downstream_assets: list[DownstreamAsset] = field(default_factory=list)
    risk_score: float = 0.0
    risk_level: str = "Unknown"
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mocked lineage data
# ---------------------------------------------------------------------------

_MOCK_LINEAGE: dict[str, list[DownstreamAsset]] = {
    "default/snowflake/123/ANALYTICS/FCT_ORDERS/total_amount": [
        DownstreamAsset(
            name="Revenue Dashboard",
            asset_type="Dashboard",
            owner="finance-analytics@acme.com",
            criticality="critical",
            direct=True,
            last_queried_days_ago=0,
            description="Executive revenue dashboard refreshed hourly",
        ),
        DownstreamAsset(
            name="Weekly GMV Report",
            asset_type="Report",
            owner="biz-ops@acme.com",
            criticality="high",
            direct=True,
            last_queried_days_ago=1,
            description="Board-level gross merchandise value report",
        ),
        DownstreamAsset(
            name="Churn Prediction Model",
            asset_type="ML Model",
            owner="ml-team@acme.com",
            criticality="high",
            direct=False,
            last_queried_days_ago=3,
            description="Uses order totals as a feature for churn scoring",
        ),
        DownstreamAsset(
            name="dbt_orders_enriched",
            asset_type="dbt Model",
            owner="data-eng@acme.com",
            criticality="medium",
            direct=True,
            last_queried_days_ago=0,
            description="Intermediate dbt model joining orders with customer data",
        ),
        DownstreamAsset(
            name="v_customer_lifetime_value",
            asset_type="View",
            owner="data-eng@acme.com",
            criticality="medium",
            direct=False,
            last_queried_days_ago=7,
            description="Snowflake view aggregating LTV per customer",
        ),
    ],
    "default/snowflake/123/ANALYTICS/DIM_CUSTOMERS/email": [
        DownstreamAsset(
            name="Marketing Campaign Scheduler",
            asset_type="Scheduled Query",
            owner="growth@acme.com",
            criticality="critical",
            direct=True,
            last_queried_days_ago=0,
            description="Sends daily email campaigns based on customer segments",
        ),
        DownstreamAsset(
            name="Customer 360 Dashboard",
            asset_type="Dashboard",
            owner="cx-team@acme.com",
            criticality="high",
            direct=True,
            last_queried_days_ago=1,
            description="Support team's single-customer view",
        ),
        DownstreamAsset(
            name="PII Compliance Report",
            asset_type="Report",
            owner="legal@acme.com",
            criticality="critical",
            direct=False,
            last_queried_days_ago=14,
            description="Quarterly PII audit report for GDPR compliance",
        ),
    ],
    "default/snowflake/123/ANALYTICS/FCT_PAYMENTS/payment_method": [
        DownstreamAsset(
            name="Payment Mix Dashboard",
            asset_type="Dashboard",
            owner="finance-analytics@acme.com",
            criticality="medium",
            direct=True,
            last_queried_days_ago=2,
            description="Tracks payment method distribution over time",
        ),
        DownstreamAsset(
            name="Fraud Detection Model",
            asset_type="ML Model",
            owner="risk-team@acme.com",
            criticality="critical",
            direct=True,
            last_queried_days_ago=0,
            description="Real-time fraud scoring pipeline using payment method signals",
        ),
    ],
}

# Provide a fallback so any typed-in asset still returns something useful
_FALLBACK_DOWNSTREAM = [
    DownstreamAsset(
        name="Unknown Consumer A",
        asset_type="Dashboard",
        owner="team-unknown@acme.com",
        criticality="medium",
        direct=True,
        last_queried_days_ago=5,
        description="Auto-discovered downstream consumer (mocked)",
    ),
    DownstreamAsset(
        name="Unknown Consumer B",
        asset_type="Scheduled Query",
        owner="team-unknown@acme.com",
        criticality="low",
        direct=False,
        last_queried_days_ago=30,
        description="Auto-discovered transitive consumer (mocked)",
    ),
]


def _deterministic_fallback(qualified_name: str) -> list[DownstreamAsset]:
    """Generate a deterministic set of mock assets for any unknown qualified name."""
    seed = int(hashlib.md5(qualified_name.encode()).hexdigest()[:8], 16)
    count = (seed % 4) + 1  # 1-4 assets
    assets: list[DownstreamAsset] = []
    for i in range(count):
        idx = (seed + i) % len(ASSET_TYPES)
        crit_choices = list(CRITICALITY_WEIGHTS.keys())
        crit = crit_choices[(seed + i) % len(crit_choices)]
        assets.append(
            DownstreamAsset(
                name=f"Downstream Asset {i + 1}",
                asset_type=ASSET_TYPES[idx],
                owner=f"team-{i + 1}@acme.com",
                criticality=crit,
                direct=(i % 2 == 0),
                last_queried_days_ago=(seed + i * 7) % 60,
                description=f"Auto-discovered downstream asset (mocked for demo)",
            )
        )
    return assets


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def get_downstream_assets(qualified_name: str) -> list[DownstreamAsset]:
    """Return downstream assets affected by changes to *qualified_name*.

    Currently returns mocked data.  To connect to Atlan:
      1. Replace the body with an HTTP call to the Atlan lineage API.
      2. Map the API response into a list of DownstreamAsset objects.
    """
    if qualified_name in _MOCK_LINEAGE:
        return _MOCK_LINEAGE[qualified_name]
    return _deterministic_fallback(qualified_name)


def compute_risk_score(
    change_type: str,
    downstream_assets: list[DownstreamAsset],
) -> tuple[float, str]:
    """Compute a 0-100 risk score and a human-readable risk level.

    Heuristics
    ----------
    - More downstream assets → higher risk.
    - Higher criticality weights → higher risk.
    - Direct dependencies weighted more than transitive.
    - Recency of usage (last_queried_days_ago) boosts score.
    - Change-type multiplier (drops are worse than renames).
    """
    if not downstream_assets:
        return 0.0, "None"

    change_weight = RISK_WEIGHTS.get(change_type, 0.5)

    total = 0.0
    for asset in downstream_assets:
        crit_w = CRITICALITY_WEIGHTS.get(asset.criticality, 0.5)
        direct_w = 1.0 if asset.direct else 0.5
        # More recent usage → higher recency factor (max 1.0)
        recency = max(0.0, 1.0 - asset.last_queried_days_ago / 90.0)
        total += crit_w * direct_w * (0.5 + 0.5 * recency)

    # Normalize: assume 5 critical direct recent assets is a "perfect 100"
    max_expected = 5.0
    raw = (total / max_expected) * 100.0 * change_weight
    score = min(round(raw, 1), 100.0)

    if score >= 75:
        level = "Critical"
    elif score >= 50:
        level = "High"
    elif score >= 25:
        level = "Medium"
    else:
        level = "Low"

    return score, level


def generate_summary(
    source_asset: str,
    change_type: str,
    downstream_assets: list[DownstreamAsset],
    risk_score: float,
    risk_level: str,
    context: str = "",
) -> tuple[str, list[str]]:
    """Produce a plain-English blast-radius summary and a recommendations list."""
    n = len(downstream_assets)
    direct = sum(1 for a in downstream_assets if a.direct)
    transitive = n - direct
    critical_count = sum(1 for a in downstream_assets if a.criticality == "critical")
    high_count = sum(1 for a in downstream_assets if a.criticality == "high")

    owners = sorted({a.owner for a in downstream_assets})

    # --- Summary paragraph ---------------------------------------------------
    parts = [
        f"**{change_type}** on `{source_asset}` affects "
        f"**{n} downstream asset{'s' if n != 1 else ''}** "
        f"({direct} direct, {transitive} transitive)."
    ]

    if critical_count:
        parts.append(
            f"  \n{critical_count} of these are marked **critical**."
        )
    if high_count:
        parts.append(f"{high_count} are **high** criticality.")

    parts.append(
        f"  \nOverall risk score: **{risk_score}/100** ({risk_level})."
    )

    if context:
        parts.append(f'  \nStated reason: *"{context}"*')

    summary = " ".join(parts)

    # --- Recommendations -----------------------------------------------------
    recs: list[str] = []

    if risk_level == "Critical":
        recs.append(
            "This change is **critical-risk**. Do NOT proceed without sign-off "
            "from all impacted asset owners."
        )
    elif risk_level == "High":
        recs.append(
            "High-risk change — notify downstream owners and schedule a "
            "migration window before applying."
        )

    if critical_count:
        recs.append(
            f"Coordinate with owners of the {critical_count} critical asset(s) first: "
            + ", ".join(a.name for a in downstream_assets if a.criticality == "critical")
            + "."
        )

    if change_type == "Drop column":
        recs.append(
            "Consider a **soft deprecation** (add a deprecation notice, stop writes, "
            "then drop after one cycle) instead of an immediate drop."
        )
    elif change_type == "Rename column":
        recs.append(
            "Add a **backwards-compatible alias** (view or synonym) before renaming "
            "to give consumers time to migrate."
        )
    elif change_type == "Change data type":
        recs.append(
            "Verify that the new data type is **backward-compatible** (e.g., widening "
            "INT → BIGINT is safe; narrowing is not)."
        )
    elif change_type == "Deprecate table":
        recs.append(
            "Publish a **deprecation timeline** (e.g., 30/60/90-day warnings) and "
            "update the table's metadata tags in the catalog."
        )

    if len(owners) > 1:
        recs.append(
            f"Notify {len(owners)} distinct owner(s): {', '.join(owners)}."
        )

    recs.append(
        "Run this simulation again after applying changes to confirm the blast "
        "radius has narrowed."
    )

    return summary, recs


def simulate(
    qualified_name: str,
    change_type: str,
    context: str = "",
) -> ImpactResult:
    """End-to-end simulation: lineage → risk → summary."""
    assets = get_downstream_assets(qualified_name)
    score, level = compute_risk_score(change_type, assets)
    summary, recs = generate_summary(
        qualified_name, change_type, assets, score, level, context
    )
    return ImpactResult(
        source_asset=qualified_name,
        change_type=change_type,
        downstream_assets=assets,
        risk_score=score,
        risk_level=level,
        summary=summary,
        recommendations=recs,
    )
