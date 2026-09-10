#!/usr/bin/env python3
"""
scripts/seed_data.py
Populates the RiskLens PostgreSQL database with rich, realistic sample data
covering all 7 productivity and behavioral categories over 30+ days.

Supported Categories:
1. income_expense  — Expenses (dining, groceries, transit) & bi-weekly income
2. savings         — Recurring deposits into vaults and funds
3. study           — Daily focus & study hours across technical subjects
4. academic        — Assessment scores & exams on a 0-100% percentage scale
5. fitness         — Workouts (running, gym, yoga) with durations & intensities
6. habits          — Daily habit completions (meditation, reading, sleep)
7. goals           — Personal targets with deadlines via POST /goals

CLI Usage:
    python scripts/seed_data.py --email demo@risklens.app --password Demo1234! --days 35
    python scripts/seed_data.py --email anshumanr699@gmail.com --days 35
"""

import argparse
import os
import random
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE_URL = os.getenv("API_URL", "http://localhost:8000")
DEFAULT_EMAIL = os.getenv("SEED_EMAIL", "demo@risklens.app")
DEFAULT_PASSWORD = os.getenv("SEED_PASSWORD", "Demo1234!")
DEFAULT_DAYS = int(os.getenv("SEED_DAYS", "35"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed database for RiskLens engine.")
    parser.add_argument("--url", default=DEFAULT_BASE_URL, help="Backend API base URL")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="User email account")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="User password")
    parser.add_argument("--name", default="Anshuman Rai", help="User profile name")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Number of historical days to seed")
    parser.add_argument("--clear-first", action="store_true", help="Clear existing entries before seeding")
    return parser.parse_args()


def get_authenticated_client(url: str, email: str, password: str) -> httpx.Client:
    """Logs in or registers the user, returning an authenticated HTTP client."""
    client = httpx.Client(base_url=url, timeout=30.0)

    # Attempt login
    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    if login_resp.status_code == 200:
        token = login_resp.json()["access_token"]
        print(f"[AUTH] Successfully logged in as {email}")
    else:
        # Attempt registration
        print(f"[AUTH] Account {email} not found or invalid credentials. Registering...")
        reg_resp = client.post("/auth/register", json={"email": email, "password": password})
        if reg_resp.status_code not in (200, 201):
            print(f"[ERROR] Registration failed ({reg_resp.status_code}): {reg_resp.text}")
            sys.exit(1)
        
        # Now login
        login_resp = client.post("/auth/login", json={"email": email, "password": password})
        if login_resp.status_code != 200:
            print(f"[ERROR] Login after registration failed: {login_resp.text}")
            sys.exit(1)
        token = login_resp.json()["access_token"]
        print(f"[AUTH] Registered and logged in as {email}")

    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def setup_profile(client: httpx.Client, name: str) -> None:
    """Sets user profile and healthy baseline thresholds."""
    profile_payload = {
        "name": name,
        "age": 22,
        "role": "Computer Science Scholar",
        "currency": "INR",
        "monthly_spending_cap": 25000.00,
        "monthly_savings_target": 12000.00,
        "weekly_study_hours": 24.0,
        "weekly_fitness_minutes": 240,
        "weekly_habit_completions": 28,
        "onboarded": True,
    }
    resp = client.put("/profile", json=profile_payload)
    if resp.status_code == 200:
        print(f"[PROFILE] Updated profile: name='{name}', onboarded=True")
    else:
        print(f"[PROFILE] Note: profile update returned status {resp.status_code}")


def seed_personal_goals(client: httpx.Client) -> None:
    """Creates 2-3 realistic targets via POST /goals."""
    print("[GOALS] Seeding personal target goals...")
    today = date.today()

    goals = [
        {
            "name": "Emergency Reserve Vault",
            "target_value": 150000.00,
            "current_value": 98000.00,
            "unit": "INR",
            "deadline": (today + timedelta(days=90)).isoformat(),
        },
        {
            "name": "Solve 100 Advanced LeetCode Problems",
            "target_value": 100.0,
            "current_value": 64.0,
            "unit": "problems",
            "deadline": (today + timedelta(days=45)).isoformat(),
        },
        {
            "name": "Marathon Conditioning Target",
            "target_value": 250.0,
            "current_value": 185.0,
            "unit": "km",
            "deadline": (today + timedelta(days=60)).isoformat(),
        },
    ]

    for g in goals:
        resp = client.post("/goals", json=g)
        if resp.status_code == 201:
            print(f"  + Created goal: '{g['name']}' ({g['current_value']}/{g['target_value']} {g['unit']})")
        else:
            print(f"  ~ Goal '{g['name']}': status {resp.status_code}")


def generate_time_series_entries(days: int) -> List[Dict[str, Any]]:
    """
    Generates realistic daily entries for 6 categories over the past `days` days.
    Guarantees >= 30 distinct daily points for each category to reach the
    'reliable' forecast tier.
    """
    random.seed(42)  # Deterministic seed for reproducible testing
    today = date.today()
    entries: List[Dict[str, Any]] = []

    # Subjects and topics for Study
    study_curriculum = [
        ("Machine Learning", ["Gradient Descent & Backprop", "Transformers & Attention", "Loss Functions", "CNNs"]),
        ("Algorithms & Data Structures", ["Dynamic Programming", "Graph Traversals", "Segment Trees", "Shortest Path"]),
        ("Distributed Systems", ["Raft Consensus", "CAP Theorem Tradeoffs", "Eventual Consistency", "Kafka Streams"]),
        ("Database Engineering", ["B-Trees & LSM Trees", "PostgreSQL Query Planning", "ACID Isolation Levels", "WAL Logging"]),
    ]

    # Courses for Academic Performance (0-100% percentage scale)
    academic_courses = [
        ("CS 401 - Advanced Algorithms", ["Midterm Exam", "Assignment 3", "Lab Practical", "Quiz 2"]),
        ("CS 480 - Machine Learning", ["Project Milestone", "Math Formulation Quiz", "Model Evaluation Lab"]),
        ("MATH 310 - Linear Algebra", ["Matrix Decomposition Exam", "Vector Spaces Quiz", "Problem Set 4"]),
    ]

    # Fitness activities
    fitness_activities = [
        ("Outdoor Running", ["moderate", "high"], (25, 50)),
        ("Strength Training", ["high", "moderate"], (45, 75)),
        ("Vinyasa Yoga", ["low", "moderate"], (30, 45)),
        ("HIIT Workout", ["high"], (20, 35)),
    ]

    # Daily Habits
    habits_list = [
        "Morning Meditation (15m)",
        "Read Technical Literature (30m)",
        "Adhere to 7+ Hours Sleep Schedule",
        "Deep Work Uninterrupted Block",
    ]

    # Generate daily data backwards from today
    for d_offset in range(days - 1, -1, -1):
        cur_date = today - timedelta(days=d_offset)
        cur_str = cur_date.isoformat()
        is_weekend = cur_date.weekday() in (5, 6)

        # ── 1. Income & Expenses ──────────────────────────────────────────────
        # Small daily living expenses
        expense_subcats = ["Groceries", "Dining Out", "Metro Transit", "Coffee & Workspaces", "Online Subscriptions"]
        num_expenses = random.randint(1, 2)
        for _ in range(num_expenses):
            sub = random.choice(expense_subcats)
            amt = round(random.uniform(150.0, 950.0) if not is_weekend else random.uniform(300.0, 1850.0), 2)
            entries.append({
                "category": "income_expense",
                "subcategory": sub,
                "value": amt,
                "unit": "INR",
                "occurred_at": cur_str,
                "notes": "expense",
            })

        # Bi-weekly income deposit
        if d_offset in (28, 14, 0):
            entries.append({
                "category": "income_expense",
                "subcategory": "Research Fellowship Stipend",
                "value": 35000.00,
                "unit": "INR",
                "occurred_at": cur_str,
                "notes": "income",
            })

        # ── 2. Savings ────────────────────────────────────────────────────────
        # Periodic savings deposits into emergency fund or index vault
        # Generate on at least every 1-2 days to ensure >= 28 distinct dates
        if random.random() < 0.90:  # 90% of days have a savings increment
            vault = random.choice(["Emergency Vault", "Nifty 50 Index", "Sovereign Gold Vault"])
            amt = round(random.choice([500.0, 750.0, 1000.0, 1500.0, 2500.0]) + random.uniform(-50.0, 150.0), 2)
            entries.append({
                "category": "savings",
                "subcategory": vault,
                "value": amt,
                "unit": "INR",
                "occurred_at": cur_str,
                "notes": "Systematic deposit",
            })

        # ── 3. Study Hours ────────────────────────────────────────────────────
        # 1.5 to 5.0 hours daily study
        subj, topics = random.choice(study_curriculum)
        topic = random.choice(topics)
        base_hours = random.uniform(2.5, 4.5) if not is_weekend else random.uniform(1.5, 3.5)
        study_hrs = round(base_hours + random.uniform(-0.4, 0.4), 1)
        entries.append({
            "category": "study",
            "subcategory": subj,
            "value": max(1.0, study_hrs),
            "unit": "hours",
            "occurred_at": cur_str,
            "notes": topic,
        })

        # ── 4. Academic Performance (0-100% scale) ─────────────────────────────
        # Assessment grades over time
        if random.random() < 0.85:  # High frequency to achieve reliable forecast tier
            course, assessments = random.choice(academic_courses)
            assessment = random.choice(assessments)
            # Scores typically between 72% and 98%
            score = round(random.uniform(74.0, 96.0) + (random.uniform(-3.0, 3.0)), 1)
            entries.append({
                "category": "academic",
                "subcategory": course,
                "value": min(100.0, max(50.0, score)),
                "unit": "%",
                "occurred_at": cur_str,
                "notes": assessment,
            })

        # ── 5. Fitness Workouts ───────────────────────────────────────
        if random.random() < 0.88:
            activity, intensities, (min_m, max_m) = random.choice(fitness_activities)
            duration = random.randint(min_m, max_m)
            intensity = random.choice(intensities)
            entries.append({
                "category": "fitness",
                "subcategory": activity,
                "value": float(duration),
                "unit": "minutes",
                "occurred_at": cur_str,
                "notes": intensity,
            })

        # ── 6. Daily Habits ───────────────────────────────────────────────────
        # Log 1-3 habit completions per day
        completed_habits = random.sample(habits_list, k=random.randint(2, len(habits_list)))
        for habit_name in completed_habits:
            entries.append({
                "category": "habits",
                "subcategory": habit_name,
                "value": 1.0,
                "unit": "count",
                "occurred_at": cur_str,
                "notes": "Completed on schedule",
            })

    return entries


def post_entries_batched(client: httpx.Client, entries: List[Dict[str, Any]]) -> None:
    """Posts all entries sequentially with progress tracking."""
    total = len(entries)
    print(f"[ENTRIES] Inserting {total} time-series entries across categories...")

    success_count = 0
    fail_count = 0

    category_counts: Dict[str, int] = {}

    for i, payload in enumerate(entries, 1):
        resp = client.post("/entries", json=payload)
        if resp.status_code == 201:
            success_count += 1
            cat = payload["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1
        else:
            fail_count += 1
            if fail_count <= 3:
                print(f"  [WARN] Failed to insert entry #{i}: {resp.status_code} - {resp.text}")

        if i % 50 == 0 or i == total:
            print(f"  -> Progress: {i}/{total} entries inserted ({success_count} ok, {fail_count} failed)")

    print("\n[SUMMARY] Entries created by category:")
    for cat, count in sorted(category_counts.items()):
        print(f"  - {cat:16}: {count} entries")


def main() -> None:
    args = parse_args()
    print("=" * 60)
    print("  RiskLens Engine — Sample Data Seeder")
    print("=" * 60)
    print(f"  Target URL : {args.url}")
    print(f"  Account    : {args.email}")
    print(f"  History    : {args.days} days")
    print("-" * 60)

    # 1. Authenticate
    client = get_authenticated_client(args.url, args.email, args.password)

    # 2. Setup profile name & baselines
    setup_profile(client, args.name)

    # 3. Seed Personal Goals
    seed_personal_goals(client)

    # 4. Generate & Insert 7 categories of entries
    entries = generate_time_series_entries(args.days)
    post_entries_batched(client, entries)

    print("\n[SUCCESS] Seeding complete! Check your dashboard at http://localhost:51067")


if __name__ == "__main__":
    main()
