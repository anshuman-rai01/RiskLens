#!/usr/bin/env python3
"""
scripts/clear_seed_data.py
Removes the data created by scripts/seed_data.py directly from PostgreSQL.

How "seeded" is defined
-----------------------
No table has a seed marker column, so seeded rows cannot be told apart from
real ones by content. The only reliable definition is ownership: everything
that belongs to the account(s) you name with --email. By default that is the
demo account (demo@risklens.app, or $SEED_EMAIL if set).

What is deleted, per targeted account
-------------------------------------
    entries    (including soft-deleted rows, i.e. deleted_at IS NOT NULL)
    goals      (including soft-deleted rows)
    alerts     (derived from entries - would be orphaned otherwise)
    forecasts  (derived from entries - cached Prophet output)

What is kept unless you pass --delete-user
------------------------------------------
    users row, profile (baselines), refresh tokens. Keeping the user means
    the "Try Demo" login keeps working and seed_data.py can simply be re-run.

Safety rails
------------
    * Dry run by default - prints what WOULD be deleted. Add --execute to delete.
    * Refuses to run when ENVIRONMENT=prod.
    * Execution asks you to type the database name (skip with --yes).
    * All deletes run in ONE transaction; any error or unexpected leftover
      rolls everything back.

Usage (from anywhere; reads backend/.env):
    python scripts/clear_seed_data.py                      # dry run, demo account
    python scripts/clear_seed_data.py --execute            # delete demo data
    python scripts/clear_seed_data.py --email me@x.com --execute
    python scripts/clear_seed_data.py --execute --delete-user
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, make_url

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ENV = REPO_ROOT / "backend" / ".env"

# Child tables that reference users.id. These are hard-coded constants (never
# user input), so interpolating them into SQL below is safe.
DATA_TABLES = ("alerts", "forecasts", "entries", "goals")
SOFT_DELETE_TABLES = {"entries", "goals"}  # tables that have a deleted_at column


# ── Data holders ─────────────────────────────────────────────────────────────


@dataclass
class TableCount:
    total: int = 0
    soft_deleted: int = 0  # only meaningful for SOFT_DELETE_TABLES


@dataclass
class UserPlan:
    user_id: str
    email: str
    counts: Dict[str, TableCount] = field(default_factory=dict)
    entry_range: Optional[tuple] = None  # (min occurred_at, max occurred_at)

    @property
    def total_rows(self) -> int:
        return sum(c.total for c in self.counts.values())


# ── Helpers ──────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Delete seeded data for one or more accounts (dry run by default)."
    )
    parser.add_argument(
        "--email",
        action="append",
        dest="emails",
        help="Account to clear. Repeatable. Default: the demo/seed account.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete. Without this flag nothing is changed.",
    )
    parser.add_argument(
        "--delete-user",
        action="store_true",
        help="Also delete the user row (cascades to profile and refresh tokens).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the type-the-database-name confirmation (for scripted use).",
    )
    return parser.parse_args()


def get_database_url() -> str:
    """Same precedence as app/config.py: real env vars beat backend/.env."""
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL")
    if not url:
        sys.exit(f"[ERROR] DATABASE_URL is not set. Expected it in {BACKEND_ENV} or the environment.")
    # The app uses asyncpg; this script is synchronous, so swap to psycopg2.
    return url.replace("postgresql+asyncpg", "postgresql+psycopg2")


def count_table(conn: Connection, table: str, user_id: str) -> TableCount:
    if table in SOFT_DELETE_TABLES:
        row = conn.execute(
            text(
                f"SELECT COUNT(*), COUNT(deleted_at) FROM {table} WHERE user_id = :uid"
            ),
            {"uid": user_id},
        ).one()
        return TableCount(total=row[0], soft_deleted=row[1])
    row = conn.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE user_id = :uid"), {"uid": user_id}
    ).one()
    return TableCount(total=row[0])


def build_plan(conn: Connection, user_id: str, email: str) -> UserPlan:
    plan = UserPlan(user_id=user_id, email=email)
    for table in DATA_TABLES:
        plan.counts[table] = count_table(conn, table, user_id)
    rng = conn.execute(
        text("SELECT MIN(occurred_at), MAX(occurred_at) FROM entries WHERE user_id = :uid"),
        {"uid": user_id},
    ).one()
    if rng[0] is not None:
        plan.entry_range = (rng[0], rng[1])
    return plan


def print_plan(plans: List[UserPlan], delete_user: bool) -> None:
    for plan in plans:
        print(f"\n  Account: {plan.email}")
        for table in DATA_TABLES:
            c = plan.counts[table]
            extra = f"  ({c.soft_deleted} already soft-deleted)" if c.soft_deleted else ""
            print(f"    {table:<10} {c.total:>6} rows{extra}")
        if plan.entry_range:
            print(f"    entries span {plan.entry_range[0]} -> {plan.entry_range[1]}")
        action = "DELETED (with profile + tokens)" if delete_user else "kept (profile, login, tokens)"
        print(f"    user row   {action}")


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    # override=False: variables already in the environment win over the .env file.
    load_dotenv(BACKEND_ENV, override=False)
    args = parse_args()

    if os.getenv("ENVIRONMENT", "dev").strip().lower() == "prod":
        sys.exit("[ABORT] ENVIRONMENT=prod. This script refuses to run against production.")

    emails = args.emails or [os.getenv("SEED_EMAIL", "demo@risklens.app")]
    url = get_database_url()
    parsed = make_url(url)
    engine = create_engine(url, pool_pre_ping=True)

    print("=" * 62)
    print("  RiskLens - Clear Seeded Data" + ("" if args.execute else "   [DRY RUN]"))
    print("=" * 62)
    print(f"  Database : {parsed.render_as_string(hide_password=True)}")
    print(f"  Accounts : {', '.join(emails)}")

    with engine.connect() as conn:
        plans: List[UserPlan] = []
        missing: List[str] = []
        for email in emails:
            row = conn.execute(
                text("SELECT id, email FROM users WHERE lower(email) = lower(:email)"),
                {"email": email},
            ).one_or_none()
            if row is None:
                missing.append(email)
                continue
            plans.append(build_plan(conn, str(row[0]), row[1]))

        if missing:
            existing = [r[0] for r in conn.execute(text("SELECT email FROM users ORDER BY email"))]
            print(f"\n  [NOT FOUND] {', '.join(missing)}")
            print(f"  Existing accounts: {', '.join(existing) if existing else '(none)'}")

    if not plans:
        print("\n  Nothing to do.")
        return

    print_plan(plans, args.delete_user)

    if all(p.total_rows == 0 for p in plans) and not args.delete_user:
        print("\n  All targeted accounts are already empty. Nothing to delete.")
        return

    if not args.execute:
        print("\n  DRY RUN - nothing was changed. Re-run with --execute to delete.")
        return

    # ── Confirmation ─────────────────────────────────────────────────────────
    if not args.yes:
        db_name = parsed.database or ""
        if not sys.stdin.isatty():
            sys.exit("\n[ABORT] Not an interactive terminal. Pass --yes to confirm non-interactively.")
        try:
            typed = input(f"\n  Type the database name ('{db_name}') to confirm deletion: ").strip()
        except EOFError:
            sys.exit("\n[ABORT] No confirmation received.")
        if typed != db_name:
            sys.exit("[ABORT] Name did not match. Nothing was deleted.")

    # ── Delete (single transaction) ──────────────────────────────────────────
    print("\n  Deleting...")
    with engine.begin() as conn:  # commits on success, rolls back on any exception
        for plan in plans:
            for table in DATA_TABLES:
                result = conn.execute(
                    text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": plan.user_id}
                )
                print(f"    {plan.email}: {table:<10} -{result.rowcount}")

            # Verify inside the transaction, before it commits.
            for table in DATA_TABLES:
                left = count_table(conn, table, plan.user_id).total
                if left:
                    raise RuntimeError(
                        f"{left} rows still in {table} for {plan.email}; rolling back."
                    )

            if args.delete_user:
                conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": plan.user_id})
                print(f"    {plan.email}: users      -1 (profile + tokens cascade)")

    print("\n  [SUCCESS] Seeded data cleared.")
    if not args.delete_user:
        print("  Re-seed any time with: python scripts/seed_data.py")


if __name__ == "__main__":
    main()
