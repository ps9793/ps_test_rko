# Databricks Migration Impact Simulator

## What is this?
A hackathon prototype that simulates the blast radius of a Databricks workspace / tenant migration on an existing Atlan Databricks connector (crawler). It uses rule-based heuristics and mocked asset data to estimate which assets will be archived, duplicated, or preserved, compute a risk score, and generate plain-English recommendations suitable for sharing with customers.

## Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Project structure
```
app.py             — Streamlit UI (single-page, two-column layout)
impact_engine.py   — Core logic: rule engine, risk scoring, summary generation
requirements.txt   — Python dependencies (just streamlit)
```

## Key modules

### impact_engine.py
- `MigrationConfig` — dataclass collecting all UI inputs (asset counts, change type, metastore/connection flags, permissions, etc.).
- `ImpactResult` — dataclass with estimated archived/duplicated/preserved counts, direct/transitive/overall risk scores, summary text, recommendations, and affected asset groups.
- `simulate(cfg)` — end-to-end orchestrator: asset-count estimation -> scoring -> summary -> recommendations.
- `_compute_asset_counts(cfg)` — rule-based logic branching by migration scenario to estimate archived, duplicated, and preserved assets.
- `_compute_scores(cfg, archived, duplicated)` — computes direct impact, transitive impact, and overall risk scores (0-100).
- `_generate_summary(cfg, result)` — produces plain-English blast-radius summary.
- `_generate_recommendations(cfg, result)` — returns 3-5 actionable next steps tailored to the scenario.

### app.py
- Two-column Streamlit layout: left = migration configuration inputs, right = results.
- Uses custom CSS for risk badges, impact chips, and asset group cards.
- Collects current connection details, planned migration characteristics, and optional customer notes.
- Renders headline metrics, risk score ring, blast radius summary, direct/transitive impact chips, recommendations, and affected asset groups.

## Migration scenarios modeled
1. **Hostname update** — same metastore, reuse connection. Low structural risk; mainly connectivity/permissions.
2. **Interim workspace** — existing connection pointed to smaller estate. High archive risk.
3. **New connection (same metastore)** — duplication risk from overlapping assets under different qualified names.
4. **New account + new metastore** — maximum structural change. Near-full archive + duplication if old connection kept.
5. **Complex / multi-workspace** — highest baseline risk with partial archive + duplication.

## Conventions
- Python 3.10+ (uses `X | Y` union syntax in type hints via `__future__.annotations`).
- No external API calls — all data is mocked for the hackathon.
- Risk levels: Critical (>=75), High (>=50), Medium (>=25), Low (<25).
- Scenario base risk multipliers defined in `SCENARIO_BASE_RISK` dict.
- Asset-type distribution mocked via `ASSET_TYPE_DISTRIBUTION` (Tables 45%, Views 20%, Dashboards 15%, Models 10%, Queries 10%).

## How to extend
1. **Connect to Atlan**: Replace mocked asset counts with real Atlan API calls to fetch crawler metadata and asset inventories.
2. **Add scenarios**: Add entries to `CHANGE_TYPES`, `CHANGE_TYPE_LABELS`, and `SCENARIO_BASE_RISK` in `impact_engine.py`, then add a rule branch in `_compute_asset_counts()` and a recommendation branch in `_generate_recommendations()`.
3. **Improve scoring**: Tune weights in `SCENARIO_BASE_RISK`, the direct/transitive formulas in `_compute_scores()`, or the environment multipliers.
4. **Real asset groups**: Replace `ASSET_TYPE_DISTRIBUTION` with actual asset-type counts from the Atlan catalog.
