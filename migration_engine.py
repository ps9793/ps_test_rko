"""
Databricks Migration Impact Simulator — Core Engine

Rule-based impact engine that estimates the blast radius of a Databricks
workspace / tenant migration on an existing Atlan Databricks connector.

All data is mocked for the hackathon. The interface is designed so each
function can be swapped for real Atlan API calls later.

## Risk Model Summary
────────────────────
Inputs used:
  - current_assets, new_assets, scenario, same_metastore, is_prod,
    overlap_pct (new-connection only), crawler_perms, interim_subset.

Risk formula (integer 0–100):
  risk = base(scenario) + 40*lost_pct + 40*dup_pct + prod_bonus + perms_adj
  where:
    base = 20 (hostname) | 55 (re-point) | 65 (new connection)
    lost_pct  = archived_assets / current_assets
    dup_pct   = duplicated_assets / current_assets
    prod_bonus = +10 if production tenant
    perms_adj  = +5 (narrower) | -5 (broader) | 0 (same)

When duplicated_assets > 0:
  Only in the "Create new Databricks connection" scenario AND
  same_metastore == True AND overlap_pct > 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCENARIOS = [
    "Update hostname/URL on existing connection (same metastore)",
    "Point existing connection to new workspace (same metastore)",
    "Create new Databricks connection to new workspace",
]

SCENARIO_LABELS: dict[str, str] = {
    SCENARIOS[0]: "Hostname update",
    SCENARIOS[1]: "Re-point existing connection",
    SCENARIOS[2]: "New connection",
}

PERMISSION_OPTIONS = ["same", "broader", "narrower"]

# Base risk per scenario (0–100 scale)
SCENARIO_BASE: dict[str, int] = {
    SCENARIOS[0]: 20,
    SCENARIOS[1]: 55,
    SCENARIOS[2]: 65,
}

# Mocked asset-type distribution (% of total estate)
ASSET_TYPE_DISTRIBUTION: dict[str, float] = {
    "Tables": 0.45,
    "Views": 0.20,
    "Dashboards": 0.15,
    "Models (ML / dbt)": 0.10,
    "Queries / Notebooks": 0.10,
}

# Safe test crawl guidance (scenario-agnostic)
SAFE_TEST_CRAWL_GUIDANCE: list[str] = [
    (
        "**Create a separate test connection** — In Atlan, create a new "
        "Databricks connection pointing to the **new** workspace/hostname. "
        'Give it a clear name like "Databricks – NEW TENANT – TEST ONLY".'
    ),
    (
        "**Scope it down** — Limit the connection filters to **1–2 "
        "catalogs/schemas** that exist in both old and new environments. "
        "Pick ones that are representative but not business-critical if possible."
    ),
    (
        "**Run manually, once** — Do not schedule it yet. Run preflight "
        "checks, then run the workflow once."
    ),
    (
        "**Compare and interpret results** — Compare asset counts for those "
        "catalogs between the old connection (current production) and the new "
        "test connection. Spot-check that qualified names look consistent and "
        "key tables appear once (not missing or duplicated)."
    ),
    (
        "**Decide next step** — If the test looks good, expand scope (more "
        "catalogs) or plan your production switch. If it looks off (missing "
        "data, unexpected structure), fix issues with Databricks/workspace "
        "configuration before touching the production connection."
    ),
]


def generate_recovery_steps(scenario: str) -> list[dict[str, str]]:
    """Return scenario-aware 'If something goes wrong' guidance.

    Each item is a dict with 'heading' and 'detail' keys.
    """
    steps: list[dict[str, str]] = []

    # Universal first step
    steps.append({
        "heading": "Stop the bleeding first",
        "detail": (
            "Pause or stop the affected Databricks workflows in Atlan "
            "(both old and new connections) to avoid compounding issues."
        ),
    })

    if scenario == SCENARIOS[0]:
        # Hostname update — revert is straightforward
        steps.append({
            "heading": "If connectivity fails or assets look wrong after the hostname change",
            "detail": (
                "Revert the connection configuration to the **previous hostname** "
                "(use the saved config/screenshot you took before cutover). "
                "Re-run the workflow with the old config to confirm catalog "
                "coverage returns to normal."
            ),
        })

    elif scenario == SCENARIOS[1]:
        # Re-point — the high-risk archive scenario
        steps.append({
            "heading": "If large portions of the estate disappeared after repointing",
            "detail": (
                "Revert the connection configuration to the **previous "
                "hostname/workspace** (use the saved config/screenshot). "
                "Re-run the workflow with the old config to restore catalog "
                "coverage. Only after you see expected asset counts again "
                "should you attempt a new migration approach."
            ),
        })

    elif scenario == SCENARIOS[2]:
        # New connection — duplicate risk
        steps.append({
            "heading": "If you see duplicates across old and new connections",
            "detail": (
                "Decide which connection is the **source of truth** (old vs "
                "new). Temporarily disable schedules on the non-canonical "
                "connection. Use search and filters (by connection, label, etc.) "
                "to bulk-archive or hide legacy assets — but only after the new "
                "connection is fully validated."
            ),
        })

    # Universal last-resort step
    steps.append({
        "heading": "If the tenant state looks corrupted or inconsistent",
        "detail": (
            "Note the approximate time of the last \"good\" state. Contact "
            "Atlan support and reference that Atlan maintains **daily tenant "
            "backups**; ask about restoring to that timestamp as a last resort. "
            "Communicate the potential impact and downtime to stakeholders "
            "before proceeding with a restore."
        ),
    })

    return steps


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MigrationConfig:
    """All inputs collected from the UI."""

    current_assets: int
    new_assets: int
    scenario: str              # one of SCENARIOS
    same_metastore: bool
    is_prod: bool
    overlap_pct: float | None  # 0–1, used only for new-connection scenario
    crawler_perms: str         # "same" | "broader" | "narrower"
    interim_subset: bool
    customer_notes: str = ""


@dataclass
class AffectedAssetGroup:
    """One row in the 'Affected Asset Groups' breakdown."""

    asset_type: str
    estimated_count: int


@dataclass
class ImpactResult:
    """Everything the UI needs to render the results panel."""

    # Core counts
    archived_assets: int = 0
    duplicated_assets: int = 0
    preserved_assets: int = 0

    # Scores (0–100, integer)
    risk_score: int = 0
    direct_impact_score: int = 0
    transitive_impact_score: int = 0
    risk_level: str = "Low"  # Low | Medium | High

    # Human-readable outputs
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    affected_groups: list[AffectedAssetGroup] = field(default_factory=list)

    # Echo back for display
    scenario_label: str = ""
    customer_notes: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _risk_level(score: int) -> str:
    if score > 60:
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"


def _compute_asset_counts(cfg: MigrationConfig) -> tuple[int, int, int, list[str]]:
    """Estimate archived / duplicated / preserved asset counts.

    Returns (archived, duplicated, preserved, notes).
    """
    total = cfg.current_assets
    new = min(cfg.new_assets, total)
    scenario = cfg.scenario
    notes: list[str] = []

    archived = 0
    duplicated = 0
    preserved = total

    # --- Scenario 1: Update hostname/URL on existing connection ----------------
    if scenario == SCENARIOS[0]:
        archived = 0
        duplicated = 0
        preserved = total
        if not cfg.same_metastore:
            notes.append(
                "You selected 'Update hostname' but indicated the metastore "
                "is changing. This is unusual — a hostname change with a "
                "different metastore may cause unexpected asset loss."
            )

    # --- Scenario 2: Point existing connection to new workspace ----------------
    elif scenario == SCENARIOS[1]:
        preserved = new
        archived = max(0, total - new)
        duplicated = 0
        if cfg.interim_subset:
            notes.append(
                "This is an interim workspace with a strict subset of the "
                "final catalogs. Archived assets are temporary but high-risk — "
                "downstream users will lose visibility until the final workspace "
                "is connected."
            )

    # --- Scenario 3: Create new Databricks connection --------------------------
    elif scenario == SCENARIOS[2]:
        overlap = cfg.overlap_pct if cfg.overlap_pct is not None else 0.0
        if cfg.same_metastore and overlap > 0:
            duplicated = round(total * overlap)
        else:
            duplicated = 0
        archived = 0
        preserved = total
        if not cfg.same_metastore:
            notes.append(
                "New connection with a different metastore — Atlan will treat "
                "all assets as brand-new entities. No duplicates, but lineage "
                "continuity will break unless you plan explicit qualified-name "
                "mappings."
            )

    return archived, duplicated, preserved, notes


def _compute_scores(
    cfg: MigrationConfig,
    archived: int,
    duplicated: int,
) -> tuple[int, int, int]:
    """Compute risk_score, direct_impact_score, transitive_impact_score.

    All returned as integers 0–100.
    """
    total = max(cfg.current_assets, 1)

    lost_pct = archived / total
    dup_pct = duplicated / total

    # --- Overall risk score ---------------------------------------------------
    base = SCENARIO_BASE.get(cfg.scenario, 50)
    loss_component = 40.0 * lost_pct
    dup_component = 40.0 * dup_pct
    prod_component = 10.0 if cfg.is_prod else 0.0

    perms_component = 0.0
    if cfg.crawler_perms == "narrower":
        perms_component = 5.0
    elif cfg.crawler_perms == "broader":
        perms_component = -5.0

    risk_raw = base + loss_component + dup_component + prod_component + perms_component
    risk_score = int(max(0, min(100, round(risk_raw))))

    # --- Direct impact score --------------------------------------------------
    # Driven primarily by the fraction of assets lost or duplicated.
    direct_raw = (lost_pct + dup_pct) * 80.0 + prod_component
    direct_score = int(max(0, min(100, round(direct_raw))))

    # --- Transitive impact score ----------------------------------------------
    # Slightly lower than direct; scaled by estate size (log heuristic).
    scale = min(math.log10(max(total, 10)) / 7.0, 1.0)
    transitive_raw = direct_raw * 0.7 * scale
    transitive_score = int(max(0, min(100, round(transitive_raw))))

    return risk_score, direct_score, transitive_score


def _build_affected_groups(
    archived: int,
    duplicated: int,
    preserved: int,
) -> list[AffectedAssetGroup]:
    """Create mocked asset-type breakdown proportional to affected assets."""
    total_affected = archived + duplicated
    groups: list[AffectedAssetGroup] = []
    for asset_type, frac in ASSET_TYPE_DISTRIBUTION.items():
        count = int(total_affected * frac)
        if count == 0 and total_affected > 0:
            count = 1
        groups.append(AffectedAssetGroup(asset_type=asset_type, estimated_count=count))
    return groups


def _generate_summary(cfg: MigrationConfig, result: ImpactResult) -> str:
    """Produce a plain-English blast-radius summary paragraph."""
    label = SCENARIO_LABELS.get(cfg.scenario, cfg.scenario)
    total = max(cfg.current_assets, 1)
    affected_total = result.archived_assets + result.duplicated_assets
    affected_pct = round(affected_total / total * 100)

    parts: list[str] = []

    parts.append(f"**{label}** scenario selected.")

    if affected_total > 0:
        parts.append(
            f"This change is expected to affect approximately "
            f"**{affected_total:,} of {cfg.current_assets:,} existing assets "
            f"({affected_pct}%)**."
        )
    else:
        parts.append(
            f"This change is expected to have **minimal structural impact** on "
            f"the **{cfg.current_assets:,}** existing assets."
        )

    # Explain the primary risk type — scenario-aware emphasis
    if cfg.scenario == SCENARIOS[0]:
        # Hostname update: emphasize connectivity, not loss
        parts.append(
            "If the metastore and connection filters are unchanged, the primary "
            "risk is around **connectivity and permissions** — not asset loss. "
            "Assets should remain intact as long as the new hostname resolves "
            "to the same Unity Catalog metastore."
        )
    elif result.archived_assets > 0 and result.duplicated_assets == 0:
        # Re-point scenario: emphasize archive danger
        parts.append(
            "Because we are re-using the same connection and the new workspace "
            "has fewer assets, these assets are at risk of being **archived or "
            "disappearing from the catalog**. For a large estate, this can mean "
            "losing visibility on a significant portion of assets in a single "
            "crawl run."
        )
    elif result.duplicated_assets > 0 and result.archived_assets == 0:
        # New connection: emphasize duplication + split enrichment
        parts.append(
            "Existing curated assets remain in place while new assets are "
            "created under a separate connection, leading to **duplicate "
            "tables, models, dashboards, and split enrichment**. The primary "
            "challenge is managing the overlap period and migrating enrichment "
            "(tags, descriptions, owners) from old to new assets."
        )
    elif result.archived_assets > 0 and result.duplicated_assets > 0:
        parts.append(
            "This scenario carries both **archive risk** (assets disappearing) "
            "and **duplication risk** (overlapping assets under different "
            "connections)."
        )

    env = "production" if cfg.is_prod else "non-production"
    parts.append(
        f"Overall risk score: **{result.risk_score}/100 ({result.risk_level})** "
        f"for this {env} tenant."
    )

    # Append any engine notes
    for note in result.notes:
        parts.append(f"*Note: {note}*")

    if cfg.customer_notes:
        parts.append(f'Customer notes: *"{cfg.customer_notes}"*')

    return "  \n".join(parts)


def _generate_recommendations(
    cfg: MigrationConfig,
    result: ImpactResult,
) -> list[str]:
    """Return actionable recommendations tailored to the scenario and risk."""
    recs: list[str] = []
    scenario = cfg.scenario

    # -- Risk preamble ---------------------------------------------------------
    if result.risk_level == "High":
        recs.append(
            "This migration is rated **High risk**. Schedule a dedicated "
            "migration window and notify all downstream asset owners before "
            "proceeding."
        )
    elif result.risk_level == "Medium":
        recs.append(
            "This migration is rated **Medium risk**. Review the blast radius "
            "carefully and ensure key stakeholders are aware before proceeding."
        )

    # -- Scenario-specific advice ----------------------------------------------
    if scenario == SCENARIOS[0]:
        # --- Scenario 1: Update hostname/URL (same metastore) -----------------
        recs.append(
            "**Validate assumptions before changing anything in prod** — "
            "Confirm with the Databricks team that the Unity Catalog metastore "
            "ID stays the same and the same catalogs/schemas/tables will remain "
            "available. In Atlan, confirm the connection filters "
            "(catalogs/schemas) won't change."
        )
        recs.append(
            "**Run a small test crawl on a separate connection first** — Do "
            "**not** point the existing production connection to a test URL. "
            "Instead, create a **new Databricks connection** pointing at the "
            "new hostname, limit filters to 1–2 low-risk catalogs/schemas, and "
            "run the workflow once manually with scheduling turned off. Compare "
            "asset counts and qualified names vs. the old connection for those "
            "catalogs."
        )
        recs.append(
            "**Plan the production switch** — Schedule a short migration "
            "window. Before editing the production connection, capture the "
            "current connection configuration (screenshot or JSON) and the last "
            "successful run time. Communicate to downstream teams that a brief "
            "refresh gap might occur."
        )
        recs.append(
            "**Cut over with a clear rollback** — Update the hostname on the "
            "existing connection. Run preflight + a limited-scope run first "
            "(not the full estate). If something looks wrong (missing catalogs, "
            "failures), revert the hostname to the previous value and re-run "
            "the workflow to restore previous behavior."
        )

    elif scenario == SCENARIOS[1]:
        # --- Scenario 2: Re-point existing connection -------------------------
        recs.append(
            "**Treat this as a high-risk operation** — Re-using the same "
            "connection and pointing it to a workspace with fewer assets will "
            "likely **archive everything that no longer appears in the new "
            "workspace**. For a large estate, this can mean losing visibility "
            "on hundreds of thousands of assets in a single crawl."
        )
        recs.append(
            "**Do not repoint your existing production connection to an "
            "interim workspace** that has only a subset of catalogs. Instead, "
            "either wait until the **final** workspace is fully ready, or use "
            "**Scenario 3 (new connection)** plus controlled enrichment "
            "migration to avoid any archival churn."
        )
        recs.append(
            "**If you still must use this scenario, follow a strict plan** — "
            "First, ensure a **separate test connection** has already validated "
            "that the new workspace exposes the full set of required assets. "
            "Then restrict the first production run to a smaller set of "
            "catalogs to verify behavior before scanning the entire estate. "
            "Communicate clearly that assets not present in the new workspace "
            "will be archived in Atlan."
        )
        recs.append(
            "**Treat tenant backups as a last resort, not the primary plan** — "
            "Atlan keeps **daily backups** of the tenant and, in a worst-case "
            "scenario, support can restore to the last known good point. "
            "However, this is a **time-consuming operation** and should not be "
            "used as a substitute for safe testing and planning."
        )
        if not cfg.same_metastore:
            recs.append(
                "**Metastore is also changing** — Assets may get new qualified "
                "names and lose enrichment. Plan an enrichment migration "
                "(asset-export / MDLH) before cutting over."
            )

    elif scenario == SCENARIOS[2]:
        # --- Scenario 3: New connection in parallel ---------------------------
        recs.append(
            "**Stand up the new connection in parallel** — Create a new "
            "Databricks connection pointing to the new workspace. Start with a "
            "limited scope (e.g., 1–2 critical catalogs). Run the workflow "
            "manually and confirm that counts & structures match expectations "
            "and permissions and Unity Catalog behavior are correct."
        )
        recs.append(
            "**Gradually expand scope and compare results** — Increase filters "
            "to include more catalogs/schemas. Compare total asset counts "
            "between old vs. new for a few key domains, and spot-check a small "
            "sample of business-critical tables/views."
        )
        recs.append(
            "**Plan enrichment & user migration** — Clearly label the new "
            "connection as the future \"source of truth\". Optionally use "
            "Atlan's enrichment migration options (asset-export / MDLH) to "
            "export enrichment for overlapping assets from the old connection "
            "and re-apply to the new assets once validated. Communicate a "
            "timeline for when users should switch and when the old connection "
            "will be frozen and eventually retired."
        )
        recs.append(
            "**Clean up duplicates carefully** — Once the new connection is "
            "stable and validated, turn off schedules on the old connection. "
            "Use filters (by connection, label, or source) to bulk-archive or "
            "hide legacy assets. Make sure teams have confirmed they are no "
            "longer using the old assets before final cleanup."
        )

    # -- Closing recommendation ------------------------------------------------
    recs.append(
        "Re-run this simulation after each migration phase to confirm the "
        "blast radius is narrowing as expected."
    )

    return recs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def simulate(cfg: MigrationConfig) -> ImpactResult:
    """End-to-end migration impact simulation.

    Orchestrates: asset-count estimation -> scoring -> summary -> recommendations.
    """
    archived, duplicated, preserved, notes = _compute_asset_counts(cfg)
    risk_score, direct_score, transitive_score = _compute_scores(
        cfg, archived, duplicated,
    )
    level = _risk_level(risk_score)
    affected_groups = _build_affected_groups(archived, duplicated, preserved)

    result = ImpactResult(
        archived_assets=archived,
        duplicated_assets=duplicated,
        preserved_assets=preserved,
        risk_score=risk_score,
        direct_impact_score=direct_score,
        transitive_impact_score=transitive_score,
        risk_level=level,
        notes=notes,
        affected_groups=affected_groups,
        scenario_label=SCENARIO_LABELS.get(cfg.scenario, cfg.scenario),
        customer_notes=cfg.customer_notes,
    )

    result.summary = _generate_summary(cfg, result)
    result.recommendations = _generate_recommendations(cfg, result)

    return result
