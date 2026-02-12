"""
Atlan Impact Simulators — Launcher

A simple hub page that links to the two standalone simulator apps.

Run with:  streamlit run app.py

Or launch either app directly:
  streamlit run schema_app.py        # Schema-Change Impact Simulator
  streamlit run migration_app.py     # Databricks Migration Impact Simulator
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

col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("### Schema-Change Simulator")
    st.markdown(
        "Simulate the blast radius of a proposed schema change "
        "(drop/rename column, change data type, deprecate table) "
        "on downstream assets."
    )
    st.code("streamlit run schema_app.py", language="bash")

with col2:
    st.markdown("### Databricks Migration Simulator")
    st.markdown(
        "Simulate the impact of a Databricks workspace or tenant "
        "migration on an existing Atlan Databricks connector."
    )
    st.code("streamlit run migration_app.py", language="bash")

st.divider()
st.markdown(
    "*Launch either app from your terminal using the commands above, "
    "or run them on different ports simultaneously:*"
)
st.code(
    "streamlit run schema_app.py --server.port 8501\n"
    "streamlit run migration_app.py --server.port 8502",
    language="bash",
)
