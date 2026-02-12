"""
Atlan Impact Simulators — Launcher Hub

The main entry point for the RKO hackathon site.  Streamlit's multipage
feature auto-discovers pages in the ``pages/`` directory and adds them to
the sidebar.  This hub provides a visual overview and quick links.

Run with:  streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Atlan Impact Simulators",
    page_icon="🎯",
    layout="centered",
)

st.title("Atlan Impact Simulators")
st.caption("Hackathon prototypes — pick a simulator to launch.")
st.divider()

# ---------------------------------------------------------------------------
# Utilities section — primary entry points
# ---------------------------------------------------------------------------
st.markdown("## Utilities")

col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("### Schema-Change Impact Simulator")
    st.markdown(
        "Assess the blast radius of a proposed schema change "
        "(drop/rename table, change column type, deprecate table) "
        "on downstream assets — powered by your Snowflake data."
    )
    # st.page_link navigates within the multipage app (Streamlit >= 1.31).
    st.page_link(
        "pages/1_Schema_Change_Impact_Simulator.py",
        label="Open Schema-Change Simulator",
        icon="🔍",
    )

with col2:
    st.markdown("### Databricks Migration Simulator")
    st.markdown(
        "Simulate the impact of a Databricks workspace or tenant "
        "migration on an existing Atlan Databricks connector."
    )
    st.code("streamlit run migration_app.py", language="bash")

st.divider()

# ---------------------------------------------------------------------------
# Quick-start instructions
# ---------------------------------------------------------------------------
st.markdown("## Quick Start")
st.markdown(
    "The **Schema-Change Impact Simulator** is integrated directly — "
    "click the link above or use the sidebar.  "
    "The Databricks Migration Simulator can be launched from the terminal:"
)
st.code(
    "streamlit run migration_app.py --server.port 8502",
    language="bash",
)

st.divider()

# ---------------------------------------------------------------------------
# Environment setup hint
# ---------------------------------------------------------------------------
st.markdown("## Snowflake Configuration")
st.markdown(
    "To connect the Schema-Change simulator to real Snowflake data, "
    "set the following environment variables before launching:"
)
st.code(
    "export SNOWFLAKE_ACCOUNT=xy12345.us-east-1\n"
    "export SNOWFLAKE_USER=your_user\n"
    "export SNOWFLAKE_PASSWORD=your_password\n"
    "export SNOWFLAKE_WAREHOUSE=COMPUTE_WH\n"
    "export SNOWFLAKE_DATABASE=ANALYTICS\n"
    "export SNOWFLAKE_ROLE=ANALYST_ROLE   # optional",
    language="bash",
)
st.markdown(
    "If these are not set, the simulator will still work using **mock data** "
    "for demo purposes."
)
