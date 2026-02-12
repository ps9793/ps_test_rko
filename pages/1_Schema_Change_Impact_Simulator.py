"""
Schema-Change Impact Simulator — Page

Integrated into the RKO site as a first-class utility via Streamlit's
multipage app feature.  Accessible from the sidebar or from the hub page.

This page queries Snowflake (via schema_impact_engine) for real downstream
dependency data from the PRERNA schema.  If Snowflake is not configured,
the engine falls back to deterministic mock data so the UI still works.
"""

import streamlit as st
from schema_impact_engine import (
    CHANGE_TYPES,
    ENV_OPTIONS,
    SCOPE_OPTIONS,
    ImpactResult,
    simulate,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Schema-Change Impact Simulator",
    page_icon="🔍",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS (reuses the existing RKO site styling patterns)
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

    .score-ring {
        font-size: 3rem;
        font-weight: 800;
        text-align: center;
    }

    .info-chip {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 8px;
        margin-bottom: 6px;
    }
    .chip-snowflake { background: #dbeafe; color: #1e40af; }
    .chip-mock      { background: #fef3c7; color: #92400e; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Schema-Change Impact Simulator")
st.caption(
    "Assess the blast radius of a proposed schema change on downstream assets "
    "— powered by your Snowflake PRERNA schema."
)
st.divider()

# ---------------------------------------------------------------------------
# Example assets for quick demo
# ---------------------------------------------------------------------------
EXAMPLE_ASSETS = [
    "default/snowflake/123/ANALYTICS/PRERNA/FCT_ORDERS",
    "default/snowflake/123/ANALYTICS/PRERNA/DIM_CUSTOMERS",
    "default/snowflake/123/ANALYTICS/PRERNA/FCT_PAYMENTS",
    "(custom — type your own below)",
]

# ---------------------------------------------------------------------------
# CSS helpers
# ---------------------------------------------------------------------------
RISK_CSS = {"High": "risk-high", "Medium": "risk-medium", "Low": "risk-low"}
RISK_COLOR = {"High": "#dc2626", "Medium": "#ca8a04", "Low": "#16a34a"}


def _risk_badge_html(level: str) -> str:
    css = RISK_CSS.get(level, "risk-low")
    return f'<span class="risk-badge {css}">{level} Risk</span>'


# ---------------------------------------------------------------------------
# Layout — two columns
# ---------------------------------------------------------------------------
col_input, col_results = st.columns([1, 2], gap="large")

# ---------------------------------------------------------------------------
# LEFT COLUMN — Inputs
# ---------------------------------------------------------------------------
with col_input:
    st.subheader("Configuration")

    # -- Asset qualified name --------------------------------------------------
    selected_example = st.selectbox(
        "Pick an example asset or choose custom",
        EXAMPLE_ASSETS,
    )

    if selected_example == "(custom — type your own below)":
        qualified_name = st.text_input(
            "Asset qualified name",
            placeholder="default/snowflake/123/DB/SCHEMA/TABLE",
        )
    else:
        qualified_name = st.text_input(
            "Asset qualified name",
            value=selected_example,
        )

    # -- Change type -----------------------------------------------------------
    change_type = st.selectbox("Change type", CHANGE_TYPES)

    # -- Scope -----------------------------------------------------------------
    scope = st.radio("Scope", SCOPE_OPTIONS, horizontal=True)

    # -- Environment -----------------------------------------------------------
    environment = st.radio("Environment", ENV_OPTIONS, horizontal=True)

    st.markdown("---")

    # -- Run button ------------------------------------------------------------
    assess_clicked = st.button(
        "Assess Impact", type="primary", use_container_width=True
    )

# ---------------------------------------------------------------------------
# RIGHT COLUMN — Outputs
# ---------------------------------------------------------------------------
with col_results:
    if assess_clicked:
        if not qualified_name:
            st.warning("Please enter an asset qualified name.")
        else:
            with st.spinner("Assessing impact…"):
                result = simulate(qualified_name, change_type, scope, environment)

            # -- Data source indicator -----------------------------------------
            if result.snowflake_connected:
                st.markdown(
                    '<span class="info-chip chip-snowflake">'
                    "Connected to Snowflake (PRERNA schema)</span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<span class="info-chip chip-mock">'
                    "Using mock data (Snowflake not configured)</span>",
                    unsafe_allow_html=True,
                )

            st.subheader("Impact Results")

            # -- Headline metrics ----------------------------------------------
            m1, m2, m3 = st.columns(3)
            m1.metric(
                "Estimated Impacted Downstream Assets",
                result.downstream_count,
            )
            m2.metric(
                "Depth (max hops)",
                result.max_depth,
            )
            m3.metric(
                "Risk Band",
                f"{result.risk_band}",
            )

            st.divider()

            # -- Score ring + summary ------------------------------------------
            score_col, summary_col = st.columns([1, 2])

            with score_col:
                st.markdown("#### Risk Score")
                color = RISK_COLOR.get(result.risk_band, "#64748b")
                st.markdown(
                    f'<p class="score-ring" style="color:{color}">'
                    f"{result.risk_score}</p>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='text-align:center'>"
                    f"{_risk_badge_html(result.risk_band)}"
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

            # -- Breakdown chips -----------------------------------------------
            st.markdown("#### Impact Breakdown")
            m_d, m_t = st.columns(2)
            m_d.metric("Direct (1-hop)", result.direct_count)
            m_t.metric("Transitive (2+ hops)", result.transitive_count)

            st.divider()

            # -- Recommended next steps ----------------------------------------
            st.markdown("#### Recommended Next Steps")
            for i, rec in enumerate(result.recommendations, 1):
                st.markdown(f"{i}. {rec}")

    else:
        st.info(
            "Configure a schema change on the left and click "
            "**Assess Impact** to see the blast radius.",
            icon="👈",
        )
