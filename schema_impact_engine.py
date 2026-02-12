"""
Schema-Change Impact Simulator — Snowflake-backed Engine

Queries Snowflake's INFORMATION_SCHEMA to discover downstream dependencies
and computes risk scores based on change type and downstream asset count.

Snowflake config comes from env vars (see snowflake_client.py for details).

The target schema is hardcoded as PRERNA (constant PRERNA_SCHEMA below).
Change this if your demo schema has a different name.

Assumptions:
  - The PRERNA schema contains tables/views in the configured Snowflake database.
  - Downstream dependencies are approximated by scanning
    INFORMATION_SCHEMA.VIEWS for references to the given table name.
  - If no lineage table exists, the VIEW_DEFINITION text search is used.
  - If Snowflake is not configured, the engine falls back to deterministic
    mock data so the UI still works for demos without a live connection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from snowflake_client import SnowflakeClient, SnowflakeConnectionError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Schema containing the demo data — adjust if your schema name differs.
PRERNA_SCHEMA = "PRERNA"

CHANGE_TYPES = [
    "Rename table",
    "Drop table",
    "Deprecate table",
    "Change column type",
    "Drop column",
]

# Breaking changes get a higher base risk.
BREAKING_CHANGES = {"Drop table", "Drop column", "Change column type"}
SOFT_CHANGES = {"Rename table", "Deprecate table"}

SCOPE_OPTIONS = ["Single table", "Entire schema"]
ENV_OPTIONS = ["Prod", "Non-prod"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ImpactResult:
    source_asset: str
    change_type: str
    scope: str
    environment: str
    downstream_count: int = 0
    direct_count: int = 0
    transitive_count: int = 0
    max_depth: int = 0
    risk_score: int = 0
    risk_band: str = "Low"
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)
    snowflake_connected: bool = False


# ---------------------------------------------------------------------------
# Risk scoring (as specified in the requirements)
# ---------------------------------------------------------------------------


def compute_risk_score(change_type: str, downstream_count: int) -> tuple[int, str]:
    """Compute risk score and band.

    Rules:
      - Base: 70 for breaking changes, 30 for soft changes.
      - +10 if downstream_count > 10.
      - +20 if downstream_count > 100  (replaces the +10, not additive).
      - Cap at 100, integer.

    Bands: 0–29 → Low, 30–59 → Medium, 60+ → High.
    """
    base = 70 if change_type in BREAKING_CHANGES else 30

    bonus = 0
    if downstream_count > 100:
        bonus = 20
    elif downstream_count > 10:
        bonus = 10

    score = min(base + bonus, 100)

    if score >= 60:
        band = "High"
    elif score >= 30:
        band = "Medium"
    else:
        band = "Low"

    return score, band


# ---------------------------------------------------------------------------
# Summary & recommendations
# ---------------------------------------------------------------------------


def _generate_summary(
    source_asset: str,
    change_type: str,
    downstream_count: int,
    direct_count: int,
    transitive_count: int,
    risk_band: str,
    environment: str,
    scope: str,
) -> str:
    """Produce a 1–3 sentence blast-radius summary."""
    is_breaking = change_type in BREAKING_CHANGES
    compat = "**not backward-compatible**" if is_breaking else "likely backward-compatible"

    parts = [
        f"**{change_type}** on `{source_asset}` affects an estimated "
        f"**{downstream_count}** downstream asset(s) "
        f"({direct_count} direct, {transitive_count} transitive). "
        f"This change is {compat}."
    ]

    if downstream_count > 0:
        parts.append(
            "Likely impacted consumers include downstream views, dbt models, "
            "dashboards, and scheduled queries that reference this asset."
        )

    if environment == "Prod" and risk_band == "High":
        parts.append(
            "**This is a production environment** — extra caution is warranted."
        )

    return " ".join(parts)


def _generate_recommendations(
    change_type: str,
    downstream_count: int,
    risk_band: str,
    environment: str,
) -> list[str]:
    """Scenario-specific recommended next steps."""
    recs: list[str] = []

    if environment == "Prod":
        recs.append(
            "**Stage in non-prod first.** Apply this change in a non-production "
            "environment and verify that downstream assets continue to work."
        )

    if risk_band == "High":
        recs.append(
            "**Communicate broadly.** Notify all downstream asset owners before "
            "applying this change — the blast radius is significant."
        )

    if change_type == "Drop table":
        recs.append(
            "**Deprecate before dropping.** Mark the table as deprecated, "
            "wait for consumers to migrate, then drop after a grace period."
        )
    elif change_type == "Drop column":
        recs.append(
            "**Soft deprecation.** Stop writing to the column, add a deprecation "
            "notice, then drop after one full refresh cycle."
        )
    elif change_type == "Rename table":
        recs.append(
            "**Create an alias view.** Add a view with the old name pointing to "
            "the new table so consumers can migrate at their own pace."
        )
    elif change_type == "Deprecate table":
        recs.append(
            "**Publish a deprecation timeline** (e.g. 30/60/90-day warnings) "
            "and update metadata tags in the catalog."
        )
    elif change_type == "Change column type":
        recs.append(
            "**Verify backward compatibility.** Widening (e.g. INT -> BIGINT) is "
            "usually safe; narrowing or changing type families is breaking."
        )

    if downstream_count > 0:
        recs.append(
            "**Test downstream queries.** Run integration tests against key "
            "downstream assets to validate they still produce correct results."
        )

    recs.append(
        "**Prepare rollback.** Have a rollback plan ready (e.g. `ALTER TABLE` "
        "to revert the change, or restore from a Snowflake Time Travel snapshot)."
    )

    recs.append(
        "**Re-assess after applying.** Run this simulator again post-change "
        "to confirm the blast radius has narrowed as expected."
    )

    return recs


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def simulate(
    qualified_name: str,
    change_type: str,
    scope: str = "Single table",
    environment: str = "Prod",
) -> ImpactResult:
    """End-to-end simulation: Snowflake query -> risk score -> summary.

    Falls back to deterministic mock data when Snowflake is not configured.
    """
    snowflake_connected = False
    downstream_count = 0
    direct_count = 0
    transitive_count = 0
    max_depth = 0

    try:
        client = SnowflakeClient()
        # Extract just the table name from the qualified name.
        table_name = _extract_table_name(qualified_name)

        result = client.get_downstream_dependencies(table_name, PRERNA_SCHEMA)
        downstream_count = result["total_count"]
        direct_count = result["direct_count"]
        transitive_count = result["transitive_count"]
        max_depth = result["max_depth"]
        snowflake_connected = True
    except (SnowflakeConnectionError, Exception):
        # Fall back to mock data — UI still works without Snowflake.
        downstream_count, direct_count, transitive_count, max_depth = (
            _mock_downstream(qualified_name)
        )

    # "Entire schema" scope multiplies the estimate to reflect broader impact.
    if scope == "Entire schema":
        downstream_count = int(downstream_count * 3.5)
        direct_count = int(direct_count * 3.5)
        transitive_count = int(transitive_count * 3.5)

    risk_score, risk_band = compute_risk_score(change_type, downstream_count)

    summary = _generate_summary(
        qualified_name,
        change_type,
        downstream_count,
        direct_count,
        transitive_count,
        risk_band,
        environment,
        scope,
    )

    recommendations = _generate_recommendations(
        change_type, downstream_count, risk_band, environment
    )

    return ImpactResult(
        source_asset=qualified_name,
        change_type=change_type,
        scope=scope,
        environment=environment,
        downstream_count=downstream_count,
        direct_count=direct_count,
        transitive_count=transitive_count,
        max_depth=max_depth,
        risk_score=risk_score,
        risk_band=risk_band,
        summary=summary,
        recommendations=recommendations,
        snowflake_connected=snowflake_connected,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_table_name(qualified_name: str) -> str:
    """Extract table name from an Atlan-style qualified name.

    Handles formats like:
      default/snowflake/123/DB/SCHEMA/TABLE/column  → TABLE
      default/snowflake/123/DB/SCHEMA/TABLE          → TABLE
      SCHEMA.TABLE                                    → TABLE
      TABLE                                           → TABLE
    """
    parts = qualified_name.strip().split("/")
    if len(parts) >= 6:
        return parts[5]  # TABLE is the 6th segment
    if len(parts) >= 4:
        return parts[-1]
    # Handle dot-separated names (e.g. PRERNA.FCT_ORDERS)
    if "." in qualified_name:
        return qualified_name.split(".")[-1]
    return qualified_name


def _mock_downstream(qualified_name: str) -> tuple[int, int, int, int]:
    """Deterministic mock data when Snowflake is not available.

    Returns (total, direct, transitive, max_depth).
    """
    seed = int(hashlib.md5(qualified_name.encode()).hexdigest()[:8], 16)
    total = (seed % 15) + 2  # 2–16 downstream assets
    direct = max(1, total // 3)
    transitive = total - direct
    depth = min(transitive, 4) if transitive > 0 else 1
    return total, direct, transitive, depth
