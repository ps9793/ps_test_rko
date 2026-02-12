"""
Schema-Change Impact Simulator — Streamlit UI

Run with:  streamlit run schema_app.py
"""

import streamlit as st
from schema_engine import CHANGE_TYPES, ImpactResult, simulate

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Schema-Change Impact Simulator",
    page_icon="🔍",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Custom CSS for a polished look
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
    .risk-none     { background: #f0f9ff; color: #075985; border: 1px solid #7dd3fc; }

    .asset-card {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 10px;
    }

    .score-ring {
        font-size: 3rem;
        font-weight: 800;
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Schema-Change Impact Simulator")
st.caption("Simulate who you'll break before you change schemas.")
st.divider()

# ---------------------------------------------------------------------------
# Pre-loaded example assets for the selectbox
# ---------------------------------------------------------------------------
EXAMPLE_ASSETS = [
    "default/snowflake/123/ANALYTICS/FCT_ORDERS/total_amount",
    "default/snowflake/123/ANALYTICS/DIM_CUSTOMERS/email",
    "default/snowflake/123/ANALYTICS/FCT_PAYMENTS/payment_method",
    "(custom — type your own below)",
]

# ---------------------------------------------------------------------------
# Input panel
# ---------------------------------------------------------------------------
col_input, col_results = st.columns([1, 2], gap="large")

with col_input:
    st.subheader("Configuration")

    selected_example = st.selectbox(
        "Pick an example asset or choose custom",
        EXAMPLE_ASSETS,
    )

    if selected_example == "(custom — type your own below)":
        qualified_name = st.text_input(
            "Asset qualified name",
            placeholder="default/snowflake/123/SCHEMA/TABLE/column",
        )
    else:
        qualified_name = st.text_input(
            "Asset qualified name",
            value=selected_example,
        )

    change_type = st.selectbox("Change type", CHANGE_TYPES)

    context = st.text_area(
        "Context / reason for change (optional)",
        placeholder="e.g. Migrating to new naming convention…",
        height=80,
    )

    simulate_clicked = st.button("Simulate", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Helper renderers
# ---------------------------------------------------------------------------

RISK_CSS_CLASS = {
    "Critical": "risk-critical",
    "High": "risk-high",
    "Medium": "risk-medium",
    "Low": "risk-low",
    "None": "risk-none",
    "Unknown": "risk-none",
}

CRITICALITY_ICON = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🟢",
}


def _render_risk_badge(level: str) -> str:
    css = RISK_CSS_CLASS.get(level, "risk-none")
    return f'<span class="risk-badge {css}">{level} Risk</span>'


def _render_score(result: ImpactResult) -> None:
    """Big score + badge in the centre."""
    css = RISK_CSS_CLASS.get(result.risk_level, "risk-none")
    color_map = {
        "risk-critical": "#dc2626",
        "risk-high": "#ea580c",
        "risk-medium": "#ca8a04",
        "risk-low": "#16a34a",
        "risk-none": "#0284c7",
    }
    color = color_map.get(css, "#64748b")
    st.markdown(
        f'<p class="score-ring" style="color:{color}">{result.risk_score}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='text-align:center'>{_render_risk_badge(result.risk_level)}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<p style='text-align:center;color:#64748b;font-size:.85rem'>out of 100</p>",
        unsafe_allow_html=True,
    )


def _render_asset_table(result: ImpactResult) -> None:
    """Render downstream assets as styled cards."""
    for asset in result.downstream_assets:
        icon = CRITICALITY_ICON.get(asset.criticality, "⚪")
        dep_tag = "Direct" if asset.direct else "Transitive"
        st.markdown(
            f"""<div class="asset-card">
                <strong>{icon} {asset.name}</strong>
                &nbsp;·&nbsp;<code>{asset.asset_type}</code>
                &nbsp;·&nbsp;{dep_tag}
                &nbsp;·&nbsp;Criticality: <strong>{asset.criticality}</strong>
                <br/>
                <span style="color:#64748b;font-size:.85rem">
                    Owner: {asset.owner} &nbsp;|&nbsp; Last queried: {asset.last_queried_days_ago}d ago
                </span>
                <br/>
                <span style="color:#475569;font-size:.85rem">{asset.description}</span>
            </div>""",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Results panel
# ---------------------------------------------------------------------------

with col_results:
    if simulate_clicked:
        if not qualified_name:
            st.warning("Please enter an asset qualified name.")
        else:
            with st.spinner("Simulating impact…"):
                result = simulate(qualified_name, change_type, context)

            st.subheader("Impact Results")

            # -- Top metrics row -------------------------------------------
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Downstream Assets", len(result.downstream_assets))
            m2.metric(
                "Direct",
                sum(1 for a in result.downstream_assets if a.direct),
            )
            m3.metric(
                "Transitive",
                sum(1 for a in result.downstream_assets if not a.direct),
            )
            m4.metric(
                "Critical",
                sum(
                    1
                    for a in result.downstream_assets
                    if a.criticality == "critical"
                ),
            )

            st.divider()

            # -- Score + summary -------------------------------------------
            score_col, summary_col = st.columns([1, 2])

            with score_col:
                st.markdown("#### Risk Score")
                _render_score(result)

            with summary_col:
                st.markdown("#### Blast Radius Summary")
                st.markdown(result.summary)

            st.divider()

            # -- Recommendations -------------------------------------------
            st.markdown("#### Recommended Next Steps")
            for i, rec in enumerate(result.recommendations, 1):
                st.markdown(f"{i}. {rec}")

            st.divider()

            # -- Detailed asset list ---------------------------------------
            st.markdown("#### Affected Downstream Assets")
            _render_asset_table(result)

    else:
        st.info(
            "Configure a schema change on the left and click **Simulate** to see the impact.",
            icon="👈",
        )
