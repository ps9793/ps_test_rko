"""
Databricks Migration Impact Simulator — Core Engine

Rule-based impact engine that estimates the blast radius of a Databricks
workspace / tenant migration on an existing Atlan Databricks connector.

All data is mocked for the hackathon. The interface is designed so each
function can be swapped for real Atlan API calls later.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHANGE_TYPES = [
    "Update hostname/URL on existing connection (same metastore)",
    "Point existing connection to interim workspace with smaller estate",
    "Create new Databricks connection for new workspace (same metastore)",
    "Migrate to new account + new metastore",
    "Complex / multi-workspace migration",
]

# Short labels used in the UI and summary text
CHANGE_TYPE_LABELS: dict[str, str] = {
    CHANGE_TYPES[0]: "Hostname update",
    CHANGE_TYPES[1]: "Interim workspace",
    CHANGE_TYPES[2]: "New connection (same metastore)",
    CHANGE_TYPES[3]: "New account + metastore",
    CHANGE_TYPES[4]: "Complex migration",
}

ENVIRONMENTS = ["Prod", "Non-prod", "Mixed"]
PERMISSION_OPTIONS = ["same", "broader", "narrower"]

# Base risk multipliers per scenario (0.0–1.0 scale)
SCENARIO_BASE_RISK: dict[str, float] = {
    CHANGE_TYPES[0]: 0.15,  # hostname only — low structural risk
    CHANGE_TYPES[1]: 0.70,  # interim workspace — high archive risk
    CHANGE_TYPES[2]: 0.60,  # new connection — duplication risk
    CHANGE_TYPES[3]: 0.85,  # new account+metastore — maximum structural change
    CHANGE_TYPES[4]: 0.90,  # complex — highest baseline
}

# Mocked asset-type distribution (% of total estate)
ASSET_TYPE_DISTRIBUTION: dict[str, float] = {
    "Tables": 0.45,
    "Views": 0.20,
    "Dashboards": 0.15,
    "Models (ML / dbt)": 0.10,
    "Queries / Notebooks": 0.10,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MigrationConfig:
    """All inputs collected from the UI."""

    current_assets: int
    new_assets: int
    change_type: str
    environment: str  # "Prod" | "Non-prod" | "Mixed"
    high_criticality_pct: float  # 0–100
    same_metastore: bool
    same_workspace_url: bool
    reuse_connection: bool
    crawler_perms: str  # "same" | "broader" | "narrower"
    interim_workspace: bool  # True if strict subset of final catalogs
    customer_notes: str = ""


@dataclass
class AffectedAssetGroup:
    """One row in the 'Affected Asset Groups' breakdown."""

    asset_type: str
    estimated_count: int
    pct_high_criticality: float  # 0–100


@dataclass
class ImpactResult:
    """Everything the UI needs to render the results panel."""

    # Core counts
    estimated_archived_assets: int = 0
    estimated_duplicated_assets: int = 0
    estimated_preserved_assets: int = 0

    # Scores (0–100)
    direct_impact_score: float = 0.0
    transitive_impact_score: float = 0.0
    overall_risk_score: float = 0.0
    risk_level: str = "Low"  # Low | Medium | High | Critical

    # Human-readable outputs
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)
    affected_groups: list[AffectedAssetGroup] = field(default_factory=list)

    # Echo back for display
    change_type_label: str = ""
    customer_notes: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _risk_level(score: float) -> str:
    """Map a 0-100 score to a human label."""
    if score >= 75:
        return "Critical"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Medium"
    return "Low"


def _compute_asset_counts(cfg: MigrationConfig) -> tuple[int, int, int]:
    """Estimate archived / duplicated / preserved asset counts.

    The logic branches by scenario and then applies modifiers for
    metastore sameness, permissions, and asset-count deltas.
    """
    current = cfg.current_assets
    new = cfg.new_assets
    change = cfg.change_type

    archived = 0
    duplicated = 0
    preserved = current  # optimistic default

    # --- Scenario 1: Hostname update, same metastore, reuse connection ------
    if change == CHANGE_TYPES[0]:
        # If filters & perms are identical, everything is preserved.
        if cfg.crawler_perms == "narrower":
            # Narrower perms may cause some assets to become inaccessible.
            loss_pct = 0.10  # ~10% lost to narrower perms
            archived = int(current * loss_pct)
        preserved = current - archived

    # --- Scenario 2: Interim workspace with fewer assets --------------------
    elif change == CHANGE_TYPES[1]:
        # Assets in Atlan but not in the new workspace get archived.
        if new < current:
            archived = current - new
        preserved = current - archived
        # If interim flag is on, add a note but counts stay the same.

    # --- Scenario 3: New connection, same metastore -------------------------
    elif change == CHANGE_TYPES[2]:
        # Overlapping assets get duplicated under different qualified names.
        overlap = min(current, new)
        duplicated = overlap
        # Nothing is archived from the old connection (it still exists).
        preserved = current  # old connection untouched
        # But effectively, the NEW connection creates duplicated copies.

    # --- Scenario 4: New account + new metastore ----------------------------
    elif change == CHANGE_TYPES[3]:
        # Maximum structural change — almost nothing auto-preserved.
        preserved_pct = 0.05  # only ~5% might survive via manual mapping
        if cfg.same_metastore:
            preserved_pct = 0.30  # user contradicted the scenario; be gentler
        preserved = int(current * preserved_pct)
        archived = current - preserved
        # Duplication if they also keep the old connection running.
        if not cfg.reuse_connection:
            duplicated = new  # new connection creates a parallel set

    # --- Scenario 5: Complex / multi-workspace ------------------------------
    elif change == CHANGE_TYPES[4]:
        # High baseline — assume partial archive + partial duplication.
        archived = int(current * 0.30)
        duplicated = int(min(current, new) * 0.40)
        preserved = current - archived

    # --- Permissions modifier (across all scenarios) ------------------------
    if cfg.crawler_perms == "narrower" and change != CHANGE_TYPES[0]:
        extra_archive = int(current * 0.05)
        archived = min(archived + extra_archive, current)
        preserved = current - archived

    return archived, duplicated, preserved


def _compute_scores(
    cfg: MigrationConfig,
    archived: int,
    duplicated: int,
) -> tuple[float, float, float]:
    """Compute direct_impact, transitive_impact, and overall risk scores.

    Direct impact  — based on the volume of immediately affected assets
                     plus the high-criticality %.
    Transitive     — penalty for large estates where many assets are
                     multiple hops from the source (modeled simply as
                     f(total_assets, high_crit_pct)).
    Overall        — weighted combination plus scenario base risk.
    """
    current = max(cfg.current_assets, 1)
    crit_frac = cfg.high_criticality_pct / 100.0

    # -- Direct impact -------------------------------------------------------
    affected_frac = (archived + duplicated) / current
    direct = affected_frac * 60.0 + crit_frac * 40.0
    # Bump for prod environments
    if cfg.environment == "Prod":
        direct *= 1.15
    elif cfg.environment == "Mixed":
        direct *= 1.05
    direct = _clamp(direct)

    # -- Transitive impact ---------------------------------------------------
    # Larger estates have more transitive fanout.
    scale_factor = min(math.log10(max(current, 10)) / 7.0, 1.0)  # log10(10M)~7
    transitive = (scale_factor * 50.0) + (crit_frac * 30.0) + (affected_frac * 20.0)
    transitive = _clamp(transitive)

    # -- Overall risk --------------------------------------------------------
    base = SCENARIO_BASE_RISK.get(cfg.change_type, 0.5)
    overall = (
        base * 40.0
        + direct * 0.35
        + transitive * 0.25
    )
    # Metastore change is a strong risk amplifier
    if not cfg.same_metastore:
        overall += 10.0
    # Not reusing connection raises duplication risk
    if not cfg.reuse_connection:
        overall += 5.0
    overall = _clamp(round(overall, 1))

    return round(direct, 1), round(transitive, 1), overall


def _build_affected_groups(
    total_affected: int,
    high_crit_pct: float,
) -> list[AffectedAssetGroup]:
    """Create mocked asset-type breakdown proportional to total affected."""
    groups: list[AffectedAssetGroup] = []
    for asset_type, frac in ASSET_TYPE_DISTRIBUTION.items():
        count = int(total_affected * frac)
        if count == 0 and total_affected > 0:
            count = 1  # show at least 1 so the row appears
        groups.append(
            AffectedAssetGroup(
                asset_type=asset_type,
                estimated_count=count,
                pct_high_criticality=round(high_crit_pct, 1),
            )
        )
    return groups


def _generate_summary(
    cfg: MigrationConfig,
    result: ImpactResult,
) -> str:
    """Produce a plain-English blast-radius summary paragraph."""
    label = CHANGE_TYPE_LABELS.get(cfg.change_type, cfg.change_type)
    affected_total = result.estimated_archived_assets + result.estimated_duplicated_assets
    affected_pct = (
        round(affected_total / max(cfg.current_assets, 1) * 100, 1)
    )
    crit_pct = cfg.high_criticality_pct

    parts: list[str] = []
    parts.append(
        f"**{label}** migration scenario selected."
    )
    parts.append(
        f"Expected to affect **~{affected_total:,}** of "
        f"**{cfg.current_assets:,}** existing assets "
        f"(**{affected_pct}%** of the estate)."
    )
    if crit_pct > 0:
        parts.append(
            f"Of those, **{crit_pct}%** are flagged as high-criticality."
        )

    if result.estimated_archived_assets > 0:
        parts.append(
            f"An estimated **{result.estimated_archived_assets:,}** assets "
            f"may be **archived or lost** from the catalog."
        )
    if result.estimated_duplicated_assets > 0:
        parts.append(
            f"An estimated **{result.estimated_duplicated_assets:,}** assets "
            f"may appear as **duplicates** under the new connection."
        )
    parts.append(
        f"Overall risk score: **{result.overall_risk_score}/100** "
        f"({result.risk_level})."
    )

    if cfg.customer_notes:
        parts.append(f'  \nCustomer notes: *"{cfg.customer_notes}"*')

    return "  \n".join(parts)


def _generate_recommendations(
    cfg: MigrationConfig,
    result: ImpactResult,
) -> list[str]:
    """Return 3-5 actionable recommendations tailored to the scenario."""
    recs: list[str] = []
    change = cfg.change_type

    # -- Universal high-risk preamble ----------------------------------------
    if result.risk_level == "Critical":
        recs.append(
            "This migration is rated **Critical risk**. "
            "Do not proceed without a detailed migration plan reviewed by "
            "both the customer's data-platform team and Atlan support."
        )
    elif result.risk_level == "High":
        recs.append(
            "This migration is rated **High risk**. "
            "Schedule a dedicated migration window and notify all downstream "
            "asset owners before proceeding."
        )

    # -- Scenario-specific advice --------------------------------------------
    if change == CHANGE_TYPES[0]:
        # Hostname update
        recs.append(
            "Risk is mainly around **connectivity and permissions**. "
            "Validate with a small test crawl after updating the hostname."
        )
        if cfg.crawler_perms == "narrower":
            recs.append(
                "Crawler permissions are **narrower** than before. "
                "Expect some assets to become inaccessible. "
                "Widen permissions or accept the reduced scope before cutover."
            )
        recs.append(
            "Confirm that Unity Catalog metastore ID, filters, and "
            "deny-list rules are unchanged after the URL swap."
        )

    elif change == CHANGE_TYPES[1]:
        # Interim workspace
        recs.append(
            "Updating the existing connection to an interim workspace will "
            "**archive assets not present in the smaller estate**. "
            "Prefer going directly from the old workspace to the final "
            "workspace to avoid churn."
        )
        if cfg.interim_workspace:
            recs.append(
                "The interim workspace contains a strict subset of the "
                "final catalogs. Consider creating a **separate temporary "
                "connection** for the interim period instead of re-pointing "
                "the production connection."
            )
        recs.append(
            "If you must use the interim workspace, document which assets "
            "will be temporarily archived and set expectations with "
            "downstream consumers."
        )

    elif change == CHANGE_TYPES[2]:
        # New connection, same metastore
        recs.append(
            "Creating a new Atlan connection will cause **duplicate assets** "
            "under different qualified names. Enrichment (tags, descriptions, "
            "owners) will remain on the old assets only."
        )
        recs.append(
            "Plan an **enrichment migration** using Atlan's asset-export/"
            "import or the MDLH pipeline to transfer metadata from the "
            "old connection to the new one."
        )
        recs.append(
            "After enrichment migration, archive or soft-delete the old "
            "connection's assets to avoid confusion."
        )

    elif change == CHANGE_TYPES[3]:
        # New account + new metastore
        recs.append(
            "New account + new metastore means Atlan will treat all assets "
            "as **brand-new entities**. Lineage continuity will break unless "
            "you plan explicit qualified-name mappings."
        )
        recs.append(
            "Run a **small-scale test crawl** (1-2 catalogs) on the new "
            "account and compare asset counts and critical-asset coverage "
            "before the full cutover."
        )
        recs.append(
            "Use Atlan's **bulk enrichment migration** (export from old, "
            "remap qualified names, import to new) to preserve tags, "
            "classifications, and ownership."
        )

    elif change == CHANGE_TYPES[4]:
        # Complex / multi-workspace
        recs.append(
            "Complex multi-workspace migrations carry the **highest risk "
            "of both duplication and data loss**. Break the migration into "
            "phases and simulate each phase independently."
        )
        recs.append(
            "Maintain a **connection mapping spreadsheet** that tracks "
            "old-workspace-to-new-workspace asset correspondence."
        )
        recs.append(
            "Consider using Atlan's **MDLH GOLD layer** to reconcile "
            "assets across workspaces after migration."
        )

    # -- Always-on closing recommendation ------------------------------------
    recs.append(
        "Re-run this simulation after each migration phase to confirm "
        "the blast radius is narrowing as expected."
    )

    return recs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate(cfg: MigrationConfig) -> ImpactResult:
    """End-to-end migration impact simulation.

    Orchestrates: asset-count estimation -> scoring -> summary -> recommendations.
    """
    archived, duplicated, preserved = _compute_asset_counts(cfg)
    direct, transitive, overall = _compute_scores(cfg, archived, duplicated)
    level = _risk_level(overall)

    total_affected = archived + duplicated
    affected_groups = _build_affected_groups(total_affected, cfg.high_criticality_pct)

    result = ImpactResult(
        estimated_archived_assets=archived,
        estimated_duplicated_assets=duplicated,
        estimated_preserved_assets=preserved,
        direct_impact_score=direct,
        transitive_impact_score=transitive,
        overall_risk_score=overall,
        risk_level=level,
        affected_groups=affected_groups,
        change_type_label=CHANGE_TYPE_LABELS.get(cfg.change_type, cfg.change_type),
        customer_notes=cfg.customer_notes,
    )

    result.summary = _generate_summary(cfg, result)
    result.recommendations = _generate_recommendations(cfg, result)

    return result
