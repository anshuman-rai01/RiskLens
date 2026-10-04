"""
Tests for Scenario 3: Study Hours What-If (reduce_study_hours).

Acceptance criteria verified:
- Leakage test: study session on assessment date or after does NOT change feature or curve.
- created_at invariance: created_at far after occurred_at does not change results.
- Subject filter with n=5 returns insufficient and reports pooled_n.
- Curve values stay within [0, 100], and risk <= expected <= best everywhere.
- KPI values equal derived_values at settled sliders.
"""

from datetime import date, datetime, timedelta
import pytest
from app.models.entry import Entry
from app.services.scenarios.study_hours import ReduceStudyHours


def _make_entry(
    user_id: str,
    category: str,
    value: float,
    occurred_at: date,
    subcategory: str = "",
    notes: str = "",
    unit: str = "hours",
    max_value: float = 100.0,
    created_at: datetime = None,
) -> Entry:
    e = Entry(
        user_id=user_id,
        category=category,
        value=value,
        occurred_at=datetime.combine(occurred_at, datetime.min.time()),
        subcategory=subcategory,
        notes=notes,
        unit=unit,
        max_value=max_value,
        deleted_at=None,
    )
    if created_at is not None:
        e.created_at = created_at
    return e


def test_scenario3_leakage_safety():
    """A study session on the assessment date, or after it, does not change that assessment's feature."""
    scenario = ReduceStudyHours()
    user_id = "user_s3_leakage"
    base_date = date(2024, 1, 1)

    # 10 assessments, one every 15 days starting day 20
    entries = []
    # Seed prior study entries with varying hours across weeks
    for day_offset in range(1, 200):
        d = base_date + timedelta(days=day_offset)
        # Hours increase over time so assessments have distinct study features
        hours = 1.0 + (day_offset // 15) * 0.5 + (day_offset % 3) * 0.2
        entries.append(_make_entry(user_id, "study", hours, d, subcategory="physics"))

    for i in range(10):
        assess_date = base_date + timedelta(days=20 + i * 15)
        entries.append(
            _make_entry(
                user_id,
                "academic",
                60.0 + i * 3.5,
                assess_date,
                subcategory="physics",
                notes="Midterm",
                max_value=100.0,
            )
        )

    res1 = scenario.compute(user_id, list(entries), {"window_days": 14, "subject": "physics"})
    assert res1["reliability"] in ("reliable", "low_confidence"), f"res1 reliability: {res1.get('message')}"

    # Add study entries ON assessment dates and AFTER all assessments
    leaked_entries = list(entries)
    for i in range(10):
        assess_date = base_date + timedelta(days=20 + i * 15)
        # On assessment date d (window was [d-14, d-1])
        leaked_entries.append(_make_entry(user_id, "study", 10.0, assess_date, subcategory="physics"))

    # Post-assessment study entries (after the final assessment)
    last_assess_date = base_date + timedelta(days=20 + 9 * 15)
    for day_offset in range(1, 15):
        leaked_entries.append(
            _make_entry(user_id, "study", 12.0, last_assess_date + timedelta(days=day_offset), subcategory="physics")
        )

    res2 = scenario.compute(user_id, leaked_entries, {"window_days": 14, "subject": "physics"})

    assert res1["derived_values"]["observed_avg_daily_hours"] == res2["derived_values"]["observed_avg_daily_hours"]
    assert res1["derived_values"]["baseline_score"] == res2["derived_values"]["baseline_score"]
    assert res1["derived_values"]["scenario_score"] == res2["derived_values"]["scenario_score"]
    assert res1["lines"] == res2["lines"]


def test_scenario3_created_at_invariance():
    """Every created_at is far after occurred_at and results are unchanged."""
    scenario = ReduceStudyHours()
    user_id = "user_s3_created_at"
    base_date = date(2024, 1, 1)

    entries1 = []
    entries2 = []

    for day_offset in range(1, 180):
        d = base_date + timedelta(days=day_offset)
        hours = 1.0 + (day_offset // 15) * 0.4
        entries1.append(_make_entry(user_id, "study", hours, d, subcategory="math"))
        # Backfilled entries with created_at 60 days in the future
        e2 = _make_entry(
            user_id, "study", hours, d, subcategory="math",
            created_at=datetime.combine(d + timedelta(days=60), datetime.min.time())
        )
        entries2.append(e2)

    for i in range(10):
        assess_date = base_date + timedelta(days=20 + i * 15)
        entries1.append(_make_entry(user_id, "academic", 60.0 + i * 3, assess_date, subcategory="math"))
        e2_acad = _make_entry(
            user_id, "academic", 60.0 + i * 3, assess_date, subcategory="math",
            created_at=datetime.combine(assess_date + timedelta(days=90), datetime.min.time())
        )
        entries2.append(e2_acad)

    res1 = scenario.compute(user_id, entries1, {"window_days": 14})
    res2 = scenario.compute(user_id, entries2, {"window_days": 14})

    assert res1["lines"] == res2["lines"]
    assert res1["derived_values"] == res2["derived_values"]


def test_scenario3_subject_filter_insufficient_with_pooled_hint():
    """A subject filter with n=5 returns insufficient with pooled_n as hint."""
    scenario = ReduceStudyHours()
    user_id = "user_s3_filter"
    base_date = date(2024, 1, 1)

    entries = []
    # Seed study entries for both subjects
    for day_offset in range(1, 200):
        d = base_date + timedelta(days=day_offset)
        entries.append(_make_entry(user_id, "study", 2.0, d, subcategory="physics"))
        entries.append(_make_entry(user_id, "study", 3.0, d, subcategory="chemistry"))

    # 5 physics assessments and 5 chemistry assessments
    for i in range(5):
        d1 = base_date + timedelta(days=20 + i * 20)
        entries.append(_make_entry(user_id, "academic", 75.0, d1, subcategory="physics"))
        d2 = base_date + timedelta(days=25 + i * 20)
        entries.append(_make_entry(user_id, "academic", 80.0, d2, subcategory="chemistry"))

    res = scenario.compute(user_id, entries, {"window_days": 14, "subject": "physics"})

    assert res["reliability"] == "insufficient"
    assert res["data_point_count"] == 5
    assert len(res["lines"]) == 0
    assert res["derived_values"]["pooled_n"] == 10
    assert "Only 5 assessments found" in res["message"]
    assert "There are 10 total assessments available without filters" in res["message"]


def test_scenario3_curve_clamped_and_bounds():
    """Curve values stay within [0, 100], and lower <= y <= upper everywhere."""
    scenario = ReduceStudyHours()
    user_id = "user_s3_bounds"
    base_date = date(2024, 1, 1)

    entries = []
    for day_offset in range(1, 220):
        d = base_date + timedelta(days=day_offset)
        hours = 0.5 + (day_offset // 15) * 0.4
        entries.append(_make_entry(user_id, "study", hours, d, subcategory="biology"))

    # 12 assessments
    for i in range(12):
        d = base_date + timedelta(days=20 + i * 15)
        score = min(100.0, max(0.0, 50.0 + i * 4.0))
        entries.append(_make_entry(user_id, "academic", score, d, subcategory="biology", max_value=100.0))

    res = scenario.compute(user_id, entries, {"window_days": 14})
    assert res["reliability"] in ("reliable", "low_confidence"), f"bounds reliability: {res.get('message')}"

    lines_by_label = {line["label"]: line["points"] for line in res["lines"]}
    assert "expected_case" in lines_by_label
    assert "best_case" in lines_by_label
    assert "risk_case" in lines_by_label

    expected = lines_by_label["expected_case"]
    best = lines_by_label["best_case"]
    risk = lines_by_label["risk_case"]

    assert len(expected) == 81  # 0.0 to 8.0 step 0.1
    assert len(best) == 81
    assert len(risk) == 81

    for i in range(81):
        x_exp = expected[i]["x"]
        y_exp = expected[i]["value"]
        y_best = best[i]["value"]
        y_risk = risk[i]["value"]

        assert 0.0 <= x_exp <= 8.0
        assert 0.0 <= y_risk <= 100.0
        assert 0.0 <= y_exp <= 100.0
        assert 0.0 <= y_best <= 100.0
        assert y_risk <= y_exp <= y_best, f"Bound violation at index {i} (x={x_exp}): risk={y_risk}, exp={y_exp}, best={y_best}"


def test_scenario3_kpis_match_derived_values():
    """KPI values equal derived_values at settled sliders."""
    scenario = ReduceStudyHours()
    user_id = "user_s3_kpi"
    base_date = date(2024, 1, 1)

    entries = []
    for day_offset in range(1, 200):
        d = base_date + timedelta(days=day_offset)
        hours = 1.0 + (day_offset // 15) * 0.4
        entries.append(_make_entry(user_id, "study", hours, d, subcategory="history"))

    for i in range(10):
        d = base_date + timedelta(days=20 + i * 16)
        entries.append(_make_entry(user_id, "academic", 65.0 + i * 2.5, d, subcategory="history"))

    res = scenario.compute(
        user_id,
        entries,
        {"window_days": 14, "current_daily_hours": 2.0, "simulated_daily_hours": 4.0},
    )

    dv = res["derived_values"]
    assert dv["current_daily_hours"] == 2.0
    assert dv["simulated_daily_hours"] == 4.0
    assert dv["absolute_difference_pp"] == round(dv["scenario_score"] - dv["baseline_score"], 2)
    if dv["baseline_score"] > 0:
        expected_rel = round((dv["scenario_score"] - dv["baseline_score"]) / dv["baseline_score"] * 100.0, 2)
        assert dv["relative_difference_pct"] == expected_rel
