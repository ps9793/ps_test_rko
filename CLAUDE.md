# Atlan Impact Simulators

## What is this?

Two hackathon prototypes that simulate the blast radius of changes to data assets in Atlan:

1. **Schema-Change Impact Simulator** (`schema_app.py` + `schema_engine.py`) — simulates what happens when you drop/rename a column, change a data type, or deprecate a table. Uses mocked lineage data and heuristic risk scoring.
2. **Databricks Migration Impact Simulator** (`migration_app.py` + `migration_engine.py`) — simulates the impact of Databricks workspace/tenant migrations on an existing Atlan connector. Uses rule-based heuristics and mocked asset data.

Both apps are standalone Streamlit applications with no cross-imports between them.

## Quick start

```bash
# Install dependencies (only streamlit)
pip install -r requirements.txt

# Launch either app directly:
streamlit run schema_app.py          # Schema-Change simulator (default: port 8501)
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
schema_app.py        — Streamlit UI for Schema-Change simulator (246 lines)
schema_engine.py     — Core logic: mocked lineage, risk scoring, summary generation (390 lines)
migration_app.py     — Streamlit UI for Databricks Migration simulator (361 lines)
migration_engine.py  — Core logic: rule engine, risk scoring, summary generation (471 lines)
requirements.txt     — Python dependencies (streamlit>=1.30.0)
CLAUDE.md            — This file
.gitignore           — Ignores __pycache__/ and *.pyc
```

There are no tests, CI configuration, or additional config files (pyproject.toml, setup.cfg, etc.).

## Architecture

### Pattern: UI + Engine separation

Each simulator follows the same pattern:
- **`*_app.py`** — Streamlit UI layer. Handles page config, CSS, layout, input widgets, and result rendering. Imports only from its paired engine module.
- **`*_engine.py`** — Pure logic layer. Defines dataclasses, constants, scoring functions, summary generators, and a top-level `simulate()` orchestrator. No Streamlit imports.

The `app.py` launcher hub is a simple Streamlit page that describes both apps and shows how to run them. It does not import from either engine.

### Data flow

```
User input (Streamlit widgets)
  -> simulate() orchestrator (engine module)
    -> compute asset counts / downstream assets
    -> compute risk score
    -> generate English summary + recommendations
    -> return ImpactResult dataclass
  -> render results (Streamlit UI)
```

---

## App 1: Schema-Change Impact Simulator

### Data model (`schema_engine.py`)

```python
@dataclass
class DownstreamAsset:
    name: str
    asset_type: str           # Dashboard | Report | ML Model | dbt Model | View | Scheduled Query
    owner: str
    criticality: str          # critical | high | medium | low
    direct: bool = True       # direct vs transitive dependency
    last_queried_days_ago: int = 1
    description: str = ""

@dataclass
class ImpactResult:
    source_asset: str
    change_type: str
    downstream_assets: list[DownstreamAsset]
    risk_score: float         # 0.0–100.0
    risk_level: str           # Critical | High | Medium | Low | None
    summary: str              # Markdown paragraph
    recommendations: list[str]
```

### Constants

| Constant | Purpose |
|---|---|
| `CHANGE_TYPES` | `["Drop column", "Rename column", "Change data type", "Deprecate table"]` |
| `ASSET_TYPES` | 6 downstream asset types (Dashboard, Report, ML Model, dbt Model, View, Scheduled Query) |
| `RISK_WEIGHTS` | Change-type multipliers: Drop=1.0, Rename=0.7, Data type=0.6, Deprecate=1.0 |
| `CRITICALITY_WEIGHTS` | critical=1.0, high=0.75, medium=0.5, low=0.25 |

### Key functions (`schema_engine.py`)

- **`get_downstream_assets(qualified_name)`** — Returns mocked downstream assets from `_MOCK_LINEAGE` dict (3 pre-built example assets). Falls back to `_deterministic_fallback()` which uses MD5 hash to generate 1–4 deterministic mock assets for any unknown qualified name. Designed to be swapped for real Atlan API calls.
- **`compute_risk_score(change_type, downstream_assets)`** — Returns `(score: float, level: str)`. Heuristic 0–100 score based on criticality, directness, recency (90-day window), and change-type multiplier. Normalization assumes 5 critical direct recent assets = 100.
- **`generate_summary(source_asset, change_type, downstream_assets, risk_score, risk_level, context)`** — Returns `(summary: str, recommendations: list[str])`. Produces Markdown blast-radius paragraph and tailored recommendations.
- **`simulate(qualified_name, change_type, context)`** — End-to-end orchestrator. Returns `ImpactResult`.

### Risk scoring formula (schema)

```
per_asset_score = criticality_weight * directness_weight * (0.5 + 0.5 * recency_factor)
  where:
    criticality_weight = {critical: 1.0, high: 0.75, medium: 0.5, low: 0.25}
    directness_weight  = 1.0 (direct) | 0.5 (transitive)
    recency_factor     = max(0, 1 - last_queried_days_ago / 90)

total = sum of per_asset_scores
score = min((total / 5.0) * 100 * change_type_weight, 100)
```

Risk levels: Critical (>=75), High (>=50), Medium (>=25), Low (<25), None (no assets).

### UI (`schema_app.py`)

- Two-column Streamlit layout: left = inputs (1/3 width), right = results (2/3 width).
- Three pre-loaded example qualified names from `_MOCK_LINEAGE`; also supports custom input.
- Custom CSS classes for risk badges (`risk-critical`, `risk-high`, `risk-medium`, `risk-low`, `risk-none`) and asset cards.
- Results panel: 4 headline metrics, risk score ring with color, blast radius summary, numbered recommendations, styled asset cards with criticality icons.

### Mocked lineage data

Three pre-built assets in `_MOCK_LINEAGE`:

| Qualified Name | Downstream Count | Critical Assets |
|---|---|---|
| `default/snowflake/123/ANALYTICS/FCT_ORDERS/total_amount` | 5 | Revenue Dashboard |
| `default/snowflake/123/ANALYTICS/DIM_CUSTOMERS/email` | 3 | Marketing Campaign Scheduler, PII Compliance Report |
| `default/snowflake/123/ANALYTICS/FCT_PAYMENTS/payment_method` | 2 | Fraud Detection Model |

---

## App 2: Databricks Migration Impact Simulator

### Data model (`migration_engine.py`)

```python
@dataclass
class MigrationConfig:
    current_assets: int
    new_assets: int
    scenario: str              # one of SCENARIOS
    same_metastore: bool
    is_prod: bool
    overlap_pct: float | None  # 0–1, only for new-connection scenario
    crawler_perms: str         # "same" | "broader" | "narrower"
    interim_subset: bool
    customer_notes: str = ""

@dataclass
class AffectedAssetGroup:
    asset_type: str
    estimated_count: int

@dataclass
class ImpactResult:
    archived_assets: int = 0
    duplicated_assets: int = 0
    preserved_assets: int = 0
    risk_score: int = 0                # 0–100 integer
    direct_impact_score: int = 0       # 0–100 integer
    transitive_impact_score: int = 0   # 0–100 integer
    risk_level: str = "Low"            # Low | Medium | High
    summary: str = ""
    recommendations: list[str]
    notes: list[str]
    affected_groups: list[AffectedAssetGroup]
    scenario_label: str = ""
    customer_notes: str = ""
```

### Migration scenarios

| # | Scenario | Base Risk | Primary Risk Type |
|---|---|---|---|
| 1 | Update hostname/URL on existing connection (same metastore) | 20 | Minimal — just a URL swap |
| 2 | Point existing connection to new workspace (same metastore) | 55 | **Loss** — assets not in new workspace get archived |
| 3 | Create new Databricks connection to new workspace | 65 | **Duplication** — overlapping assets appear twice |

### Risk model (migration)

```
risk = base(scenario) + 40 * lost_pct + 40 * dup_pct + prod_bonus + perms_adj
```

Where:
- `base` = 20 (hostname) | 55 (re-point) | 65 (new connection)
- `lost_pct` = archived_assets / current_assets (0–1)
- `dup_pct` = duplicated_assets / current_assets (0–1)
- `prod_bonus` = +10 if production tenant, else 0
- `perms_adj` = +5 (narrower) | -5 (broader) | 0 (same)

Risk levels: High (>60), Medium (30–60), Low (<30). Score is always an integer clamped to 0–100.

**When `duplicated_assets > 0`:** Only in the "Create new connection" scenario AND `same_metastore == True` AND `overlap_pct > 0`. All other scenarios have `duplicated_assets = 0`.

### Direct and transitive impact scores

```
direct_raw       = (lost_pct + dup_pct) * 80 + prod_bonus
direct_score     = clamp(round(direct_raw), 0, 100)

log_scale        = min(log10(max(current_assets, 10)) / 7, 1)
transitive_raw   = direct_raw * 0.7 * log_scale
transitive_score = clamp(round(transitive_raw), 0, 100)
```

### Key functions (`migration_engine.py`)

- **`_compute_asset_counts(cfg)`** — Returns `(archived, duplicated, preserved, notes)`. Applies scenario-specific rules to estimate asset counts.
- **`_compute_scores(cfg, archived, duplicated)`** — Returns `(risk_score, direct_score, transitive_score)` as integers 0–100.
- **`_build_affected_groups(archived, duplicated, preserved)`** — Proportional breakdown using `ASSET_TYPE_DISTRIBUTION` (Tables 45%, Views 20%, Dashboards 15%, Models 10%, Queries 10%).
- **`_generate_summary(cfg, result)`** — Plain-English blast-radius paragraph with scenario label, affected counts/percentages, risk type explanation.
- **`_generate_recommendations(cfg, result)`** — Scenario-specific actionable guidance.
- **`simulate(cfg)`** — End-to-end orchestrator. Returns `ImpactResult`.

### UI (`migration_app.py`)

- Two-column layout: left = migration configuration (1/3), right = results (2/3).
- **Conditional inputs** based on scenario selection:
  - `new_assets` number input: appears for scenarios 2 and 3
  - `overlap_pct` slider: appears only for scenario 3 (new connection)
  - `interim_subset` checkbox: appears only for scenario 2 (re-point)
- Results panel: 4 headline metrics (archived/duplicated/preserved/risk), score ring, blast radius summary, direct/transitive impact chips, numbered recommendations, recovery guidance (`RECOVERY_STEPS`), affected asset group cards.

---

## Conventions

### Language and runtime
- Python 3.10+ required (uses `X | Y` union syntax in type hints via `from __future__ import annotations`).
- Single dependency: `streamlit>=1.30.0`.

### Code style
- Docstrings on all public functions and dataclasses.
- Module-level constants in `UPPER_SNAKE_CASE`.
- Private helpers prefixed with `_` (e.g., `_compute_asset_counts`, `_deterministic_fallback`).
- Section separators using `# ---` comment blocks.
- Custom CSS embedded directly in `st.markdown()` calls using `unsafe_allow_html=True`.

### Architecture rules
- **No cross-imports** between the two simulators. Each app is self-contained with its own engine.
- **Engine modules have no Streamlit imports.** All UI logic stays in `*_app.py` files.
- **No external API calls.** All data is mocked for the hackathon.
- **Dataclasses** are the primary data containers (no Pydantic or attrs).
- **Risk levels differ between apps:**
  - Schema: Critical (>=75), High (>=50), Medium (>=25), Low (<25)
  - Migration: High (>60), Medium (30–60), Low (<30)

### Git conventions
- Commit messages are descriptive and explain the "why" (e.g., "Fix risk scoring: zero-impact migrations now score near-zero").
- No CI/CD pipeline configured.
- No test suite.

---

## How to extend

1. **Connect to Atlan API**: Replace mocked data in engine modules with real Atlan API calls. In `schema_engine.py`, swap `get_downstream_assets()`. In `migration_engine.py`, replace hardcoded asset-type distributions with real catalog metadata.
2. **Add change types / scenarios**: Add entries to `CHANGE_TYPES` or `SCENARIOS` constants and add corresponding rule branches in `compute_risk_score` / `_compute_asset_counts` and recommendation logic.
3. **Improve scoring**: Tune weights and normalization constants in the engine modules. The schema engine normalizes against 5 assets; the migration engine uses a formula with configurable base scores.
4. **Add tests**: No tests exist yet. Engine modules are pure functions with dataclass I/O, making them straightforward to unit test.
5. **Add new UI sections**: Follow the existing pattern of rendering helpers (e.g., `_render_risk_badge`, `_chip_html`) and conditional layout blocks.
