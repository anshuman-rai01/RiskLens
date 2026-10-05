"""
Tests for compute_forecast zero_fill and as_of parameters.
Verifies sparse series handling, synthetic zeros not inflating reliability,
and anchoring the horizon to as_of.
"""

from datetime import date, timedelta
import pytest
from app.services.forecasting import compute_forecast


class DummyEntry:
    def __init__(self, occurred_at: date, value: float):
        self.occurred_at = occurred_at
        self.value = value


@pytest.mark.parametrize("offset", list(range(7)))
def test_zero_fill_sparse_series_and_as_of(offset: int):
    base_date = date(2026, 1, 1) + timedelta(days=offset)
    # 70 days, entry every 3rd day of ₹100 -> 24 active entries
    entries = [
        DummyEntry(base_date + timedelta(days=i), 100.0)
        for i in range(0, 70, 3)
    ]
    active_days_count = len(entries)
    as_of = base_date + timedelta(days=70)

    # 1. Default mode (zero_fill=False)
    res_default = compute_forecast(entries, horizon_days=30, zero_fill=False)
    total_default = sum(p["predicted"] for p in res_default["forecast_points"])

    # 2. Zero-fill mode (zero_fill=True, as_of provided)
    res_zf = compute_forecast(entries, horizon_days=30, zero_fill=True, as_of=as_of)
    total_zf = sum(p["predicted"] for p in res_zf["forecast_points"])

    # Data point count must equal active entry days, NOT inflated by synthetic zeros
    assert res_zf["data_point_count"] == active_days_count
    assert res_zf["reliability"] == "low_confidence"  # 24 is in [14, 27]

    # Predicted total with zero_fill must be below half the default-mode total
    assert total_zf < (total_default / 2.0)
    # Measured around 900-1100 for true mean ≈ 1000
    assert 800.0 <= total_zf <= 1200.0

    # The forecast's first date is the day after as_of
    expected_first_date = (as_of + timedelta(days=1)).strftime("%Y-%m-%d")
    assert res_zf["forecast_points"][0]["date"] == expected_first_date
