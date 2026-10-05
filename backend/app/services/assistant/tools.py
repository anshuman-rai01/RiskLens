"""
Tool registry and deterministic tool implementations for the RiskLens AI Assistant.

Two read-only tools:
- get_forecast: Predict future income, expenses, savings, or overall finances using Prophet.
- build_report: Summarize past-period financial performance with metrics and charts.

Design principles:
- The LLM never computes or hallucinates user numbers; tools compute everything deterministically.
- user_id is injected via ToolContext (from JWT), never exposed as an LLM argument.
- Each tool opens its own short-lived async session via async_session().
- User-controlled strings (labels) are strictly sanitized and truncated before returning.
- Tool result data payloads to the LLM are capped (<= 4KB) to avoid context bloat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Literal, Optional, Tuple, Type
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database import async_session
from app.models.entry import Entry
from app.schemas.assistant import (
    Block,
    ChartBand,
    ChartSeries,
    MetricItem,
)
from app.services.assistant.blocks import (
    build_chart_block,
    build_metrics_block,
    build_notice_block,
)
from app.services.assistant.llm import ToolDeclaration
from app.services.forecasting import compute_forecast

logger = logging.getLogger(__name__)


# ── Context & Result Container ───────────────────────────────────

@dataclass
class ToolContext:
    user_id: str
    client_date: date


@dataclass
class ToolExecutionResult:
    data: Dict[str, Any]
    blocks: List[Block]


# ── Helpers ──────────────────────────────────────────────────────

def sanitize_label(text: Optional[str], max_len: int = 40) -> str:
    """Strip ASCII control characters and truncate to max_len."""
    if not text:
        return "Uncategorized"
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text).strip()
    return cleaned[:max_len] if cleaned else "Uncategorized"


def cap_data_payload(data: Dict[str, Any], max_bytes: int = 4096) -> Dict[str, Any]:
    """Ensure data payload serialized size is within max_bytes."""
    raw = json.dumps(data)
    if len(raw.encode("utf-8")) <= max_bytes:
        return data
    # If oversized, trim top lists if present
    trimmed = dict(data)
    if "top_expenses" in trimmed and isinstance(trimmed["top_expenses"], list):
        trimmed["top_expenses"] = trimmed["top_expenses"][:3]
    return trimmed


# ── Tool 1: get_forecast ─────────────────────────────────────────

class GetForecastArgs(BaseModel):
    series: Literal["expenses", "income", "savings", "finances"] = Field(
        ...,
        description="The financial series to forecast: expenses, income, savings, or finances (income and expenses together)."
    )
    horizon_days: int = Field(
        default=30,
        ge=1,
        le=90,
        description="Forecast horizon in days (1 to 90)."
    )


GET_FORECAST_DECLARATION = ToolDeclaration(
    name="get_forecast",
    description=(
        "Predict the user's future income, expenses, savings, or overall finances "
        "(income and expenses together with the net) for the next N days, using their tracked history. "
        "Use for any question about what will happen to their money. Do not use for past data."
    ),
    parameters=GetForecastArgs.model_json_schema(),
)


FORECAST_SERIES_CONFIG: Dict[str, Dict[str, Any]] = {
    "expenses": {
        "label": "Expenses",
        "category": "income_expense",
        "filter": lambda e: (e.notes or "").strip().lower() == "expense",
        "role": "expense",
    },
    "income": {
        "label": "Income",
        "category": "income_expense",
        "filter": lambda e: (e.notes or "").strip().lower() == "income",
        "role": "income",
    },
    "savings": {
        "label": "Savings",
        "category": "savings",
        "filter": lambda e: True,
        "role": "savings",
    },
}

RELIABILITY_RANK = {
    "insufficient": 0,
    "low_confidence": 1,
    "reliable": 2,
}


async def _run_single_forecast(
    user_id: str,
    series_key: str,
    horizon_days: int,
    today: date,
) -> Dict[str, Any]:
    cfg = FORECAST_SERIES_CONFIG[series_key]
    async with async_session() as db:
        stmt = (
            select(Entry)
            .where(
                Entry.user_id == user_id,
                Entry.deleted_at.is_(None),
                Entry.category == cfg["category"],
            )
        )
        res = await db.execute(stmt)
        all_entries = res.scalars().all()

    # Filter in Python
    filtered = [e for e in all_entries if cfg["filter"](e)]

    # Run Prophet in thread pool
    forecast_res = await asyncio.to_thread(
        compute_forecast,
        entries=filtered,
        horizon_days=horizon_days,
        freq="D",
        zero_fill=True,
        as_of=today,
    )

    # Clamp money predictions at 0
    for p in forecast_res.get("forecast_points", []):
        p["predicted"] = max(0.0, float(p.get("predicted", 0.0)))
        p["lower"] = max(0.0, float(p.get("lower", 0.0)))
        p["upper"] = max(0.0, float(p.get("upper", 0.0)))

    # Compute trailing actual total over the same horizon
    past_cutoff = today - timedelta(days=horizon_days)
    trailing_actual = sum(
        float(e.value)
        for e in filtered
        if past_cutoff < e.occurred_at <= today
    )

    return {
        "forecast": forecast_res,
        "trailing_actual": trailing_actual,
        "filtered_entries": filtered,
    }


async def execute_get_forecast(
    args: GetForecastArgs,
    context: ToolContext,
) -> ToolExecutionResult:
    today = context.client_date
    blocks: List[Block] = []

    if args.series != "finances":
        res = await _run_single_forecast(context.user_id, args.series, args.horizon_days, today)
        fc = res["forecast"]
        rel = fc["reliability"]
        active_days = fc["data_point_count"]

        if rel == "insufficient":
            data = {
                "status": "insufficient_data",
                "series": args.series,
                "horizon_days": args.horizon_days,
                "reliability": rel,
                "active_days": active_days,
                "required_days": 14,
            }
            blocks.append(
                build_notice_block(
                    "warn",
                    f"Not enough history yet: {active_days} of 14 days with entries.",
                )
            )
            return ToolExecutionResult(data=cap_data_payload(data), blocks=blocks)

        # Sufficient data
        points = fc["forecast_points"]
        total_pred = sum(p["predicted"] for p in points)
        daily_avg = round(total_pred / args.horizon_days, 2)
        trailing = round(res["trailing_actual"], 2)

        data = {
            "status": "ok",
            "series": args.series,
            "horizon_days": args.horizon_days,
            "reliability": rel,
            "active_days": active_days,
            "required_days": 14,
            "total_predicted": round(total_pred, 2),
            "daily_avg_predicted": daily_avg,
            "trailing_actual_total": trailing,
        }

        if rel == "low_confidence":
            blocks.append(
                build_notice_block(
                    "info",
                    f"Rough estimate: based on {active_days} days of entries.",
                )
            )

        series_label = FORECAST_SERIES_CONFIG[args.series]["label"]
        blocks.append(
            build_metrics_block(
                title=f"{series_label} Forecast Summary",
                items=[
                    MetricItem(
                        label="Predicted Total",
                        value=round(total_pred, 2),
                        format="currency",
                        tone="neutral",
                    ),
                    MetricItem(
                        label="Daily Average",
                        value=daily_avg,
                        format="currency",
                        tone="neutral",
                    ),
                    MetricItem(
                        label=f"Past {args.horizon_days}d Actual",
                        value=trailing,
                        format="currency",
                        tone="neutral",
                    ),
                ],
            )
        )

        chart_role = FORECAST_SERIES_CONFIG[args.series]["role"]
        chart_data = [
            {
                "x": p["date"],
                "predicted": p["predicted"],
                "lower": p["lower"],
                "upper": p["upper"],
            }
            for p in points
        ]
        blocks.append(
            build_chart_block(
                title=f"{series_label} Forecast ({args.horizon_days} Days)",
                kind="line",
                x_format="date",
                y_format="currency",
                series=[
                    ChartSeries(key="predicted", label="Predicted", role="forecast"),
                ],
                band=ChartBand(lower_key="lower", upper_key="upper"),
                data=chart_data,
            )
        )

        return ToolExecutionResult(data=cap_data_payload(data), blocks=blocks)

    else:
        # finances = expenses + income run concurrently
        exp_res, inc_res = await asyncio.gather(
            _run_single_forecast(context.user_id, "expenses", args.horizon_days, today),
            _run_single_forecast(context.user_id, "income", args.horizon_days, today),
        )

        exp_fc = exp_res["forecast"]
        inc_fc = inc_res["forecast"]

        rel_order = ["insufficient", "low_confidence", "reliable"]
        exp_rel = exp_fc["reliability"]
        inc_rel = inc_fc["reliability"]
        weaker_idx = min(rel_order.index(exp_rel), rel_order.index(inc_rel))
        overall_rel = rel_order[weaker_idx]

        if overall_rel == "insufficient":
            data = {
                "status": "insufficient_data",
                "series": "finances",
                "horizon_days": args.horizon_days,
                "reliability": overall_rel,
                "expenses_reliability": exp_rel,
                "income_reliability": inc_rel,
                "expenses_active_days": exp_fc["data_point_count"],
                "income_active_days": inc_fc["data_point_count"],
                "required_days": 14,
            }
            blocks.append(
                build_notice_block(
                    "warn",
                    "Not enough history yet to forecast overall finances (requires at least 14 days of both income and expense entries).",
                )
            )
            return ToolExecutionResult(data=cap_data_payload(data), blocks=blocks)

        exp_points = exp_fc["forecast_points"]
        inc_points = inc_fc["forecast_points"]
        exp_total = sum(p["predicted"] for p in exp_points)
        inc_total = sum(p["predicted"] for p in inc_points)
        net_pred = inc_total - exp_total

        data = {
            "status": "ok",
            "series": "finances",
            "horizon_days": args.horizon_days,
            "reliability": overall_rel,
            "expected_expenses": round(exp_total, 2),
            "expected_income": round(inc_total, 2),
            "net_predicted": round(net_pred, 2),
            "expenses_active_days": exp_fc["data_point_count"],
            "income_active_days": inc_fc["data_point_count"],
            "required_days": 14,
        }

        if overall_rel == "low_confidence":
            blocks.append(
                build_notice_block(
                    "info",
                    "Rough estimate: based on limited history for income or expenses.",
                )
            )

        blocks.append(
            build_metrics_block(
                title="Finances Outlook Summary",
                items=[
                    MetricItem(
                        label="Expected Expenses",
                        value=round(exp_total, 2),
                        format="currency",
                        tone="neutral",
                    ),
                    MetricItem(
                        label="Expected Income",
                        value=round(inc_total, 2),
                        format="currency",
                        tone="ok",
                    ),
                    MetricItem(
                        label="Expected Net",
                        value=round(net_pred, 2),
                        format="currency",
                        tone="ok" if net_pred >= 0 else "danger",
                    ),
                ],
            )
        )

        # Merge daily income & expense lines
        inc_map = {p["date"]: p["predicted"] for p in inc_points}
        exp_map = {p["date"]: p["predicted"] for p in exp_points}
        all_dates = sorted(set(inc_map.keys()) | set(exp_map.keys()))

        chart_data = [
            {
                "x": d,
                "income": inc_map.get(d, 0.0),
                "expense": exp_map.get(d, 0.0),
            }
            for d in all_dates
        ]

        blocks.append(
            build_chart_block(
                title=f"Finances Projection ({args.horizon_days} Days)",
                kind="line",
                x_format="date",
                y_format="currency",
                series=[
                    ChartSeries(key="income", label="Income", role="income"),
                    ChartSeries(key="expense", label="Expenses", role="expense"),
                ],
                band=None,
                data=chart_data,
            )
        )

        return ToolExecutionResult(data=cap_data_payload(data), blocks=blocks)


# ── Tool 2: build_report ─────────────────────────────────────────

class BuildReportArgs(BaseModel):
    period: Literal["last_7_days", "last_30_days", "this_month", "last_month", "custom"] = Field(
        default="last_7_days",
        description="Past period to summarize."
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date for custom period (YYYY-MM-DD)."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date for custom period (YYYY-MM-DD)."
    )


BUILD_REPORT_DECLARATION = ToolDeclaration(
    name="build_report",
    description=(
        "Summarize the user's tracked income, expenses and savings over a past period and show charts. "
        "Use for reports, summaries, and questions like 'how much did I spend'."
    ),
    parameters=BuildReportArgs.model_json_schema(),
)


def resolve_report_window(
    period: str,
    client_date: date,
    start_str: Optional[str],
    end_str: Optional[str],
) -> Tuple[date, date]:
    """Resolve start and end dates strictly from client_date."""
    if period == "last_7_days":
        return client_date - timedelta(days=6), client_date
    elif period == "last_30_days":
        return client_date - timedelta(days=29), client_date
    elif period == "this_month":
        start = date(client_date.year, client_date.month, 1)
        return start, client_date
    elif period == "last_month":
        if client_date.month == 1:
            prev_year = client_date.year - 1
            prev_month = 12
        else:
            prev_year = client_date.year
            prev_month = client_date.month - 1
        start = date(prev_year, prev_month, 1)
        # End of last month = day before 1st of current month
        end = date(client_date.year, client_date.month, 1) - timedelta(days=1)
        return start, end
    elif period == "custom":
        if not start_str or not end_str:
            raise ValueError("start_date and end_date are required for custom period")
        s = date.fromisoformat(start_str)
        e = date.fromisoformat(end_str)
        if s > e:
            raise ValueError("start_date cannot be after end_date")
        if e > client_date:
            raise ValueError("end_date cannot be in the future")
        span = (e - s).days + 1
        if span > 62:
            raise ValueError("custom period span cannot exceed 62 days")
        return s, e
    else:
        return client_date - timedelta(days=6), client_date


async def execute_build_report(
    args: BuildReportArgs,
    context: ToolContext,
) -> ToolExecutionResult:
    try:
        start_date, end_date = resolve_report_window(
            args.period,
            context.client_date,
            args.start_date,
            args.end_date,
        )
    except Exception as exc:
        data = {
            "status": "error",
            "error": "invalid_arguments",
            "message": str(exc),
        }
        return ToolExecutionResult(data=data, blocks=[])

    async with async_session() as db:
        stmt = (
            select(Entry)
            .where(
                Entry.user_id == context.user_id,
                Entry.deleted_at.is_(None),
                Entry.occurred_at >= start_date,
                Entry.occurred_at <= end_date,
                Entry.category.in_(["income_expense", "savings"]),
            )
        )
        res = await db.execute(stmt)
        entries = res.scalars().all()

    income_entries: List[Entry] = []
    expense_entries: List[Entry] = []
    savings_entries: List[Entry] = []
    untagged_entries: List[Entry] = []

    for e in entries:
        if e.category == "savings":
            savings_entries.append(e)
        elif e.category == "income_expense":
            kind = (e.notes or "").strip().lower()
            if kind == "income":
                income_entries.append(e)
            elif kind == "expense":
                expense_entries.append(e)
            else:
                untagged_entries.append(e)

    entries_counted = len(income_entries) + len(expense_entries) + len(savings_entries)
    untagged_count = len(untagged_entries)

    if entries_counted == 0:
        data = {
            "status": "no_data",
            "period": args.period,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        blocks = [
            build_notice_block("info", "No financial entries were found for this period.")
        ]
        return ToolExecutionResult(data=cap_data_payload(data), blocks=blocks)

    income_total = sum(float(e.value) for e in income_entries)
    expense_total = sum(float(e.value) for e in expense_entries)
    savings_added = sum(float(e.value) for e in savings_entries)
    net = income_total - expense_total

    # Top 5 expense categories
    cat_totals: Dict[str, float] = {}
    for e in expense_entries:
        raw_sub = (e.subcategory or "").strip().lower()
        cat_name = sanitize_label(e.subcategory or "Uncategorized")
        # Group case-insensitively
        cat_totals[cat_name] = cat_totals.get(cat_name, 0.0) + float(e.value)

    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:5]
    top_expenses = [
        {
            "label": name,
            "amount": round(val, 2),
            "share_pct": round((val / expense_total * 100), 1) if expense_total > 0 else 0.0,
        }
        for name, val in sorted_cats
    ]

    data = {
        "status": "ok",
        "period": args.period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "income_total": round(income_total, 2),
        "expense_total": round(expense_total, 2),
        "net": round(net, 2),
        "savings_added": round(savings_added, 2),
        "entries_counted": entries_counted,
        "untagged_count": untagged_count,
        "top_expenses": top_expenses,
    }

    blocks: List[Block] = []

    # 1. Metrics block
    blocks.append(
        build_metrics_block(
            title=f"Financial Summary ({start_date.isoformat()} to {end_date.isoformat()})",
            items=[
                MetricItem(
                    label="Income",
                    value=round(income_total, 2),
                    format="currency",
                    tone="ok",
                ),
                MetricItem(
                    label="Expenses",
                    value=round(expense_total, 2),
                    format="currency",
                    tone="danger" if expense_total > 0 else "neutral",
                ),
                MetricItem(
                    label="Net",
                    value=round(net, 2),
                    format="currency",
                    tone="ok" if net >= 0 else "danger",
                ),
                MetricItem(
                    label="Savings Added",
                    value=round(savings_added, 2),
                    format="currency",
                    tone="neutral",
                ),
            ],
        )
    )

    # 2. Daily or weekly income vs expense bar chart
    span_days = (end_date - start_date).days + 1
    if span_days <= 31:
        # Zero-filled daily breakdown
        day_inc: Dict[str, float] = {}
        day_exp: Dict[str, float] = {}
        for e in income_entries:
            d_str = e.occurred_at.isoformat()
            day_inc[d_str] = day_inc.get(d_str, 0.0) + float(e.value)
        for e in expense_entries:
            d_str = e.occurred_at.isoformat()
            day_exp[d_str] = day_exp.get(d_str, 0.0) + float(e.value)

        chart_data: List[Dict[str, Any]] = []
        cur = start_date
        while cur <= end_date:
            cur_str = cur.isoformat()
            chart_data.append({
                "x": cur_str,
                "income": round(day_inc.get(cur_str, 0.0), 2),
                "expense": round(day_exp.get(cur_str, 0.0), 2),
            })
            cur += timedelta(days=1)

        blocks.append(
            build_chart_block(
                title="Daily Income vs Expenses",
                kind="bar",
                x_format="date",
                y_format="currency",
                series=[
                    ChartSeries(key="income", label="Income", role="income"),
                    ChartSeries(key="expense", label="Expenses", role="expense"),
                ],
                data=chart_data,
            )
        )
    else:
        # Weekly bucketing (Monday start)
        week_inc: Dict[str, float] = {}
        week_exp: Dict[str, float] = {}
        for e in income_entries:
            mon = (e.occurred_at - timedelta(days=e.occurred_at.weekday())).isoformat()
            week_inc[mon] = week_inc.get(mon, 0.0) + float(e.value)
        for e in expense_entries:
            mon = (e.occurred_at - timedelta(days=e.occurred_at.weekday())).isoformat()
            week_exp[mon] = week_exp.get(mon, 0.0) + float(e.value)

        # Generate all Monday weeks from start_date to end_date
        first_mon = start_date - timedelta(days=start_date.weekday())
        cur_mon = first_mon
        weekly_data: List[Dict[str, Any]] = []
        while cur_mon <= end_date:
            mon_str = cur_mon.isoformat()
            weekly_data.append({
                "x": mon_str,
                "income": round(week_inc.get(mon_str, 0.0), 2),
                "expense": round(week_exp.get(mon_str, 0.0), 2),
            })
            cur_mon += timedelta(days=7)

        blocks.append(
            build_chart_block(
                title="Weekly Income vs Expenses",
                kind="bar",
                x_format="date",
                y_format="currency",
                series=[
                    ChartSeries(key="income", label="Income", role="income"),
                    ChartSeries(key="expense", label="Expenses", role="expense"),
                ],
                data=weekly_data,
            )
        )

    # 3. Top expenses chart (if expense data exists)
    if expense_total > 0 and top_expenses:
        top_chart_data = [
            {"x": item["label"], "amount": item["amount"]}
            for item in top_expenses
        ]
        blocks.append(
            build_chart_block(
                title="Top Expenses",
                kind="bar",
                x_format="category",
                y_format="currency",
                series=[
                    ChartSeries(key="amount", label="Expenses", role="expense"),
                ],
                data=top_chart_data,
            )
        )

    # 4. Notice block for untagged entries if any
    if untagged_count > 0:
        blocks.append(
            build_notice_block(
                "info",
                f"{untagged_count} income/expense entries have no type and were left out.",
            )
        )

    return ToolExecutionResult(data=cap_data_payload(data), blocks=blocks)


# ── Registry Definition ──────────────────────────────────────────

@dataclass
class RegisteredTool:
    name: str
    declaration: ToolDeclaration
    args_model: Type[BaseModel]
    handler: Callable[[Any, ToolContext], Coroutine[Any, Any, ToolExecutionResult]]


TOOL_REGISTRY: Dict[str, RegisteredTool] = {
    "get_forecast": RegisteredTool(
        name="get_forecast",
        declaration=GET_FORECAST_DECLARATION,
        args_model=GetForecastArgs,
        handler=execute_get_forecast,
    ),
    "build_report": RegisteredTool(
        name="build_report",
        declaration=BUILD_REPORT_DECLARATION,
        args_model=BuildReportArgs,
        handler=execute_build_report,
    ),
}


def get_tool_registry() -> Dict[str, RegisteredTool]:
    """Return the global tool registry dictionary."""
    return TOOL_REGISTRY
