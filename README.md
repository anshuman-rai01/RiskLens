# RiskLens — Personal Risk & Compliance Intelligence

Behavioral analytics and personal compliance platform for tracking finances, savings, study habits, academic performance, fitness, and goals — evaluated continuously against **the user's own self-set baselines** and statistical predictive forecasts.

---

## Milestone 2 Architecture & Status: Fully Complete

Milestone 2 transitions RiskLens from a client-side prototype into a full-stack, enterprise-grade architecture powered by a high-performance **FastAPI** backend, **PostgreSQL** relational persistence with **Alembic** migrations, and a modern **React + Vite** frontend.

### 1. Backend Core & Security
- **Framework**: FastAPI (asyncio) with Pydantic v2 request/response validation.
- **Persistence**: PostgreSQL via Async SQLAlchemy 2.0 and Alembic migrations.
- **Authentication**: JWT access tokens (30m expiry) + rotating refresh tokens with session revocation and reuse detection.
- **Password Security**: Salted Bcrypt / PBKDF2 with robust policy enforcement.
- **Isolation**: Strict query-level tenant isolation via `current_user` dependency across all endpoints.
- **Error Sanitization**: Structured exception handling with zero sensitive trace or internal database leakage to clients.

### 2. Predictive Forecasting Engine (`app/services/forecasting.py`)
- **Model**: Automated time-series forecasting via Facebook Prophet.
- **Confidence Intervals**: Computes predicted values with upper and lower statistical uncertainty bounds over 14-day horizons.
- **Reliability Assessment**: Categorizes series data into `insufficient` (< 14 data points), `low_confidence`, or `reliable`.
- **Database Caching**: Persists generated forecasts in the `forecasts` table to minimize model re-computation.

### 3. Dynamic Risk & Alerting Engine (`app/services/alerting.py`)
- **Threshold Alerts (Goals)**: Evaluates pace against deadlines using elapsed vs. total timeline ratio.
  - Pace gap = actual progress % - expected progress %.
  - `-15% <= pace_gap < -5%` → `warning` (behind pace).
  - `pace_gap < -15%` → `risk` (critically behind pace).
  - Reconciled uniquely per goal using `goal.id` to prevent name collision.
- **Baseline Alerts (Profile)**: Continuously compares month-to-date and week-to-date entry aggregates against user-configured profile baselines:
  - *Monthly Spending Cap*: Warning at ≥ 90%, Risk at ≥ 100% of cap.
  - *Monthly Savings Target*: Warning at < 75%, Risk at < 50% of prorated monthly target.
  - *Weekly Study Hours*: Warning at < 75%, Risk at < 50% of prorated weekly target.
  - *Weekly Fitness Minutes*: Warning at < 75%, Risk at < 50% of prorated weekly target.
  - *Weekly Habit Completions*: Warning at < 75%, Risk at < 50% of prorated weekly target.
- **Trend Alerts (Forecast Deviations)**: Flags entries deviating outside forecast confidence bands:
  - Deviation ≤ 1.5× band width → `warning`.
  - Deviation > 1.5× band width → `risk`.
  - Omitted when series data reliability is `insufficient`.
- **On-Demand DB Reconciliation**:
  - Active conditions matching existing unresolved alerts update in-place (preserving `triggered_at`).
  - Newly emerged conditions insert new alert records.
  - Cleared conditions are automatically marked resolved (`resolved_at = now()`).

### 4. Frontend Architecture
- **Tech Stack**: React 18, Vite 6, TypeScript 5, Tailwind CSS 4, Recharts, Lucide icons.
- **API Integration**: Complete REST integration via `src/lib/api.ts` and `src/lib/db.ts`.
- **Clean Footprint**: Zero dead code; removed unused legacy libraries (`@dnd-kit`, `supabase`, `framer-motion`, `canvas-confetti`, `mockData.ts`, `crypto.ts`).
- **Bundle Efficiency**: Minified production build with gzip size ~195 kB.

---

## Project Structure

```
├── backend/
│   ├── alembic/              # Database migration scripts
│   ├── app/
│   │   ├── models/           # SQLAlchemy ORM models (User, Profile, Entry, Goal, Forecast, Alert)
│   │   ├── routers/          # FastAPI routers (auth, profile, entries, goals, forecasts, alerts, health)
│   │   ├── schemas/          # Pydantic v2 schemas
│   │   ├── services/         # Domain engines (forecasting.py, alerting.py)
│   │   ├── config.py         # Environment & application settings
│   │   ├── database.py       # Async SQLAlchemy engine & session factory
│   │   ├── dependencies.py   # Auth & user context dependency injection
│   │   ├── main.py           # FastAPI application entry point
│   │   └── security.py       # Password hashing & JWT token issuance/verification
│   ├── tests/                # Comprehensive Pytest async test suite (15/15 passing)
│   └── requirements.txt      # Audited Python dependencies
├── src/
│   ├── components/           # UI components (Dashboard, CategoryPage, ProfilePage, Sidebar, AuthGate)
│   ├── lib/                  # Frontend utilities & API adapters (api.ts, db.ts, auth.ts, store.ts)
│   ├── App.tsx               # Root application router
│   └── index.css             # Tailwind design tokens & base styling
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

The frontend dev server runs at `http://localhost:5173`.

### 3. Demo Credentials
A pre-seeded demo user is available for immediate testing:
- **Email**: `demo@risklens.app`
- **Password**: `Demo1234!`
- Or simply click the **"Try Demo"** shortcut on the authentication screen.

---

## Verification & Test Results

- **Backend Pytest Suite**: 15/15 tests passing (`pytest tests/ -v`).
  - Auth flow, token rotation, and reuse revocation.
  - Entry CRUD and category isolation.
  - Goal pacing and collision avoidance.
  - Profile baseline alert computation (pure logic + API integration).
  - Forecast generation, confidence intervals, and Prophet fallback sanitization.
  - Health checks and internal error sanitization.
- **Alembic Migrations**: Zero schema drift (`alembic check` clean).
- **Frontend Typecheck**: Zero TypeScript errors (`npm run typecheck`).
- **Frontend Build**: Zero build errors (`npm run build`).
