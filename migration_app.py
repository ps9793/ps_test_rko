"""
Databricks Migration Impact Simulator — Streamlit UI

Helps Atlan users simulate the impact of Databricks workspace / tenant
migrations on an existing Atlan Databricks connector (crawler).

Run with:  streamlit run migration_app.py
"""

import streamlit as st
from migration_engine import (
    SCENARIOS,
    PERMISSION_OPTIONS,
    RECOVERY_STEPS,
    MigrationConfig,
    simulate,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Databricks Migration Impact Simulator",
    page_icon="🔷",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .risk-badge {
        display: inline-block;
        padding: 4px 16px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 1rem;
        margin-bottom: 8px;
    }
    .risk-high   { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
    .risk-medium { background: #fefce8; color: #854d0e; border: 1px solid #fde047; }
    .risk-low    { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }

    .impact-chip {
        display: inline-block;
        padding: 6px 14px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        margin-right: 12px;
        margin-bottom: 8px;
    }
    .chip-high   { background: #fee2e2; color: #991b1b; }
    .chip-medium { background: #fefce8; color: #854d0e; }
    .chip-low    { background: #f0fdf4; color: #166534; }

    .score-ring {
        font-size: 3rem;
        font-weight: 800;
        text-align: center;
    }

    .asset-group-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Databricks Migration Impact Simulator")
st.caption(
    "Simulate the blast radius of a Databricks workspace or tenant migration "
    "on your Atlan catalog — before you make the change."
)
st.divider()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RISK_CSS = {
    "High": "risk-high",
    "Medium": "risk-medium",
    "Low": "risk-low",
}
RISK_COLOR = {
    "High": "#dc2626",
    "Medium": "#ca8a04",
    "Low": "#16a34a",
}
CHIP_CSS = {
    "High": "chip-high",
    "Medium": "chip-medium",
    "Low": "chip-low",
}


def _risk_badge_html(level: str) -> str:
    css = RISK_CSS.get(level, "risk-low")
    return f'<span class="risk-badge {css}">{level} Risk</span>'


def _chip_html(label: str, score: int) -> str:
    if score > 60:
        lvl = "High"
    elif score >= 30:
        lvl = "Medium"
    else:
        lvl = "Low"
    css = CHIP_CSS.get(lvl, "chip-low")
    return f'<span class="impact-chip {css}">{label}: {lvl} ({score}/100)</span>'


# ---------------------------------------------------------------------------
# Layout — two columns
# ---------------------------------------------------------------------------
col_input, col_results = st.columns([1, 2], gap="large")

# ---------------------------------------------------------------------------
# LEFT COLUMN — Migration Configuration
# ---------------------------------------------------------------------------
with col_input:
    st.subheader("Migration Configuration")

    # --- Current connection details -----------------------------------------
    st.markdown("##### Current Connection Details")

    current_assets = st.number_input(
        "Assets currently in Atlan (approx)",
        min_value=0,
        max_value=50_000_000,
        value=1_000_000,
        step=10_000,
        format="%d",
    )

    is_prod = st.radio(
        "Is this a production tenant?",
        [
            "Yes – Production / Business Critical",
            "No – Non-prod / Sandbox",
        ],
        horizontal=True,
    ) == "Yes – Production / Business Critical"

    st.markdown("---")

    # --- Planned migration --------------------------------------------------
    st.markdown("##### Planned Migration")

    scenario = st.selectbox("Migration scenario", SCENARIOS)

    same_metastore = st.radio(
        "Will the Unity Catalog metastore stay the same?",
        ["Yes", "No"],
        horizontal=True,
    ) == "Yes"

    # --- Contextual inputs based on scenario --------------------------------

    # New assets at cutover: relevant when workspace changes
    if scenario in (SCENARIOS[1], SCENARIOS[2]):
        new_assets = st.number_input(
            "Estimated assets in new workspace at cutover",
            min_value=0,
            max_value=50_000_000,
            value=current_assets,
            step=10_000,
            format="%d",
        )
    else:
        new_assets = current_assets

    # Overlap slider: only for "Create new connection" scenario
    overlap_pct = None
    if scenario == SCENARIOS[2]:
        overlap_raw = st.slider(
            "Approx. % of existing assets that will also appear in the new workspace",
            min_value=0,
            max_value=100,
            value=60,
            help=(
                "Duplicated assets = assets that may appear twice (old + new "
                "connection) until you clean up enrichment."
            ),
        )
        overlap_pct = overlap_raw / 100.0

    # Interim workspace flag: only for "Point existing connection" scenario
    interim_subset = False
    if scenario == SCENARIOS[1]:
        interim_subset = st.checkbox(
            "This workspace is an interim workspace with a strict subset of the final catalogs",
            help=(
                "If checked, the simulator treats archived assets as temporary "
                "but high-risk — downstream users will lose visibility until "
                "the final workspace is connected."
            ),
        )

    # Crawler permissions — small modifier
    crawler_perms = st.selectbox(
        "Crawler credential permissions",
        PERMISSION_OPTIONS,
        format_func=lambda x: x.capitalize(),
        help="How do the crawler's permissions on the new workspace compare to the old one?",
    )

    st.markdown("---")

    # --- Optional notes -----------------------------------------------------
    st.markdown("##### Notes")
    customer_notes = st.text_area(
        "Notes for customer (optional)",
        placeholder="e.g. Customer is migrating from AWS to Azure Databricks…",
        height=80,
    )

    simulate_clicked = st.button(
        "Simulate Migration Impact",
        type="primary",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# RIGHT COLUMN — Results
# ---------------------------------------------------------------------------
with col_results:
    if simulate_clicked:
        cfg = MigrationConfig(
            current_assets=current_assets,
            new_assets=new_assets,
            scenario=scenario,
            same_metastore=same_metastore,
            is_prod=is_prod,
            overlap_pct=overlap_pct,
            crawler_perms=crawler_perms,
            interim_subset=interim_subset,
            customer_notes=customer_notes,
        )

        with st.spinner("Simulating migration impact…"):
            result = simulate(cfg)

        st.subheader("Impact Results")

        # -- Headline metrics ------------------------------------------------
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Archived Assets",
            f"{result.archived_assets:,}",
            help=(
                "Archived assets = assets that may disappear from Atlan's "
                "catalog after the migration because they're no longer "
                "present in the new workspace."
            ),
        )
        m2.metric(
            "Duplicated Assets",
            f"{result.duplicated_assets:,}",
            help=(
                "Duplicated assets = assets that may appear twice (old + new "
                "connection) until you clean up enrichment."
            ),
        )
        m3.metric(
            "Preserved Assets",
            f"{result.preserved_assets:,}",
        )
        m4.metric(
            "Risk Score",
            f"{result.risk_score}/100",
        )

        st.divider()

        # -- Score ring + summary --------------------------------------------
        score_col, summary_col = st.columns([1, 2])

        with score_col:
            st.markdown("#### Overall Risk")
            color = RISK_COLOR.get(result.risk_level, "#64748b")
            st.markdown(
                f'<p class="score-ring" style="color:{color}">'
                f"{result.risk_score}</p>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:center'>"
                f"{_risk_badge_html(result.risk_level)}"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "<p style='text-align:center;color:#64748b;font-size:.85rem'>"
                "out of 100</p>",
                unsafe_allow_html=True,
            )

        with summary_col:
            st.markdown("#### Blast Radius Summary")
            st.markdown(result.summary)

        st.divider()

        # -- Direct vs Transitive impact chips -------------------------------
        st.markdown("#### Impact Breakdown")
        st.markdown(
            _chip_html("Direct impact", result.direct_impact_score)
            + _chip_html("Transitive impact", result.transitive_impact_score),
            unsafe_allow_html=True,
        )

        st.divider()

        # -- Recommendations -------------------------------------------------
        st.markdown("#### Recommended Next Steps")
        for i, rec in enumerate(result.recommendations, 1):
            st.markdown(f"{i}. {rec}")

        st.divider()

        # -- If something goes wrong -----------------------------------------
        st.markdown("#### If something goes wrong during migration")
        for step in RECOVERY_STEPS:
            st.markdown(f"- {step}")

        st.divider()

        # -- Affected Asset Groups -------------------------------------------
        st.markdown("#### Affected Asset Groups (estimated)")
        if any(g.estimated_count > 0 for g in result.affected_groups):
            for group in result.affected_groups:
                if group.estimated_count > 0:
                    st.markdown(
                        f'<div class="asset-group-card">'
                        f"<strong>{group.asset_type}</strong>"
                        f" &nbsp;·&nbsp; ~{group.estimated_count:,} affected"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No assets are expected to be directly affected.")

    else:
        st.info(
            "Configure the migration scenario on the left and click "
            "**Simulate Migration Impact** to see results.",
            icon="👈",
        )
