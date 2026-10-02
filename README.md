# RiskLens — Personal Risk & Compliance Intelligence

Behavioral analytics and personal compliance platform for tracking finances, savings, study habits, academic performance, fitness, and goals — evaluated continuously against **the user's own self-set baselines**, statistical predictive forecasts, and **what-if simulation models**.

---

## Milestone 3 Architecture & Status: Fully Complete (Chunks 9–13)

Milestone 3 delivers the complete **Simulation Lab & Grounded AI Intelligence Engine**, integrating full-stack simulation modeling, regression analysis, assumption forecasting, grounded Gemini LLM recommendations, and goal conversion.

### 1. The 5 Simulation Scenarios

The engine supports 5 scenario types implemented through a uniform ABC and central registry architecture (`SCENARIO_REGISTRY` dispatch):

#### A. Data-Driven Scenarios (3 Scenarios)
1. **Increase Savings Rate (`increase_savings_rate`)**:
   - **Data Dependency**: Trailing 6-month window of `savings` and `income_expense` entries tagged as `"income"` in the `notes` field.
   - **Forecasting**: Shared Facebook Prophet forecast with `growth='flat'` to prevent negative income trajectory extrapolation.
   - **Horizon & Output**: 60-month horizon with exactly **2 chart lines** (`current_path_expected`, `expected_case`).
   - **Cumulative Accumulation**: Forecast contributions accumulate into running account balances over the 5-year horizon (starting at 0 to isolate future projected accumulation).
   - **Goal Conversion**: Supports "Turn This into a Goal" targeting the 5-year projected accumulation.

2. **Fitness Plan (`fitness_plan`)**:
   - **Data Dependency**: Trailing 90-day daily workout logs in `fitness` category.
   - **Reliability Tiers**: Daily point count thresholds (`insufficient` < 14, `low_confidence` 14–27, `reliable` ≥ 28).
   - **Horizon & Output**: 90-day horizon with **4 chart lines** (`current_baseline`, `best_case`, `expected_case`, `risk_case`) and confidence shaded region.
   - **Goal Conversion**: Supports "Turn This into a Goal" targeting weekly workout minutes.

3. **Reduce Study Hours (`reduce_study_hours`)**:
   - **Data Dependency**: Trailing paired-week aggregation of `study` (hours) and `academic` (quiz/exam scores).
   - **Statistical Modeling**: Ordinary Least Squares (OLS) regression via `statsmodels` with 80% prediction intervals.
   - **Honest Statistics**: Weak correlation flag ($R^2 < 0.3 \rightarrow$ `low_confidence`), explicit $R^2$ chip, and strictly non-causal reporting:
     > *"This reflects a statistical association, not a guaranteed causal outcome."*

#### B. Assumption-Based Scenarios (2 Scenarios)
4. **Buy vs Rent (`buy_vs_rent`)**:
   - **Starting Capital ($S$)**: Automatically derived from the user's real accumulated `savings` entries (verified against direct DB queries).
   - **Scoped Invalidation**: `staleness_scope = "savings"` — cached simulation results remain valid across study/fitness entries, but invalidate immediately when new savings entries are posted.
   - **Horizon & Output**: 10-year horizon (11 points, $t=0..10$) with **2 chart lines**: *Buy (Home Equity)* and *Rent (Net Position)*.
   - **Identity Guarantees**: At $t=0$, Buy Equity $= S$ and Rent Position $= S$ exactly.
   - **Mixed-Provenance Disclosure**: Discloses real tracked savings starting capital while labeling growth assumptions as hypothetical.

5. **Program Outcome (`program_outcome`)**:
   - **Assumption Modeling**: Career/education ROI simulation comparing post-program salary trajectories against a flat salary baseline.
   - **Prorated Cost Identity**: Strictly honors the identity $\sum \text{cost}_y = \text{tuition} + \text{opp\_cost} \times D$ for integer and fractional durations $D$ (e.g., $D = 2.5$ years).
   - **Indefinite Caching**: `staleness_scope = None` — cached indefinitely as it operates purely on stated assumptions.
   - **Horizon & Output**: 10-year horizon with **4 chart lines** (`without_program`, `expected_case`, `best_case`, `risk_case`).

---

### 2. Grounded AI Recommendations Layer (`app/services/grounded_llm.py` & `recommendation_engine.py`)

RiskLens pairs deterministic simulation calculations with grounded AI strategic recommendations powered by Google Gemini (`gemini-3.6-flash`).

- **The Grounding Guarantee**:
  - **Gemini only ever sees the simulation engine's already-computed numeric output** (chart line trends, input parameters, reliability tier, and derived intermediate values) — **never raw database entries**, and **is never asked to estimate, calculate, or invent numbers itself**.
  - All advice is strictly contextualized by numbers already computed deterministically in Python. If a metric was not supplied in the structured context, the model is prohibited from citing it.
  - Output is strictly schema-validated via Pydantic `RecommendationBatch`; ungrounded or malformed responses are rejected and discarded.
- **Scenario Grounding Constraints**:
  - *Increase Savings Rate*: Prohibited from inventing an "optimal rate" or naming specific financial investment products. Must reference computed total expenses, starting rate, and target rate, and must include the mandatory non-advisory disclaimer.
  - *Buy vs Rent & Program Outcome*: Enforces sensitivity-focused hypothetical framing; prohibited from treating hypothetical inputs as historical facts or passing judgment on personal spending.
- **Asynchronous Non-Blocking Lifecycle**:
  - `POST /simulations` executes deterministic math instantly and returns `recommendations_status: "pending"` with HTTP 200.
  - A FastAPI `BackgroundTask` enqueues LLM generation in the background without blocking client requests.
  - Clients poll `GET /simulations/{id}` until the status transitions to `"ready"` (persisted to DB) or `"unavailable"` (timeout, quota, or network error).
- **Graceful Degradation**:
  - On API timeouts (15s ceiling), quota limits, or invalid keys, status transitions calmly to `"unavailable"`.
  - Zero raw exception or stack trace leakage to the client. Numeric charts and projections remain 100% functional.
- **`grounded_llm.py` as a Reusable Service (Milestone 4 Foundation)**:
  - `app/services/grounded_llm.py` is built with **zero domain coupling** to simulations or entries.
  - It provides a generic interface: `generate_grounded_recommendation(context, prompt_template, schema_class, api_key, model, timeout_seconds)`.
  - **Intended Milestone 4 Reuse**: This exact module is designed as the shared grounding foundation for **Milestone 4's Conversational Assistant** and future Digital Twin capabilities, guaranteeing that conversational responses stay strictly anchored to verified system data.

---

### 3. Simulation Lab Frontend (`src/components/SimulationLab.tsx`)

The Simulation Lab delivers a unified interface for exploring what-if scenarios across financial, academic, and physical health domains.

- **Scenario Selector**: 5 scenario cards with category badges and backend metadata descriptions.
- **Dynamic Parameter Inputs**:
  - Single intuitive input for data-driven scenarios (target % or target minutes/hours).
  - Multi-field forms for assumption scenarios with client-side validation and server-side 422 field-level error mapping.
- **Tailored Visualizations**:
  - Recharts `LineChart` for 2-line comparisons (Savings Rate, Buy vs Rent).
  - Recharts `AreaChart` with shaded confidence bands for 4-line scenarios (Fitness Plan, Study Hours, Program Outcome).
- **Goal Conversion ("Turn this into a Goal")**:
  - Available exclusively on **Increase Savings Rate** and **Fitness Plan** results.
  - **Why these two scenarios specifically**:
    - *Increase Savings Rate* naturally maps to a single trackable accumulation target: `target_value` = projected 5-year cumulative savings at the target rate, `current_value` = 0, `unit` = "INR", `deadline` = +5 years.
    - *Fitness Plan* naturally maps to a single trackable weekly habit: `target_value` = target weekly minutes, `current_value` = current average weekly minutes, `unit` = "minutes", `deadline` = +3 months.
    - *The other 3 scenarios do not reduce to a single trackable number*:
      - *Reduce Study Hours* outputs a regression model fit ($R^2$, slope, intercept) — one does not "track progress toward an $R^2$".
      - *Buy vs Rent* is a comparative 10-year decision tool (home equity vs net rent position) — there is no single target metric to achieve.
      - *Program Outcome* evaluates multi-year ROI curves under varying salary perturbations — not a single progress-tracked goal.
  - **No New Backend Surface**: Clicking "Turn this into a Goal" calls the existing `POST /goals` REST endpoint directly with pre-filled fields. No simulation-specific goal creation backend endpoints were added.
- **Dashboard Teaser Card**:
  - A lightweight, static prompt card rendered between the alerts/goals area and weekly summary on the main Dashboard (`/app`).
  - Purely a client-side navigation aid (`onNavigate({ view: "simulation" })`).
  - **Zero Backend Overhead**: It performs **no backend calls itself** to render, introducing zero API overhead or query latency to the Dashboard view.

---

### 4. What is Real End-to-End vs. Prototype-Only

| Feature / Domain | Status | Implementation Details |
|---|---|---|
| **Core Authentication & Sessions** | **Real End-to-End** | JWT access/refresh tokens with rotation, bcrypt hashing, DB user isolation |
| **Entries & Categories** | **Real End-to-End** | CRUD across 7 categories, whole-integer rounding for savings/finances, 1-decimal for study/academics |
| **Profile & Baselines** | **Real End-to-End** | Self-set compliance limits, MTD/WTD threshold calculations |
| **Risk & Alerting Engine** | **Real End-to-End** | In-place alert updates, goal pace monitoring, forecast deviation alerts |
| **Time-Series Forecasting** | **Real End-to-End** | Facebook Prophet engine, 14-day horizons, statistical bounds |
| **Simulation Engine (All 5 Scenarios)** | **Real End-to-End** | Registry dispatch, SHA-256 caching, scoped staleness, OLS regression |
| **Grounded Gemini Recommendations** | **Real End-to-End** | Background task generation, schema validation, graceful fallback |
| **Simulation Lab UI & Goal Conversion** | **Real End-to-End** | Full React UI, tailored charts, polling lifecycle, goal creation |
| **Digital Twin Creation** | **Deferred** | Out of scope for Milestone 3; planned for future milestones |
| **Conversational Assistant** | **Deferred** | Out of scope for Milestone 3; planned for Milestone 4 |

---

## Project Structure

```
├── backend/
│   ├── alembic/              # Database migration scripts (through head revision c4d5e6f78901)
│   ├── app/
│   │   ├── models/           # SQLAlchemy ORM models (User, Profile, Entry, Goal, Forecast, Alert, SimulationResult)
│   │   ├── routers/          # FastAPI routers (auth, profile, entries, goals, forecasts, alerts, health, simulations)
│   │   ├── schemas/          # Pydantic v2 schemas (simulation.py, recommendation.py, etc.)
│   │   ├── services/         # Domain engines:
│   │   │   ├── forecasting.py            # Facebook Prophet engine
│   │   │   ├── alerting.py               # Risk alerts & baseline compliance
│   │   │   ├── grounded_llm.py           # Generic grounded LLM service (reusable)
│   │   │   ├── recommendation_engine.py  # Scenario-specific prompt & recommendation runner
│   │   │   └── scenarios/                # Simulation scenarios (ABC + SCENARIO_REGISTRY)
│   │   │       ├── savings_rate.py
│   │   │       ├── fitness_plan.py
│   │   │       ├── study_hours.py
│   │   │       ├── buy_vs_rent.py
│   │   │       └── program_outcome.py
│   │   ├── config.py         # Settings & Gemini API key configuration
│   │   ├── database.py       # Async SQLAlchemy engine & session factory
│   │   ├── dependencies.py   # Auth & user context dependency injection
│   │   ├── main.py           # FastAPI application entry point
│   │   └── security.py       # Password hashing & JWT token issuance/verification
│   ├── tests/                # Comprehensive Pytest async test suite (57/57 passing)
│   └── requirements.txt      # Fully audited Python dependencies
├── src/
│   ├── components/           # UI components (SimulationLab, Dashboard, CategoryPage, ProfilePage, Sidebar)
│   ├── lib/                  # Utilities & API client (api.ts, db.ts, auth.ts, currency.ts)
│   ├── App.tsx               # Root application router with /simulation view
│   └── index.css             # Tailwind design tokens & dark-editorial styling
├── package.json              # Cleaned frontend dependencies
└── README.md
```

---

## Running Locally

### 1. Backend Setup

```bash
cd backend

# Create & activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Run server
uvicorn app.main:app --reload --port 8000
```

The backend runs at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is accessible at `/docs`.

### 2. Frontend Setup

```bash
# In the repository root
npm install

# Run dev server
npm run dev

# Run typecheck & build
npm run typecheck
npm run build
```

The frontend dev server runs at `http://localhost:3000`.

---

## Full Regression Test Suite Results (Chunk 13)

- **Backend Pytest Suite**: **57/57 tests passing** (100% pass rate).
  - `test_simulations.py` (41 tests): Formatting validators, registry dispatch, flat-growth cumulative savings, fitness horizons, OLS regression & $R^2$, Buy vs Rent identity & scoped caching, Program Outcome prorating & indefinite caching, Gemini grounding & degradation, debug endpoint user isolation.
  - `test_health.py`, `test_auth.py`, `test_entries.py`, `test_goals.py`, `test_profile.py`, `test_alerts.py`, `test_forecast.py` (16 tests): Core regression coverage across health, auth, entries, goals, profiles, alerts, and time-series forecasting.
- **Alembic Migrations**: Fully verified against clean Postgres (`alembic downgrade 665dfdb21536` $\rightarrow$ `alembic upgrade head`).
- **Dependency Audit**: 100% clean — zero missing dependencies in `requirements.txt`.
- **Exception Sanitization**: 100% clean — zero raw exception text leaks to clients.
- **Frontend Typecheck**: **0 errors** (`npx tsc --noEmit`).
- **Frontend Build**: **1,993 modules transformed**, clean production bundle:
  - `dist/index.html`: 1.43 kB
  - `dist/assets/index-BHYsMbwn.css`: 43.47 kB (gzip: 8.35 kB)
  - `dist/assets/index-DVdfoII6.js`: 696.15 kB (gzip: 194.25 kB)
  - Total bundle: 739.62 kB raw (202.6 kB gzipped).
