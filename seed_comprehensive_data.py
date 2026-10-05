#!/usr/bin/env python3
"""
seed_comprehensive_data.py
Populates the RiskLens database with realistic, structured time-series data:
1. Income, Expenses & Savings (strictly integers, savings = 20% of income)
2. Academic Performance (strictly integers, 0-100 scale)
3. Study Schedule (quarterly hours: 0.25, 0.5, 0.75, etc.)
4. Fitness Activities (multiples of 5 minutes: 15, 20, 25, etc.)
"""

import argparse
from datetime import date, timedelta
import os
import random
import sys
from typing import Any, Dict, Optional

# pyrefly: ignore [missing-import]
import httpx

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================

API_BASE_URL = os.getenv("API_URL", "http://localhost:8000")
DEFAULT_EMAIL = os.getenv("SEED_EMAIL", "demo@risklens.app")
DEFAULT_PASSWORD = os.getenv("SEED_PASSWORD", "Demo1234!")

MONTHS_OF_HISTORY = 24
DAYS_OF_HISTORY = MONTHS_OF_HISTORY * 30  # 720 days

# Phases corresponding to timeline months
PHASE_TIMELINE = ["Lecture", "Problem", "Flash card", "Lab", "Group", "Past year Papers"]

# 4 Income subcategories matching weights=[0.55, 0.15, 0.2, 0.1]
INCOME_SUBCATS = [
    "Salary & Stipend",
    "Freelance Consulting",
    "Investment Dividend",
    "Performance Bonus",
]

# 7 Expense subcategories matching the 7-element weight distributions
EXPENSE_SUBCATS = [
    "Dining & Takeout",
    "Travel & Vacation",
    "Books & Education",
    "Groceries",
    "Utilities & Bills",
    "Entertainment & Leisure",
    "Transit & Commute",
]

# 3 Savings subcategories matching weights=[0.3, 0.45, 0.25]
SAVINGS_SUBCATS = [
    "Emergency Vault",
    "Nifty 50 Index",
    "Sovereign Gold Vault"
]

# Shared courses for Academic Performance & Study Schedule
COURSES = [
    "Machine Learning",
    "Algorithms & Data Structures",
    "Distributed Systems",
    "Database Engineering",
]

# Academic Assessment Types
ACADEMIC_ASSESSMENT_TYPES = [
    "Quiz",
    "Assignment",
    "Lab Practical",
    "Midterm Exam",
    "Project Evaluation",
]

# Habit Subcategories
HABIT_SUBCATS = [
    "Morning Meditation (15m)",
    "No Sugar",
    "Reading",
    "Adhere to 7+ Hours Sleep Schedule",
    "Deep Work Uninterrupted Block",
    "Journaling",
]


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def day_to_date(day_index: int) -> str:
    """
    Converts day_index (0 = oldest day, DAYS_OF_HISTORY - 1 = today)
    into an ISO date string (YYYY-MM-DD).
    """
    target_date = date.today() - timedelta(days=(DAYS_OF_HISTORY - 1 - day_index))
    return target_date.isoformat()


def create_entry(
    token: str,
    category: str,
    subcategory: str,
    value: float | int,
    unit: str,
    occurred_at: str,
    notes: Optional[str] = None,
    intensity: Optional[str] = None,
) -> bool:
    """Creates a time-series entry via POST /entries on the backend."""
    headers = {"Authorization": f"Bearer {token}"}
    payload: Dict[str, Any] = {
        "category": category,
        "subcategory": subcategory,
        "value": value,
        "unit": unit,
        "occurred_at": occurred_at,
    }
    if notes:
        payload["notes"] = notes
    if intensity:
        payload["intensity"] = intensity

    try:
        resp = httpx.post(f"{API_BASE_URL}/entries", json=payload, headers=headers, timeout=15.0)
        return resp.status_code == 201
    except Exception as exc:
        print(f"    [WARN] Failed to post entry: {exc}")
        return False


def get_token(url: str, email: str, password: str) -> str:
    """Logs in or registers the user, returning an access token."""
    client = httpx.Client(base_url=url, timeout=30.0)

    # 1. Attempt login
    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    if login_resp.status_code == 200:
        return login_resp.json()["access_token"]

    # 2. Register if account not found
    print(f"[AUTH] Account {email} not found or invalid credentials. Registering...")
    reg_resp = client.post("/auth/register", json={"email": email, "password": password})
    if reg_resp.status_code not in (200, 201):
        print(f"[ERROR] Registration failed ({reg_resp.status_code}): {reg_resp.text}")
        sys.exit(1)

    # 3. Log in after registration
    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    if login_resp.status_code != 200:
        print(f"[ERROR] Login after registration failed: {login_resp.text}")
        sys.exit(1)

    return login_resp.json()["access_token"]


# ==========================================
# 1. INCOME, EXPENSES & SAVINGS (Strictly Integers)
# ==========================================

def generate_income_expenses(token: str) -> dict:
    """Returns the dictionary of (month_index -> income_amount) so generate_savings() 
    can build exactly 20% off the same real data. Values are strictly integers."""
    print("Seeding Income & Expenses...")
    created = {"income": 0, "expense": 0}
    total_income_target = random.uniform(2_500_000, 3_200_000)
    income_events = random.randint(36, 50)
    income_per_event = total_income_target / income_events

    monthly_income = {}  # month_index -> cumulative income that month

    for i in range(income_events):
        day_index = int((i / income_events) * DAYS_OF_HISTORY) + random.randint(-3, 3)
        day_index = max(0, min(day_index, DAYS_OF_HISTORY - 1))
        subcat = random.choices(INCOME_SUBCATS, weights=[0.55, 0.15, 0.2, 0.1])[0]
        # Strictly integer amounts
        amount = int(round(income_per_event * random.uniform(0.7, 1.3)))
        
        if create_entry(token, "income_expense", subcat, amount, "INR", day_to_date(day_index), notes="income"):
            created["income"] += 1
            month_index = day_index // 30
            monthly_income[month_index] = monthly_income.get(month_index, 0) + amount

    months = MONTHS_OF_HISTORY
    for m in range(months):
        phase = PHASE_TIMELINE[m % len(PHASE_TIMELINE)]
        n_this_month = random.randint(8, 12)
        if phase == "LOW":
            n_this_month = max(4, n_this_month - 4)
            
        for _ in range(n_this_month):
            day_index = m * 30 + random.randint(0, 29)
            if day_index >= DAYS_OF_HISTORY:
                continue
                
            if phase == "VACATION":
                subcat = random.choices(EXPENSE_SUBCATS, weights=[10, 30, 2, 15, 10, 25, 8])[0]
            elif phase in ("EXAM", "BUSY_PROJECT"):
                subcat = random.choices(EXPENSE_SUBCATS, weights=[30, 5, 20, 5, 15, 5, 20])[0]
            else:
                subcat = random.choices(EXPENSE_SUBCATS, weights=[25, 10, 10, 15, 20, 15, 5])[0]
            
            # Strictly integer amounts
            amount = int(round(random.uniform(150, 4500)))
            if create_entry(token, "income_expense", subcat, amount, "INR", day_to_date(day_index), notes="expense"):
                created["expense"] += 1

    print(f"  Income entries: {created['income']}, Expense entries: {created['expense']}")
    return monthly_income


def generate_savings(token: str, monthly_income: dict) -> None:
    """Generates exactly 20% of real income as savings month-by-month. Strictly integer values."""
    print("Seeding Savings Records...")
    created = 0
    for month_index, income_total in sorted(monthly_income.items()):
        # Strictly integer calculation
        target_savings_this_month = int(round(income_total * 0.20))
        if target_savings_this_month <= 0:
            continue
            
        n_records = random.choice([1, 1, 2])
        remaining = target_savings_this_month
        
        for r in range(n_records):
            if remaining <= 0:
                break
            # Strictly integer allocation
            portion = remaining if r == n_records - 1 else int(round(remaining * random.uniform(0.4, 0.7)))
            remaining -= portion
            
            day_index = min(month_index * 30 + random.randint(0, 29), DAYS_OF_HISTORY - 1)
            subcat = random.choices(SAVINGS_SUBCATS, weights=[0.3, 0.45, 0.25])[0]
            
            if create_entry(token, "savings", subcat, portion, "INR", day_to_date(day_index)):
                created += 1

    print(f"  Savings entries: {created} (each month's total is exactly 20% of that month's real income)")


# ==========================================
# 2. STUDY SCHEDULE (Quarterly Hour Format)
# ==========================================

def generate_study_schedule(token: str) -> Dict[int, float]:
    """
    Logs study sessions across shared courses in quarterly hour format (0.25, 0.50, 0.75, 1.0, etc.).
    Returns a dictionary of (week_index -> total_study_hours_that_week) so generate_academic_performance()
    can produce matching, correlated academic scores for the simulation engine.
    """
    print("Seeding Study Schedule...")
    created = 0
    weekly_study_hours: Dict[int, float] = {}

    for day_index in range(DAYS_OF_HISTORY):
        week_index = day_index // 7
        # Log study sessions on ~55% of days across the history window
        if random.random() < 0.55:
            course = random.choice(COURSES)
            # Quarterly format: 0.25, 0.50, 0.75, 1.0, 1.25, ... 4.0 hours
            study_duration_hours = random.randint(1, 16) * 0.25
            session_type = random.choice(PHASE_TIMELINE)  # Lecture, Problem, Flash card, Lab, etc.
            
            if create_entry(
                token,
                "study",
                course,
                study_duration_hours,
                "HOURS",
                day_to_date(day_index),
                notes=session_type,
            ):
                created += 1
                weekly_study_hours[week_index] = (
                    weekly_study_hours.get(week_index, 0.0) + study_duration_hours
                )

    print(f"  Study schedule entries: {created} (distributed across matching courses: {', '.join(COURSES)})")
    return weekly_study_hours


# ==========================================
# 3. ACADEMIC PERFORMANCE (Integers Only, Matched Courses)
# ==========================================

def generate_academic_performance(
    token: str, weekly_study_hours: Optional[Dict[int, float]] = None
) -> None:
    """
    Seeds academic performance scores strictly as integers (out of 100) using the
    exact same courses as the study schedule.
    Correlates scores with weekly study hours so the simulation engine (Reduce Study Hours)
    detects a statistically reliable correlation (R² >= 0.3) across >= 14 paired weeks.
    """
    print("Seeding Academic Performance...")
    created = 0
    total_weeks = DAYS_OF_HISTORY // 7

    for week_index in range(total_weeks):
        # 1 to 2 assessments per week
        n_assessments = random.choice([1, 2])
        week_study = (
            weekly_study_hours.get(week_index, 10.0)
            if weekly_study_hours
            else random.uniform(8.0, 20.0)
        )

        for _ in range(n_assessments):
            day_offset = random.randint(0, 6)
            day_index = min(week_index * 7 + day_offset, DAYS_OF_HISTORY - 1)
            course = random.choice(COURSES)
            assessment = random.choice(ACADEMIC_ASSESSMENT_TYPES)

            # Positively correlated with study hours, strictly integer score [65 - 100]
            base_score = 65 + (week_study * 1.5) + random.randint(-4, 4)
            score = int(round(max(60, min(100, base_score))))

            if create_entry(
                token,
                "academic",
                course,
                score,
                "POINTS",
                day_to_date(day_index),
                notes=assessment,
            ):
                created += 1

    print(f"  Academic entries: {created} (matched with study courses: {', '.join(COURSES)})")


# ==========================================
# 4. FITNESS ACTIVITIES (Multiples of 5 mins)
# ==========================================

def generate_fitness_activities(token: str) -> None:
    print("Seeding Fitness Activities...")
    created = 0
    # Exactly 10 Low, 10 Moderate, and 10 High distributed randomly across dates
    intensities = ["Low"] * 10 + ["Moderate"] * 10 + ["High"] * 10
    random.shuffle(intensities)

    # 5 realistic fitness activities evenly distributed (6 of each across 30 entries)
    activity_types = ["Running", "Yoga", "Weightlifting", "Cycling", "Swimming"]
    activities = activity_types * 6
    random.shuffle(activities)

    for i in range(30):
        day_index = random.randint(0, DAYS_OF_HISTORY - 1)
        
        # Multiples of 5 format: 15, 20, 25, 30... 90 minutes
        fitness_duration_mins = random.randint(3, 18) * 5 
        intensity = intensities[i]
        activity = activities[i]
        
        if create_entry(
            token,
            "fitness",
            activity,
            fitness_duration_mins,
            "MINUTES",
            day_to_date(day_index),
            intensity=intensity,
        ):
            created += 1
            
    print(f"  Fitness entries: {created}")

# ==========================================
# 5. HABIT TRACKING (Daily Completions)
# ==========================================

# ==========================================
# 5. HABIT TRACKING (Daily Completions)
# ==========================================

def generate_habits(token: str) -> None:
    print("Seeding Habit Activities...")
    created = 0
    
    # Iterate through every day in the history window
    for day_index in range(DAYS_OF_HISTORY):
        # Simulate completing between 2 and 5 habits on any given day
        num_habits_today = random.randint(2, len(HABIT_SUBCATS) - 1)
        
        # Randomly select which habits were completed that day
        completed_habits_today = random.sample(HABIT_SUBCATS, num_habits_today)
        
        # Iterate over EVERY habit to mark it as either completed (1) or missed (-1)
        for habit in HABIT_SUBCATS:
            # If the habit is in today's completed list, value is 1, else -1
            habit_value = 1 if habit in completed_habits_today else -1
            
            if create_entry(
                token,
                "habits",
                habit,
                habit_value,
                "COMPLETION",
                day_to_date(day_index),
            ):
                created += 1

    print(f"  Habit entries: {created} (completed and missed tracked across: {', '.join(HABIT_SUBCATS)})")


# ==========================================
# CLI ENTRY POINT
# ==========================================

def main() -> None:
    global API_BASE_URL
    parser = argparse.ArgumentParser(description="Seed comprehensive data for RiskLens.")
    parser.add_argument("--url", default=API_BASE_URL, help="Backend API base URL")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="User email account")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="User password")
    args = parser.parse_args()

    API_BASE_URL = args.url

    print("=" * 60)
    print("  RiskLens Comprehensive Data Seeder")
    print(f"  Target: {args.url} | User: {args.email}")
    print(f"  History Window: {MONTHS_OF_HISTORY} months ({DAYS_OF_HISTORY} days)")
    print("=" * 60)

    token = get_token(args.url, args.email, args.password)
    print(f"[AUTH] Successfully authenticated as {args.email}\n")

    monthly_income = generate_income_expenses(token)
    generate_savings(token, monthly_income)
    weekly_study_hours = generate_study_schedule(token)
    generate_academic_performance(token, weekly_study_hours)
    generate_fitness_activities(token)
    generate_habits(token)

    print("\n[SUCCESS] Comprehensive seeding completed!")


if __name__ == "__main__":
    main()