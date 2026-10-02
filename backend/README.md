# RiskLens Backend

FastAPI backend for the RiskLens financial risk management platform.

> **Milestone 3 — Fully Complete (Chunks 9–13: Simulation Engine & Grounded AI Intelligence)**
> Real time-series behavioral data, predictive forecasting, risk alerts, 5 simulation scenarios, grounded Gemini recommendations, and goal conversion.
> Strict multi-tenant isolation via JWT, deterministic caching, scoped invalidation, and zero client trace leakage.

---

## Prerequisites

| Requirement  | Minimum Version |
|-------------|-----------------|
| Python      | 3.11+           |
| PostgreSQL  | 14+             |

Ensure PostgreSQL is running locally and you have credentials to access the `risklens` database.

---

## Setup

### 1. Configuration (`.env`)

Copy `.env.example` to `.env` if not already present:

```bash
cp .env.example .env
```

Ensure your `.env` contains:

```dotenv
DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/risklens
APP_NAME=RiskLens
ENVIRONMENT=dev
CORS_ORIGINS=http://localhost:3000
JWT_SECRET_KEY=<your-secure-random-secret>
```

> **Security Warning**: Replace `JWT_SECRET_KEY` with a strong random secret:
> `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### 2. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Run Migrations

```bash
alembic upgrade head
```

This applies all migrations up to `create entries table`.

### 4. Start Development Server

```bash
uvicorn app.main:app --reload
```

---

## API Endpoints

### System & Documentation

| Method | Path      | Description                 |
|--------|-----------|-----------------------------|
| GET    | `/health` | Database connectivity check |
| GET    | `/docs`   | Swagger UI                  |
| GET    | `/redoc`  | ReDoc                       |

### Authentication (`/auth`)

| Method | Path             | Request Body                     | Description                                          |
|--------|------------------|----------------------------------|------------------------------------------------------|
| POST   | `/auth/register` | `{ email, password }`            | Creates account, returns access + refresh tokens    |
| POST   | `/auth/login`    | `{ email, password }`            | Validates credentials (constant-time anti-enumeration) |
| POST   | `/auth/refresh`  | `{ refresh_token }`              | Rotates refresh token; full revocation on reuse      |
| POST   | `/auth/logout`   | `{ refresh_token }`              | Revokes the active session token                     |

### Entries (`/entries`) — Protected (Requires Bearer Token)

All `/entries` endpoints enforce user isolation derived solely from the validated JWT token (`get_current_user`).

| Method | Path            | Parameters / Body | Description |
|--------|-----------------|-------------------|-------------|
| POST   | `/entries`      | JSON: `{ category, subcategory?, value, unit?, occurred_at, notes? }` | Create entry (201 Created) |
| GET    | `/entries`      | Query: `category`, `subcategory`, `from`, `to`, `limit`, `offset` | List & filter entries (paginated) |
| GET    | `/entries/{id}` | Path: `id` (UUID) | Retrieve single entry (404 if not found or not owned) |
| PUT    | `/entries/{id}` | JSON: `{ value?, unit?, occurred_at?, notes? }` | Update entry (`category` & `subcategory` immutable, 422 if supplied) |
| DELETE | `/entries/{id}` | Path: `id` (UUID) | Soft delete entry (204 No Content, sets `deleted_at`, 404 if already deleted) |

#### Supported Entry Categories

- `income_expense`: Financial inflows/outflows (`value` = amount, `unit` = currency code e.g. "INR")
- `savings`: Savings milestones/records (`value` = amount, `unit` = currency code)
- `study`: Time dedicated to study/education (`value` = duration, `unit` = "hours")
- `academic`: Performance metrics and scores (`value` = score/grade, `unit` = "points")
- `fitness`: Physical activity logs (`value` = duration or distance, `unit` = "minutes" / "km")
- `habits`: Behavioral habit check-ins (`value` = completion count / binary 1.0)

### Goals (`/goals`) — Protected (Requires Bearer Token)

All `/goals` endpoints enforce user isolation derived solely from the validated JWT token (`get_current_user`).

| Method | Path          | Parameters / Body | Description |
|--------|---------------|-------------------|-------------|
| POST   | `/goals`      | JSON: `{ name, target_value, unit?, deadline? }` | Create goal (`current_value` initialized to 0, 201 Created) |
| GET    | `/goals`      | Query: `include_completed?` (bool, default true), `limit?`, `offset?` | List goals sorted: incomplete first by deadline ASC (nulls last), then completed |
| GET    | `/goals/{id}` | Path: `id` (UUID) | Retrieve single goal with computed progress (404 if not found or not owned) |
| PUT    | `/goals/{id}` | JSON: `{ name?, target_value?, current_value?, unit?, deadline? }` | Update goal (logging progress by updating `current_value`) |
| DELETE | `/goals/{id}` | Path: `id` (UUID) | Soft delete goal (204 No Content, sets `deleted_at`, 404 if already deleted) |

#### Computed Goal Progress Fields
- `progress_percent`: `min(100.0, round(current_value / target_value * 100, 1))` (computed on read, capped at 100.0%).
- `is_completed`: `true` when `current_value >= target_value`.

### Simulations (`/simulations`) — Protected (Requires Bearer Token)

All simulation operations are user-isolated and cached with scoped staleness invalidation.

| Method | Path                         | Parameters / Body | Description |
|--------|------------------------------|-------------------|-------------|
| POST   | `/simulations`               | JSON: `{ scenario_type, params }` | Run a simulation scenario (returns immediately with recommendations_status: "pending") |
| GET    | `/simulations/{id}`          | Path: `id` (UUID) | Retrieve simulation result and poll recommendation status |
| GET    | `/simulations/{id}/debug`    | Path: `id` (UUID) | Debug/inspect a cached simulation result (user-isolated) |

#### Available Scenarios

| Scenario Type | Category | Lines | Horizon | Staleness Scope |
|---|---|---|---|---|
| `increase_savings_rate` | Data-Driven | 2 (current_path_expected, expected_case) | 60 months | `all` |
| `fitness_plan` | Data-Driven | 4 (current_baseline, best/expected/risk_case) | 90 days | `all` |
| `reduce_study_hours` | Data-Driven | 4 (current_baseline, best/expected/risk_case) | 14 weeks | `all` |
| `buy_vs_rent` | Assumption-Based | 2 (Buy, Rent) | 10 years | `savings` |
| `program_outcome` | Assumption-Based | 4 (without_program, best/expected/risk_case) | 10 years | `None` (indefinite) |

#### Scoped Staleness Caching
- `"all"` (data-driven default): Cache invalidated when any entry changes.
- `"savings"` (Buy vs Rent): Only savings entries bust the cache; unrelated category changes are ignored.
- `None` (Program Outcome): Caches indefinitely — no real data dependency.

#### Mathematical Identity Guarantees
- **Buy vs Rent**: `home_equity(0) == S` and `rent_net_position(0) == S` exactly, where `S` = tracked savings.
- **Program Outcome**: `Σ cost_y == tuition + opp_cost × D` holds for both integer and fractional program durations `D`.

### Grounded AI Recommendations Layer (Chunk 11 — Gemini Integration)

RiskLens pairs deterministic scenario projections with grounded AI recommendations powered by Google Gemini. The integration enforces strict architectural boundaries to guarantee that LLM output is truthful, non-hallucinatory, and non-blocking.

#### 1. Immediate Execution vs. Asynchronous Recommendations
- **Immediate Response (`POST /simulations`)**:
  - Scenario math executes deterministically in sub-second time.
  - The endpoint responds immediately with HTTP 200 containing all numeric projection lines, reliability assessment, and intermediate derived values, with `recommendations_status: "pending"` and `recommendations: null`.
  - Gemini is **never called synchronously** during the request-response cycle, insulating the core simulation engine from external LLM API latency, network timeouts, or rate limits.
- **Background Generation (`FastAPI BackgroundTasks`)**:
  - A background task triggers `generate_recommendations_for_simulation()` concurrently.
  - Clients poll `GET /simulations/{id}` at reasonable intervals (e.g. 3.5 seconds) until `recommendations_status` transitions to:
    - `"ready"`: Recommendations successfully generated, schema-validated, and persisted to `simulation_results.recommendations`.
    - `"unavailable"`: Generation failed, timed out (15s ceiling), or API key was missing/invalid.
  - In both terminal outcomes, the client stops polling. Polling is strictly bounded and automatically cleaned up on UI unmount or scenario switch.

#### 2. The Grounding Guarantee
> **The Core Guarantee**: Gemini only ever sees the simulation engine's already-computed numeric output (chart line trends, input parameters, reliability tier, and derived values) — **never raw database entries**, and **is never asked to calculate, estimate, or invent a number itself**.

This is the central invariant of the recommendation service:
- The LLM acts exclusively as an explanatory and strategic advisor for figures that have already been validated by deterministic Python code.
- If a metric (e.g., total expenses, break-even month, current savings rate) was not explicitly provided in the structured context dictionary, the model is strictly prohibited from citing or inventing one.
- Responses must conform to the strict Pydantic `RecommendationBatch` schema (an array of items, each with `title`, `description`, `category`, and optional `impact_metric` referencing numbers in context). Malformed responses are rejected and discarded.

#### 3. Scenario-Specific Grounding Constraints
- **Increase Savings Rate (`increase_savings_rate`)**:
  - **Forbidden Content**: The model is forbidden from inventing an "optimal savings rate" or recommending specific named financial instruments/products (e.g. particular mutual funds, stocks, crypto, or third-party platforms).
  - **Required Grounding**: Must reference the actual computed expenses figure (`total_income_in_window - total_savings_in_window`), starting rate, and target rate provided in context.
  - **Mandatory Disclaimer**: Must return the standard financial disclaimer: *"This recommendation is for informational purposes only and does not constitute financial advice."*
- **Hypothetical Framing (`buy_vs_rent` & `program_outcome`)**:
  - Prompts explicitly enforce hypothetical framing: recommendations must focus on sensitivity analysis, testing alternative assumption parameters (e.g., shifts in home appreciation rate, mortgage rates, rent growth, or tuition costs), and stress-testing break-even horizons.
  - The model is forbidden from treating stated assumptions as historical facts or making judgmental claims about personal spending habits.

#### 4. Scoped Invalidation & Recommendation Lifecycle
- Recommendations live directly on the `simulation_results` table row alongside the cached numeric simulation.
- Whenever a cached simulation is invalidated due to new entries within its `staleness_scope` (e.g., new savings entries for `buy_vs_rent`, or any entry for data-driven scenarios), the cached row is superseded.
- Recommendations are wiped and re-enqueued for fresh background generation alongside the new math — **recommendations are never left stale alongside fresh numbers**.

#### 5. Reusable Design (`app/services/grounded_llm.py`)
`app/services/grounded_llm.py` is deliberately designed as a **generic, domain-agnostic grounding service**:
- **Zero Domain Coupling**: It contains no references to simulations, entries, scenarios, or RiskLens domain models.
- **Contract**: Accepts any structured context dictionary, a prompt template, and any Pydantic schema class (`Type[BaseModel]`), returning a typed, validated instance and a sanitized outcome status (`"success"`, `"timeout"`, `"api_error"`, or `"validation_error"`).
- **Intended Milestone 4 Reuse**: This exact module is designed to serve as the foundational grounding layer for **Milestone 4's Conversational Assistant** and future Digital Twin modules. Any feature requiring safe, schema-validated, non-hallucinatory LLM reasoning can directly invoke `generate_grounded_recommendation()` without rebuilding grounding, validation, or timeout logic from scratch.

#### 6. Configured Gemini Model & Catalog Maintenance
- Default configured model: `gemini-3.6-flash` (via `GEMINI_MODEL` in `backend/app/config.py` and `backend/.env.example`).
- **Catalog Note**: Google periodically updates Gemini model versions and lifecycle availability. Maintainers should periodically verify and update `GEMINI_MODEL` against Google's latest official model documentation (https://ai.google.dev/gemini-api/docs/models/gemini) as newer stable versions (or flash variants) are released.

---

## Automated Verification Tests

Run the full automated test suite:

```bash
python -m pytest tests
```

Tests cover:
- **Auth (Chunk 2)**: Registration, constant-time login, token rotation, reuse detection family revocation, logout.
- **Entries (Chunk 3)**: CRUD across 6 time-series categories, user isolation, category immutability, date limits, soft delete.
- **Goals (Chunk 4)**: Goal creation with 0 initial progress, progress updates (50%, 100%, 150% overshoot capped at 100%), target_value <= 0 rejection (422), user isolation (404), soft delete DB retention, deadline sort ordering, and `include_completed` filtering.
- **Forecasting (Chunk 5)**: Statistical forecasting with Prophet, reliability tiering (<14, 14-27, 28+), confidence interval bounds, on-demand cache hits, cache invalidation upon new entries, degenerate series resilience, and multi-tenant isolation.
- **Simulations — Data-Driven (Chunk 9)**: Entry formatting validators (integer rounding for income/savings, 1-decimal for study/academic), savings rate (cumulative growth, independence, income tagging), fitness plan (90-day daily horizon, 4 lines), reduce study hours (R², weak correlation flagging, non-causal language).
- **Simulations — Assumption-Based (Chunk 10)**: Buy vs Rent (t=0 identity, savings bounds 422, savings-scoped caching), Program Outcome (exact cost identity for whole/fractional durations, indefinite caching), field-level 422 validations, widened interface regression on Chunk 9 scenarios.
- **Grounded AI Recommendations (Chunk 11)**: Async background execution (`pending` status), polling resolution (`ready`), strict schema grounding validation, domain-agnostic `grounded_llm.py` isolation, graceful degradation on failure/timeout (`unavailable`), staleness resets, and debug outcome sanitation.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app instance, CORS, lifespan
│   ├── config.py            # Pydantic Settings (reads .env)
│   ├── database.py          # Async SQLAlchemy engine + session dependency
│   ├── security.py          # bcrypt hashing, constant-time verify, JWT
│   ├── dependencies.py      # get_current_user dependency (Isolation Principle)
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── __init__.py      # DeclarativeBase model registry
│   │   ├── user.py          # User model (email, password_hash)
│   │   ├── refresh_token.py # RefreshToken model (jti, rotation chain)
│   │   ├── entry.py         # Entry model (time-series behavioral logs)
│   │   ├── goal.py          # Goal model (personal targets & progress tracking)
│   │   ├── forecast.py      # Forecast model (cached forecasts, points, tiers)
│   │   └── simulation.py    # SimulationResult model (cached scenario outputs)
│   ├── schemas/             # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── auth.py          # Register, Login, Token, Refresh schemas
│   │   ├── entry.py         # EntryCreate, EntryUpdate, EntryResponse schemas
│   │   ├── goal.py          # GoalCreate, GoalUpdate, GoalResponse schemas
│   │   ├── forecast.py      # ForecastResponse, ForecastPoint schemas
│   │   ├── simulation.py    # SimulationRequest/Response + BuyVsRentParams, ProgramOutcomeParams
│   │   └── recommendation.py # Grounded recommendation & batch schemas
│   ├── services/            # Business logic & algorithms
│   │   ├── __init__.py
│   │   ├── forecasting.py   # Prophet integration, daily aggregation, tiering
│   │   ├── grounded_llm.py  # Generic, domain-agnostic grounded LLM service (Milestone 4 reuse)
│   │   ├── recommendation_engine.py # Simulation recommendation runner, prompts & task worker
│   │   └── scenarios/       # Simulation scenario implementations
│   │       ├── __init__.py  # ABC base classes, SCENARIO_REGISTRY, staleness_scope
│   │       ├── savings_rate.py    # IncreaseSavingsRate (data-driven, cumulative)
│   │       ├── fitness_plan.py    # FitnessPlan (data-driven, 90-day daily)
│   │       ├── study_hours.py     # ReduceStudyHours (data-driven, regression)
│   │       ├── buy_vs_rent.py     # BuyVsRent (assumption-based, savings-scoped)
│   │       └── program_outcome.py # ProgramOutcome (assumption-based, indefinite cache)
│   └── routers/             # API route handlers
│       ├── __init__.py
│       ├── health.py        # /health endpoint
│       ├── auth.py          # /auth/* endpoints
│       ├── entries.py       # /entries CRUD endpoints
│       ├── goals.py         # /goals CRUD endpoints
│       ├── forecasts.py     # /forecast endpoint
│       ├── alerts.py        # /alerts endpoint
│       └── simulations.py   # /simulations endpoints (dispatch, polling, scoped caching, debug)
├── alembic/                 # Alembic migration environment
│   ├── env.py               # Reads DB URL from app.config
│   └── versions/            # Migration versions
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures & connection pool teardown
│   ├── test_auth.py         # End-to-end auth test suite
│   ├── test_entries.py      # End-to-end entries CRUD test suite
│   ├── test_goals.py        # End-to-end goals CRUD test suite
│   ├── test_forecast.py     # End-to-end forecasting test suite
│   ├── test_alerts.py       # End-to-end alerts test suite
│   └── test_simulations.py  # Chunks 9–11: entry formatting, all 5 scenarios & Gemini recommendations
├── alembic.ini
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```



