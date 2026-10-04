"""
Study Hours What-If scenario (reduce_study_hours) — data-driven simulation.

Evaluates the statistical relationship between average daily study hours leading up
to an assessment and the resulting standardized academic score using closed-form
Ridge regression with Leave-One-Out Cross-Validation (LOO-CV).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import numpy as np

from app.models.entry import Entry
from app.services.scenarios import DataDrivenScenario

logger = logging.getLogger(__name__)

ALLOWED_STUDY_UNITS: Set[Optional[str]] = {None, "", "hours", "hour", "h", "hrs", "hr"}
RIDGE_ALPHAS = [0.01, 0.1, 1.0, 10.0]


def _to_date(val: Any) -> date:
    """Normalize datetime or date to standard datetime.date."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        return date.fromisoformat(val[:10])
    raise ValueError(f"Cannot convert {val!r} to date")


class ReduceStudyHours(DataDrivenScenario):
    """
    Scenario 3: Interactive what-if academic performance (Study Hours What-If).

    - Leakage-safe window: for assessment on date d, sums study hours in [d - W, d - 1] / W.
    - Excludes day d and later entirely.
    - Uses occurred_at only (never created_at).
    - Drops assessments where d - W precedes the user's first study entry (dropped_no_coverage).
    - Standardizes score = obtained / max_value * 100 (skipping max_value <= 0 or value < 0).
    - Closed-form Ridge regression on standardized feature + unpenalized intercept.
    - Alpha chosen from {0.01, 0.1, 1, 10} via LOO-CV via hat matrix.
    - 80% distribution-free interval via 80th percentile of |LOO residuals|.
    - Monotonic grid 0.0 - 8.0 h (step 0.1) clamped to [0, 100].
    """

    staleness_scope: Optional[str] = "all"

    def compute(
        self,
        user_id: str,
        entries: List[Entry],
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        window_days = int(params.get("window_days", 14))
        if window_days not in (7, 14):
            window_days = 14

        subject_filter = params.get("subject")
        norm_subject = (
            subject_filter.strip().lower()
            if subject_filter and subject_filter.strip()
            else None
        )

        type_filter = params.get("assessment_type")
        norm_type = (
            type_filter.strip().lower()
            if type_filter and type_filter.strip()
            else None
        )

        # ── 1. Extract and sanitize study & academic rows ──────────────
        study_entries: List[Dict[str, Any]] = []
        academic_entries: List[Dict[str, Any]] = []
        skipped_unit_count = 0

        for e in entries:
            # Respect soft-deletes if present
            if getattr(e, "deleted_at", None) is not None:
                continue

            if e.category == "study":
                unit_str = e.unit.strip().lower() if e.unit else None
                if unit_str not in ALLOWED_STUDY_UNITS:
                    skipped_unit_count += 1
                    continue
                try:
                    val = float(e.value)
                except (ValueError, TypeError):
                    continue
                if val < 0:
                    continue

                entry_date = _to_date(e.occurred_at)
                subj = e.subcategory.strip().lower() if e.subcategory else ""
                study_entries.append({
                    "date": entry_date,
                    "hours": val,
                    "subject": subj,
                })

            elif e.category == "academic":
                try:
                    obtained = float(e.value)
                except (ValueError, TypeError):
                    continue
                if obtained < 0:
                    continue

                max_val = 100.0
                if getattr(e, "max_value", None) is not None:
                    try:
                        max_val = float(e.max_value)
                    except (ValueError, TypeError):
                        max_val = 100.0
                if max_val <= 0:
                    continue

                score = (obtained / max_val) * 100.0
                entry_date = _to_date(e.occurred_at)
                course_raw = e.subcategory.strip() if e.subcategory else ""
                type_raw = e.notes.strip() if e.notes else ""

                academic_entries.append({
                    "date": entry_date,
                    "score": score,
                    "course": course_raw,
                    "course_lower": course_raw.lower(),
                    "type": type_raw,
                    "type_lower": type_raw.lower(),
                })

        # Available options from all user's academic rows regardless of filter
        available_subjects = sorted(list({a["course"] for a in academic_entries if a["course"]}))
        available_assessment_types = sorted(list({a["type"] for a in academic_entries if a["type"]}))

        if not study_entries or not academic_entries:
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": 0,
                "message": "Both study and academic entries are required for regression analysis.",
                "derived_values": {
                    "available_subjects": available_subjects,
                    "available_assessment_types": available_assessment_types,
                    "n_assessments": 0,
                    "skipped_unit_count": skipped_unit_count,
                    "dropped_no_coverage": 0,
                    "window_days": window_days,
                },
                "correlation_r_squared": None,
            }

        first_study_date = min(s["date"] for s in study_entries)

        # ── 2. Feature engineering (leakage-safe) ──────────────────────
        # Calculate pooled coverage count for all academic entries
        pooled_n = sum(
            1 for a in academic_entries
            if (a["date"] - timedelta(days=window_days)) >= first_study_date
        )

        dropped_no_coverage = 0
        paired_data: List[tuple[float, float]] = []

        for a in academic_entries:
            # Apply subject and assessment type filters
            if norm_subject and a["course_lower"] != norm_subject:
                continue
            if norm_type and a["type_lower"] != norm_type:
                continue

            d = a["date"]
            win_start = d - timedelta(days=window_days)
            win_end = d - timedelta(days=1)

            # Drop assessment if window start precedes first study entry
            if win_start < first_study_date:
                dropped_no_coverage += 1
                continue

            # Sum study hours strictly within [d - W, d - 1]
            study_hours_in_window = sum(
                s["hours"] for s in study_entries
                if win_start <= s["date"] <= win_end
                and (norm_subject is None or s["subject"] == norm_subject)
            )
            avg_daily_hours = study_hours_in_window / float(window_days)
            paired_data.append((avg_daily_hours, a["score"]))

        n = len(paired_data)

        # ── 3. Insufficient data checks ───────────────────────────────
        if n < 8:
            if norm_subject or norm_type:
                filters_used = []
                if norm_subject:
                    filters_used.append(f"subject '{norm_subject}'")
                if norm_type:
                    filters_used.append(f"type '{norm_type}'")
                msg = (
                    f"Only {n} assessments found for {', '.join(filters_used)} (minimum 8 required). "
                    f"There are {pooled_n} total assessments available without filters."
                )
            else:
                msg = (
                    f"At least 8 assessments with prior study logs are required for regression analysis. "
                    f"Currently have {n}."
                )

            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": n,
                "message": msg,
                "derived_values": {
                    "n_assessments": n,
                    "pooled_n": pooled_n,
                    "available_subjects": available_subjects,
                    "available_assessment_types": available_assessment_types,
                    "dropped_no_coverage": dropped_no_coverage,
                    "skipped_unit_count": skipped_unit_count,
                    "window_days": window_days,
                },
                "correlation_r_squared": None,
            }

        x_vals = np.array([p[0] for p in paired_data], dtype=float)
        y_vals = np.array([p[1] for p in paired_data], dtype=float)

        mu_x = float(np.mean(x_vals))
        sigma_x = float(np.std(x_vals, ddof=1))

        if sigma_x < 0.25:
            return {
                "lines": [],
                "reliability": "insufficient",
                "data_point_count": n,
                "message": (
                    "Not enough variation in your study hours to establish a reliable statistical relationship "
                    "(standard deviation < 0.25 hours/day)."
                ),
                "derived_values": {
                    "n_assessments": n,
                    "pooled_n": pooled_n,
                    "observed_avg_daily_hours": round(mu_x, 2),
                    "observed_min_hours": round(float(np.min(x_vals)), 2),
                    "observed_max_hours": round(float(np.max(x_vals)), 2),
                    "available_subjects": available_subjects,
                    "available_assessment_types": available_assessment_types,
                    "dropped_no_coverage": dropped_no_coverage,
                    "skipped_unit_count": skipped_unit_count,
                    "window_days": window_days,
                },
                "correlation_r_squared": None,
            }

        # ── 4. Closed-form Ridge Regression with LOO-CV ───────────────
        x_std = (x_vals - mu_x) / sigma_x
        y_mean = float(np.mean(y_vals))

        s_xx = float(np.sum(x_std ** 2))
        s_xy = float(np.sum(x_std * y_vals))

        best_alpha = RIDGE_ALPHAS[0]
        min_loo_mse = float("inf")

        for alpha in RIDGE_ALPHAS:
            beta_1_cand = s_xy / (s_xx + alpha)
            y_hat_cand = y_mean + beta_1_cand * x_std
            h_ii = (1.0 / n) + (x_std ** 2) / (s_xx + alpha)
            denom = np.maximum(1e-6, 1.0 - h_ii)
            loo_res = (y_vals - y_hat_cand) / denom
            mse = float(np.mean(loo_res ** 2))
            if mse < min_loo_mse:
                min_loo_mse = mse
                best_alpha = alpha

        # Refit with optimal alpha
        beta_0 = y_mean
        beta_1 = s_xy / (s_xx + best_alpha)
        y_hat = beta_0 + beta_1 * x_std
        h_ii = (1.0 / n) + (x_std ** 2) / (s_xx + best_alpha)
        denom = np.maximum(1e-6, 1.0 - h_ii)
        final_loo_res = (y_vals - y_hat) / denom

        ss_res_loo = float(np.sum(final_loo_res ** 2))
        tss = float(np.sum((y_vals - y_mean) ** 2))
        if tss > 0:
            loo_r2 = max(-1.0, min(1.0, 1.0 - (ss_res_loo / tss)))
        else:
            loo_r2 = 0.0

        loo_r2 = round(float(loo_r2), 4)
        q = float(np.percentile(np.abs(final_loo_res), 80))

        # Reliability tier
        if n < 8:
            reliability = "insufficient"
        elif n < 14 or loo_r2 < 0.3:
            reliability = "low_confidence"
        else:
            reliability = "reliable"

        # ── 5. Build grid points (0.0 to 8.0, step 0.1) ───────────────
        grid_h = np.round(np.arange(0.0, 8.05, 0.1), 1)
        expected_pts = []
        best_pts = []
        risk_pts = []

        for h in grid_h:
            h_std = (h - mu_x) / sigma_x
            pred_y = beta_0 + beta_1 * h_std

            exp_val = round(float(np.clip(pred_y, 0.0, 100.0)), 2)
            best_val = round(float(np.clip(pred_y + q, 0.0, 100.0)), 2)
            risk_val = round(float(np.clip(pred_y - q, 0.0, 100.0)), 2)

            date_str = f"{h:.1f}h"
            x_num = round(float(h), 1)
            expected_pts.append({"date": date_str, "value": exp_val, "x": x_num})
            best_pts.append({"date": date_str, "value": best_val, "x": x_num})
            risk_pts.append({"date": date_str, "value": risk_val, "x": x_num})

        lines = [
            {"label": "expected_case", "points": expected_pts},
            {"label": "best_case", "points": best_pts},
            {"label": "risk_case", "points": risk_pts},
        ]

        # ── 6. Derived values & slider metrics ────────────────────────
        def predict_score(val: float) -> float:
            h_std = (val - mu_x) / sigma_x
            pred = beta_0 + beta_1 * h_std
            return float(np.clip(pred, 0.0, 100.0))

        curr_h_param = params.get("current_daily_hours")
        sim_h_param = params.get("simulated_daily_hours")

        current_daily_hours = (
            round(float(curr_h_param), 2)
            if curr_h_param is not None
            else round(mu_x, 2)
        )
        simulated_daily_hours = (
            round(float(sim_h_param), 2)
            if sim_h_param is not None
            else current_daily_hours
        )

        baseline_score = round(predict_score(current_daily_hours), 2)
        scenario_score = round(predict_score(simulated_daily_hours), 2)
        absolute_diff_pp = round(scenario_score - baseline_score, 2)
        relative_diff_pct = round(
            ((scenario_score - baseline_score) / baseline_score * 100.0)
            if baseline_score > 0
            else 0.0,
            2,
        )

        r2_desc = (
            "strong" if loo_r2 >= 0.5 else ("moderate" if loo_r2 >= 0.3 else "weak")
        )
        message = (
            f"Based on historical data across {n} assessments (LOO R²={loo_r2:.2f}, {r2_desc}), "
            f"adjusting study routine from {current_daily_hours:.2f}h to {simulated_daily_hours:.2f}h daily is associated with "
            f"a projected score change from {baseline_score:.1f}% to {scenario_score:.1f}% ({absolute_diff_pp:+.1f} pp). "
            f"This reflects an observed statistical correlation in your logs, not a guaranteed causal outcome."
        )

        derived_values = {
            "observed_avg_daily_hours": round(mu_x, 2),
            "observed_min_hours": round(float(np.min(x_vals)), 2),
            "observed_max_hours": round(float(np.max(x_vals)), 2),
            "n_assessments": int(n),
            "loo_alpha": float(best_alpha),
            "available_subjects": available_subjects,
            "available_assessment_types": available_assessment_types,
            "baseline_score": baseline_score,
            "scenario_score": scenario_score,
            "absolute_difference_pp": absolute_diff_pp,
            "relative_difference_pct": relative_diff_pct,
            "current_daily_hours": current_daily_hours,
            "simulated_daily_hours": simulated_daily_hours,
            "window_days": window_days,
            "dropped_no_coverage": dropped_no_coverage,
            "skipped_unit_count": skipped_unit_count,
            "interval_q": round(q, 2),
            "regression_slope": round(float(beta_1 / sigma_x), 4),
            "regression_intercept": round(float(beta_0 - beta_1 * mu_x / sigma_x), 4),
        }

        return {
            "lines": lines,
            "reliability": reliability,
            "data_point_count": n,
            "message": message,
            "derived_values": derived_values,
            "correlation_r_squared": loo_r2,
        }
