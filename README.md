# RiskLens — Personal Risk & Compliance Intelligence (Milestone 1)

Behavioral analytics console for personal data: finances, savings, study, academic performance,
fitness, habits, and goals — checked against **the user's own self-set baselines** (compliance here
means adherence to personal limits, not regulatory regimes).

## What Milestone 1 delivers

- **Auth**: register/login, salted **PBKDF2-SHA256** password hashing (120k iterations), compact
  **HS256-signed tokens** — 30-min access + 7-day refresh with **rotation on every use**; refresh-token
  reuse revokes all sessions for the user. Logout, logout-everywhere, change-password.
- **Profile**: 1:1 with the user; identity fields plus five self-set compliance baselines
  (spending cap, savings target, weekly study hours, weekly fitness minutes, weekly habit completions).
- **Data collection**: 7 categories, each with create / view history / update / delete. Edits never
  overwrite — the pre-edit state is archived as an append-only **revision trail** (see the seeded
  "Emergency fund" goal: v1 → v3).
- **Isolation**: every repository call resolves the actor from the *verified access token*
  (`requireUserId()`) and filters rows on `userId` — at query level, not UI level.
- **Dashboard shell**: compliance board (pace-aware progress vs. baselines), month pulse, goals with
  deadlines, recent-activity feed. No charts/models — the shell is structured so Milestone 2 (risk
  scoring, rule engine, charts) plugs in above `db.getOverview()` without a rewrite.

## Environment note — where Postgres/FastAPI went

This artifact runs in a static-frontend sandbox, so the persistence tier is a storage adapter
(`src/lib/store.ts`) over `localStorage`, and the API tier is the repository/service layer
(`src/lib/db.ts`, `src/lib/auth.ts`). Both keep the **exact contracts** of the planned deployment:

| Client module / function        | FastAPI port                          |
| ------------------------------- | ------------------------------------- |
| `auth.register` / `auth.login`  | `POST /auth/register`, `POST /auth/login` |
| `auth.forceRotate` (auto on expiry) | `POST /auth/refresh`              |
| `auth.logout` / `logoutEverywhere` | `POST /auth/logout`, `DELETE /auth/sessions` |
| `db.listEntries(cat)` …         | `GET/POST/PATCH/DELETE /entries?category=` |
| `db.getProfile` / `updateProfile` | `GET/PATCH /profile`                |
| `db.getOverview`                | `GET /overview`                       |

Hashing migrates to **argon2id** server-side behind the same `hashPassword/verifyPassword` interface.

## Postgres schema sketch (Milestone-2 port)

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  email citext unique not null,
  password_hash text not null, salt text not null, iterations int not null,
  created_at timestamptz not null default now()
);
create table profiles (
  user_id uuid primary key references users(id) on delete cascade,
  name text not null, age int check (age between 10 and 100),
  role text not null, currency text not null default '₹', -- fixed to INR application-wide (see src/lib/currency.ts)
  monthly_spending_cap numeric(12,2), monthly_savings_target numeric(12,2),
  weekly_study_hours numeric(6,2), weekly_fitness_minutes numeric(8,2),
  weekly_habit_completions int, updated_at timestamptz not null default now()
);
create table sessions (
  jti text primary key, user_id uuid not null references users(id) on delete cascade,
  created_at timestamptz not null, expires_at timestamptz not null,
  rotated_at timestamptz not null, user_agent text
);
create table entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  category text not null check (category in
    ('income_expense','savings','study','academic','fitness','habits','goals')),
  data jsonb not null,               -- typed payload per category
  occurred_on date not null,
  note text not null default '',
  revisions jsonb not null default '[]',   -- append-only prior versions
  derived jsonb,                     -- milestone 2: risk_score, threshold_breached, impacted_goal_ids
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index entries_history_idx on entries (user_id, category, occurred_on desc);
-- per-user isolation: enable RLS on all tables with `using (user_id = auth.uid())`
```

One `entries` table with a `category` discriminator was chosen over seven tables: uniform
history/permissions, one hot index, and new sources are a config change. The trade-off — weaker
per-category column constraints — is covered by the shared field-schema validator
(`src/lib/categories.ts` → `db.validateEntryPayload`), which becomes Pydantic models on the port.

## Run locally

```bash
npm install
npm run dev       # local dev server
npm run build     # production build (dist/)
```

Demo account (seeded on first load, 60 days of history): `demo@risklens.app` / `Demo1234!`

## Manual verification checklist (per chunk)

1. **Auth**: register with a weak password → rejected with policy message; register + login +
   reload page → session restored via refresh rotation; wrong password → generic error.
2. **Tokens**: watch the top-bar countdown; let it hit 0:00 → auto-rotation toast; press *rotate*
   → new countdown (~30:00). *Sign out everywhere* then try the old tab → bounced to login.
3. **Isolation**: create a second account — the first account's entries/counts are invisible;
   `requireUserId()` derives the owner from the verified token on every call.
4. **CRUD + history**: add/edit/delete in each of the 7 categories; edit the demo "Emergency fund"
   goal again → its revision drawer shows v1/v2/v3 with archived timestamps.
5. **Baselines**: blank a baseline in Profile → its board row flips to "no baseline / set →".

## Out of scope (Milestone 2+)

risk scoring / predictive models · compliance rule engine · charts & trend visuals ·
notifications & recommendations · conversational assistant.
