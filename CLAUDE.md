# Schema-Change Impact Simulator

## What is this?
A hackathon prototype that simulates the blast radius of a proposed schema change (drop/rename column, change data type, deprecate table). It uses mocked lineage data and heuristic risk scoring to show downstream assets that would be affected, compute a risk score, and generate plain-English recommendations.

## Quick start
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Project structure
```
app.py             — Streamlit UI (single-page app)
impact_engine.py   — Core logic: mocked lineage, risk scoring, summary generation
requirements.txt   — Python dependencies (just streamlit)
```

## Key modules

### impact_engine.py
- `get_downstream_assets(qualified_name)` — returns mocked downstream assets; designed to be swapped for real Atlan API calls.
- `compute_risk_score(change_type, assets)` — heuristic 0-100 score based on criticality, directness, recency, and change type.
- `generate_summary(...)` — produces English blast-radius summary and recommendations list.
- `simulate(qualified_name, change_type, context)` — end-to-end orchestrator returning an `ImpactResult`.

### app.py
- Two-column Streamlit layout: left = inputs, right = results.
- Uses custom CSS for risk badges and asset cards.
- Three pre-loaded example assets; also supports custom qualified names.

## Conventions
- Python 3.10+ (uses `X | Y` union syntax in type hints via `__future__.annotations`).
- No external API calls in the current version — all data is mocked.
- Risk levels: Critical (>=75), High (>=50), Medium (>=25), Low (<25).
- Change type weights: Drop column = 1.0, Rename = 0.7, Change data type = 0.6, Deprecate table = 1.0.

## How to extend
1. **Connect to Atlan**: Replace the body of `get_downstream_assets()` with an HTTP call to the Atlan lineage API and map the response to `DownstreamAsset` objects.
2. **Add change types**: Add entries to `CHANGE_TYPES` and `RISK_WEIGHTS` in `impact_engine.py`, then add a recommendation branch in `generate_summary()`.
3. **Improve scoring**: Tune weights in `CRITICALITY_WEIGHTS`, `RISK_WEIGHTS`, or the normalization constant in `compute_risk_score()`.
