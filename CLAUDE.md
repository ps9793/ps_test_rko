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
- `MigrationConfig` — dataclass collecting all UI inputs: `current_assets`, `new_assets`, `scenario`, `same_metastore`, `is_prod`, `overlap_pct`, `crawler_perms`, `interim_subset`.
- `ImpactResult` — dataclass with archived/duplicated/preserved counts, integer risk scores (0–100), summary, recommendations, notes, and affected asset groups.
- `simulate(cfg)` — end-to-end orchestrator: asset-count estimation -> scoring -> summary -> recommendations.

### Migration scenarios modeled
1. **Update hostname/URL on existing connection (same metastore)** — reuses connection, just URL change. Low structural risk (base = 20).
2. **Point existing connection to new workspace (same metastore)** — reuses connection, but assets not in the new workspace get archived. Loss risk (base = 55).
3. **Create new Databricks connection to new workspace** — old connection stays, new one added. Duplication risk (base = 65).

### Risk model
```
risk = base(scenario) + 40 * lost_pct + 40 * dup_pct + prod_bonus + perms_adj
```
Where:
- `base` = 20 (hostname) | 55 (re-point) | 65 (new connection)
- `lost_pct` = archived_assets / current_assets (0–1)
- `dup_pct` = duplicated_assets / current_assets (0–1)
- `prod_bonus` = +10 if production tenant, else 0
- `perms_adj` = +5 (narrower) | -5 (broader) | 0 (same)

Risk levels: High (>60), Medium (30–60), Low (<30). Score is always an integer.

**When `duplicated_assets > 0`:** Only in the "Create new connection" scenario AND `same_metastore == True` AND `overlap_pct > 0`. All other scenarios have `duplicated_assets = 0`.

### UI (migration_app.py)
- Two-column layout: left = migration configuration, right = results.
- Inputs: current assets, is_prod radio, scenario dropdown, same_metastore radio, new_assets (conditional), overlap % slider (conditional), interim workspace checkbox (conditional), crawler permissions.
- Results: headline metrics, risk score ring, blast radius summary, impact chips, scenario-specific recommendations, recovery guidance, affected asset groups.

## Conventions
- Python 3.10+ (uses `X | Y` union syntax in type hints via `__future__.annotations`).
- No external API calls — all data is mocked for the hackathon.
- Risk levels: High (>60), Medium (30–60), Low (<30).
- Each app has its own engine module — no cross-imports between the two simulators.

## How to extend
1. **Connect to Atlan**: Replace mocked data with real Atlan API calls in the engine modules.
2. **Add change types / scenarios**: Add entries to the relevant constants and add rule branches in the engine.
3. **Improve scoring**: Tune weights and normalization constants in the engine modules.
