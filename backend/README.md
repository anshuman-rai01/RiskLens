# RiskLens Backend

FastAPI backend for the RiskLens financial risk management platform.

> **Milestone 2 — Chunk 3 (Entries CRUD)**
> Real time-series data collection API covering 6 behavioral categories (`income_expense`, `savings`, `study`, `academic`, `fitness`, `habits`).
> Strict multi-tenant isolation via JWT, category immutability, Numeric(12,2) precision, and soft-delete retention.

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

### Forecasting (`/forecast`) — Protected (Requires Bearer Token)

All forecasting operations are user-isolated and compute on-demand with automatic cache reuse.

| Method | Path        | Parameters | Description |
|--------|-------------|------------|-------------|
| GET    | `/forecast` | Query: `category` (required), `subcategory` (optional), `horizon_days` (default 14) | Returns forecast with 80% confidence bands (`predicted`, `lower`, `upper`) |

#### Reliability Tiering
- **`< 14` data points**: Returns `reliability: "insufficient"`, empty `forecast_points`, and message `"More data is required to generate a forecast"`.
- **`14–27` data points**: Returns `reliability: "low_confidence"` with Prophet forecast points.
- **`>= 28` data points**: Returns `reliability: "reliable"` with full confidence band projections.

#### On-Demand Staleness Caching
Forecast results are cached in the `forecasts` table per `(user_id, category, subcategory)`. If no entries have been added, modified, or deleted since the cached `generated_at`, subsequent calls return the cached forecast instantly without refitting Prophet. Adding or editing an entry automatically triggers a fresh refit on the next read.

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
│   │   └── forecast.py      # Forecast model (cached forecasts, points, tiers)
│   ├── schemas/             # Pydantic request/response schemas
│   │   ├── __init__.py
│   │   ├── auth.py          # Register, Login, Token, Refresh schemas
│   │   ├── entry.py         # EntryCreate, EntryUpdate, EntryResponse schemas
│   │   ├── goal.py          # GoalCreate, GoalUpdate, GoalResponse schemas
│   │   └── forecast.py      # ForecastResponse, ForecastPoint schemas
│   ├── services/            # Business logic & algorithms
│   │   ├── __init__.py
│   │   └── forecasting.py   # Prophet integration, daily aggregation, tiering
│   └── routers/             # API route handlers
│       ├── __init__.py
│       ├── health.py        # /health endpoint
│       ├── auth.py          # /auth/* endpoints
│       ├── entries.py       # /entries CRUD endpoints
│       ├── goals.py         # /goals CRUD endpoints
│       └── forecasts.py     # /forecast endpoint
├── alembic/                 # Alembic migration environment
│   ├── env.py               # Reads DB URL from app.config
│   └── versions/            # Migration versions
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Pytest fixtures & connection pool teardown
│   ├── test_auth.py         # End-to-end auth test suite
│   ├── test_entries.py      # End-to-end entries CRUD test suite
│   ├── test_goals.py        # End-to-end goals CRUD test suite
│   └── test_forecast.py     # End-to-end forecasting test suite
├── alembic.ini
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```



