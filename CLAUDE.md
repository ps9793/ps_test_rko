# Atlan Impact Simulators

## What is this?
Two hackathon prototypes that simulate the blast radius of changes to data assets in Atlan:

1. **Schema-Change Impact Simulator** — simulates what happens when you drop/rename a column, change a data type, or deprecate a table. Uses mocked lineage data and heuristic risk scoring.
2. **Databricks Migration Impact Simulator** — simulates the impact of Databricks workspace/tenant migrations on an existing Atlan connector. Uses rule-based heuristics and mocked asset data.

## Quick start
```bash
pip install -r requirements.txt

# Launch either app directly:
streamlit run schema_app.py          # Schema-Change simulator
streamlit run migration_app.py       # Databricks Migration simulator

# Or run both on different ports:
streamlit run schema_app.py --server.port 8501
streamlit run migration_app.py --server.port 8502

# Or open the launcher hub:
streamlit run app.py
```

## Project structure
```
app.py               — Launcher hub page (links to both apps)
schema_app.py        — Streamlit UI for Schema-Change simulator
schema_engine.py     — Core logic: mocked lineage, risk scoring, summary generation
migration_app.py     — Streamlit UI for Databricks Migration simulator
migration_engine.py  — Core logic: rule engine, risk scoring, summary generation
requirements.txt     — Python dependencies (just streamlit)
```

## App 1: Schema-Change Impact Simulator

### Key functions (schema_engine.py)
- `get_downstream_assets(qualified_name)` — returns mocked downstream assets; designed to be swapped for real Atlan API calls.
- `compute_risk_score(change_type, assets)` — heuristic 0-100 score based on criticality, directness, recency, and change type.
- `generate_summary(...)` — produces English blast-radius summary and recommendations list.
- `simulate(qualified_name, change_type, context)` — end-to-end orchestrator returning an `ImpactResult`.

### UI (schema_app.py)
- Two-column Streamlit layout: left = inputs, right = results.
- Three pre-loaded example assets; also supports custom qualified names.
- Change types: Drop column, Rename column, Change data type, Deprecate table.

## App 2: Databricks Migration Impact Simulator

### Key functions (migration_engine.py)
- `MigrationConfig` — dataclass collecting all UI inputs (asset counts, change type, metastore/connection flags, permissions, etc.).
- `ImpactResult` — dataclass with archived/duplicated/preserved counts, direct/transitive/overall risk scores, summary, recommendations, and affected asset groups.
- `simulate(cfg)` — end-to-end orchestrator: asset-count estimation -> scoring -> summary -> recommendations.

### Migration scenarios modeled
1. **Hostname update** — same metastore, reuse connection. Low structural risk.
2. **Interim workspace** — existing connection pointed to smaller estate. High archive risk.
3. **New connection (same metastore)** — duplication risk from overlapping assets.
4. **New account + new metastore** — maximum structural change.
5. **Complex / multi-workspace** — highest baseline risk.

### UI (migration_app.py)
- Two-column layout: left = migration configuration, right = results.
- Collects current connection details, migration characteristics, and optional customer notes.
- Renders headline metrics, risk score, blast radius summary, impact chips, recommendations, and affected asset groups.

## Conventions
- Python 3.10+ (uses `X | Y` union syntax in type hints via `__future__.annotations`).
- No external API calls — all data is mocked for the hackathon.
- Risk levels: Critical (>=75), High (>=50), Medium (>=25), Low (<25).
- Each app has its own engine module — no cross-imports between the two simulators.

## How to extend
1. **Connect to Atlan**: Replace mocked data with real Atlan API calls in the engine modules.
2. **Add change types / scenarios**: Add entries to the relevant constants and add rule branches in the engine.
3. **Improve scoring**: Tune weights and normalization constants in the engine modules.
