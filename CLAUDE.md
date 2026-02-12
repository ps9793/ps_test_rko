# Atlan Impact Simulators

## What is this?
Two hackathon prototypes that simulate the blast radius of changes to data assets in Atlan:

1. **Schema-Change Impact Simulator** — simulates what happens when you drop/rename a table, change a column type, or deprecate a table. Queries Snowflake's PRERNA schema for real downstream dependencies; falls back to mock data when Snowflake is not configured.
2. **Databricks Migration Impact Simulator** — simulates the impact of Databricks workspace/tenant migrations on an existing Atlan connector. Uses rule-based heuristics and mocked asset data.

## Quick start
```bash
pip install -r requirements.txt

# Launch the hub (includes the Schema-Change simulator as a built-in page):
streamlit run app.py

# Or launch the Databricks Migration simulator standalone:
streamlit run migration_app.py --server.port 8502

# The original standalone schema app still works too:
streamlit run schema_app.py
```

### Snowflake configuration (optional)
To connect the Schema-Change simulator to real Snowflake data, set these
environment variables before launching:
```bash
export SNOWFLAKE_ACCOUNT=xy12345.us-east-1
export SNOWFLAKE_USER=your_user
export SNOWFLAKE_PASSWORD=your_password
export SNOWFLAKE_WAREHOUSE=COMPUTE_WH
export SNOWFLAKE_DATABASE=ANALYTICS
export SNOWFLAKE_ROLE=ANALYST_ROLE   # optional
```
If these are not set, the simulator uses **deterministic mock data** — the UI
still works for demos without a live Snowflake connection.

## Project structure
```
app.py                                       — Launcher hub (multipage home)
pages/
  1_Schema_Change_Impact_Simulator.py        — Integrated Schema-Change simulator page
schema_impact_engine.py                      — Snowflake-backed engine: risk scoring, summary
snowflake_client.py                          — Snowflake connection & INFORMATION_SCHEMA queries
schema_app.py                                — Original standalone Schema-Change simulator UI
schema_engine.py                             — Original engine: mocked lineage, risk scoring
migration_app.py                             — Standalone Databricks Migration simulator UI
migration_engine.py                          — Migration engine: rule engine, risk scoring
requirements.txt                             — Python deps (streamlit, snowflake-connector-python)
```

## App 1: Schema-Change Impact Simulator (integrated)

### Integrated page (pages/1_Schema_Change_Impact_Simulator.py)
Accessible from the hub sidebar or the "Utilities" card on the home page.

**Inputs (left column):**
- Asset qualified name (text input + example dropdown).
- Change type: Rename table, Drop table, Deprecate table, Change column type, Drop column.
- Scope: Single table / Entire schema.
- Environment: Prod / Non-prod.
- "Assess Impact" button.

**Outputs (right column):**
- Headline metrics: Estimated impacted downstream assets, Depth (max hops), Risk band.
- Risk score ring (0–100) with color-coded badge.
- Blast-radius summary (1–3 sentences).
- Recommended next steps (scenario-specific bullets).
- Data source indicator (Snowflake connected vs mock data).

### Key functions (schema_impact_engine.py)
- `simulate(qualified_name, change_type, scope, environment)` — end-to-end orchestrator; tries Snowflake, falls back to mock.
- `compute_risk_score(change_type, downstream_count)` — rule-based 0–100 score (see risk model below).
- `_generate_summary(...)` / `_generate_recommendations(...)` — English text generation.

### Snowflake client (snowflake_client.py)
- `SnowflakeClient` — reads config from env vars; connects via `snowflake-connector-python`.
- `get_downstream_dependencies(table_name, schema_name)` — scans `INFORMATION_SCHEMA.VIEWS` for references.
- Target schema is hardcoded as `PRERNA` (constant `PRERNA_SCHEMA` in `schema_impact_engine.py`).

### Risk model (schema changes)
```
risk = base + bonus
```
- `base` = 70 (breaking: Drop table/column, Change column type) | 30 (soft: Rename, Deprecate)
- `bonus` = +10 if downstream_count > 10 | +20 if downstream_count > 100
- Capped at 100, always an integer.
- Bands: 0–29 = Low, 30–59 = Medium, 60+ = High.

### Demo example
A valid `asset_qualified_name` from the PRERNA schema:
```
default/snowflake/123/ANALYTICS/PRERNA/FCT_ORDERS
```

### Original standalone app (schema_app.py + schema_engine.py)
Still works as before — uses mocked lineage data. Run with `streamlit run schema_app.py`.

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
- Schema-Change simulator connects to Snowflake when env vars are set; falls back to mock data.
- Databricks Migration simulator uses mock data only (no external API calls).
- Risk levels: High (>60), Medium (30–60), Low (<30).
- Each app has its own engine module — no cross-imports between the two simulators.

## How to extend
1. **Connect to Atlan**: Replace mocked data with real Atlan API calls in the engine modules.
2. **Add change types / scenarios**: Add entries to the relevant constants and add rule branches in the engine.
3. **Improve scoring**: Tune weights and normalization constants in the engine modules.
4. **Add lineage table**: If a dedicated lineage table is available in the PRERNA schema, update `snowflake_client.py` to query it instead of scanning `INFORMATION_SCHEMA.VIEWS`.
