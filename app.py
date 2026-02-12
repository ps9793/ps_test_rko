"""
Databricks Migration Impact Simulator — Streamlit UI

Helps Atlan users simulate the impact of Databricks workspace / tenant
migrations on an existing Atlan Databricks connector (crawler).

Run with:  streamlit run app.py
"""

import streamlit as st
from impact_engine import (
    CHANGE_TYPES,
    ENVIRONMENTS,
    PERMISSION_OPTIONS,
    ImpactResult,
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
    .risk-critical { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
    .risk-high     { background: #fff7ed; color: #9a3412; border: 1px solid #fdba74; }
    .risk-medium   { background: #fefce8; color: #854d0e; border: 1px solid #fde047; }
    .risk-low      { background: #f0fdf4; color: #166534; border: 1px solid #86efac; }

    .impact-chip {
        display: inline-block;
        padding: 6px 14px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        margin-right: 12px;
        margin-bottom: 8px;
    }
    .chip-critical { background: #fee2e2; color: #991b1b; }
    .chip-high     { background: #fff7ed; color: #9a3412; }
    .chip-medium   { background: #fefce8; color: #854d0e; }
    .chip-low      { background: #f0fdf4; color: #166534; }

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
    "Critical": "risk-critical",
    "High": "risk-high",
    "Medium": "risk-medium",
    "Low": "risk-low",
}
RISK_COLOR = {
    "Critical": "#dc2626",
    "High": "#ea580c",
    "Medium": "#ca8a04",
    "Low": "#16a34a",
}
CHIP_CSS = {
    "Critical": "chip-critical",
    "High": "chip-high",
    "Medium": "chip-medium",
    "Low": "chip-low",
}


def _risk_badge_html(level: str) -> str:
    css = RISK_CSS.get(level, "risk-low")
    return f'<span class="risk-badge {css}">{level} Risk</span>'


def _chip_html(label: str, score: float) -> str:
    if score >= 75:
        lvl = "Critical"
    elif score >= 50:
        lvl = "High"
    elif score >= 25:
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

    environment = st.selectbox("Environment", ENVIRONMENTS)

    high_crit_pct = st.slider(
        "% of assets tagged as high-criticality",
        min_value=0,
        max_value=100,
        value=15,
    )

    st.markdown("---")

    # --- Planned migration --------------------------------------------------
    st.markdown("##### Planned Migration")

    change_type = st.selectbox("Migration scenario", CHANGE_TYPES)

    same_metastore = st.radio(
        "Will the Unity Catalog metastore stay the same?",
        ["Yes", "No"],
        horizontal=True,
    ) == "Yes"

    same_workspace_url = st.radio(
        "Will the workspace URL stay the same?",
        ["Same", "Different"],
        horizontal=True,
    ) == "Same"

    reuse_connection = st.radio(
        "Will you reuse the same Atlan connection?",
        ["Yes", "No"],
        horizontal=True,
    ) == "Yes"

    new_assets = st.number_input(
        "Estimated assets in new workspace at cutover",
        min_value=0,
        max_value=50_000_000,
        value=current_assets,
        step=10_000,
        format="%d",
    )

    crawler_perms = st.selectbox(
        "Crawler credential permissions",
        PERMISSION_OPTIONS,
        format_func=lambda x: x.capitalize(),
    )

    interim_workspace = st.checkbox(
        "Interim workspace with a strict subset of the final catalogs"
    )

    st.markdown("---")

    # --- Optional qualitative -----------------------------------------------
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
            change_type=change_type,
            environment=environment,
            high_criticality_pct=float(high_crit_pct),
            same_metastore=same_metastore,
            same_workspace_url=same_workspace_url,
            reuse_connection=reuse_connection,
            crawler_perms=crawler_perms,
            interim_workspace=interim_workspace,
            customer_notes=customer_notes,
        )

        with st.spinner("Simulating migration impact…"):
            result = simulate(cfg)

        st.subheader("Impact Results")

        # -- Headline metrics ------------------------------------------------
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Archived Assets",
            f"{result.estimated_archived_assets:,}",
        )
        m2.metric(
            "Duplicated Assets",
            f"{result.estimated_duplicated_assets:,}",
        )
        m3.metric(
            "Preserved Assets",
            f"{result.estimated_preserved_assets:,}",
        )
        # Overall risk score with colored label
        m4.metric(
            "Risk Score",
            f"{result.overall_risk_score}/100",
        )

        st.divider()

        # -- Score ring + summary --------------------------------------------
        score_col, summary_col = st.columns([1, 2])

        with score_col:
            st.markdown("#### Overall Risk")
            color = RISK_COLOR.get(result.risk_level, "#64748b")
            st.markdown(
                f'<p class="score-ring" style="color:{color}">'
                f"{result.overall_risk_score}</p>",
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

        # -- Affected Asset Groups -------------------------------------------
        st.markdown("#### Affected Asset Groups (mocked)")
        for group in result.affected_groups:
            st.markdown(
                f'<div class="asset-group-card">'
                f"<strong>{group.asset_type}</strong>"
                f" &nbsp;·&nbsp; ~{group.estimated_count:,} affected"
                f" &nbsp;·&nbsp; {group.pct_high_criticality}% high-criticality"
                f"</div>",
                unsafe_allow_html=True,
            )

    else:
        st.info(
            "Configure the migration scenario on the left and click "
            "**Simulate Migration Impact** to see results.",
            icon="👈",
        )
