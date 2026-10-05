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
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Literal, Optional, Tuple, Type
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.database import async_session
from app.models.entry import Entry
from app.schemas.assistant import (
    Block,
    ChartBand,
    ChartSeries,
    MetricItem,
    TableColumn,
)
from app.services.assistant.blocks import (
    build_chart_block,
    build_confirm_delete_block,
    build_confirm_entry_block,
    build_metrics_block,
    build_notice_block,
    build_table_block,
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


# ── Helper for safe date parsing ─────────────────────────────────

def _safe_parse_date(val: Optional[str]) -> Optional[date]:
    if not val:
        return None
    try:
        return date.fromisoformat(val.strip())
    except (ValueError, TypeError):
        return None


# ── Tool 3: find_entries ─────────────────────────────────────────

class FindEntriesArgs(BaseModel):
    category: Literal["income_expense", "savings", "study", "academic", "fitness", "habits"] = Field(
        ...,
        description="The category to search entries in."
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Filter entries on or after this date (YYYY-MM-DD)."
    )
    end_date: Optional[str] = Field(
        default=None,
        description="Filter entries on or before this date (YYYY-MM-DD)."
    )
    search_text: Optional[str] = Field(
        default=None,
        description="Case-insensitive substring search in description, subcategory, or notes."
    )
    kind: Optional[Literal["income", "expense"]] = Field(
        default=None,
        description="Only for income_expense: filter by 'income' or 'expense'."
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum entries to return (default 10, max 25)."
    )


FIND_ENTRIES_DECLARATION = ToolDeclaration(
    name="find_entries",
    description=(
        "Search and filter the user's existing tracked entries across categories (income_expense, "
        "savings, study, academic, fitness, habits). Always call this tool BEFORE proposing deletions, "
        "and whenever the user asks to see, list, check, or find entries."
    ),
    parameters=FindEntriesArgs.model_json_schema(),
)


async def execute_find_entries(
    args: FindEntriesArgs,
    context: ToolContext,
) -> ToolExecutionResult:
    """
    Search and filter existing user entries without mutating anything.
    Excludes soft-deleted entries and enforces user isolation.
    """
    try:
        user_uuid = uuid.UUID(str(context.user_id))
    except Exception:
        user_uuid = context.user_id

    conditions = [
        Entry.user_id == user_uuid,
        Entry.category == args.category,
        Entry.deleted_at.is_(None),
    ]

    parsed_start = _safe_parse_date(args.start_date)
    if parsed_start:
        conditions.append(Entry.occurred_at >= parsed_start)

    parsed_end = _safe_parse_date(args.end_date)
    if parsed_end:
        conditions.append(Entry.occurred_at <= parsed_end)

    if args.category == "income_expense" and args.kind:
        conditions.append(Entry.notes.ilike(f"%{args.kind.strip()}%"))

    if args.search_text and args.search_text.strip():
        kw = f"%{args.search_text.strip()}%"
        conditions.append(or_(Entry.notes.ilike(kw), Entry.subcategory.ilike(kw)))

    async with async_session() as db:
        count_stmt = select(func.count()).select_from(Entry).where(*conditions)
        total_result = await db.execute(count_stmt)
        total_matches = total_result.scalar() or 0

        cat_title = args.category.replace("_", " ").title()

        if total_matches == 0:
            return ToolExecutionResult(
                data={
                    "status": "no_data",
                    "category": args.category,
                    "total_matches": 0,
                    "returned_count": 0,
                    "entries": [],
                },
                blocks=[
                    build_notice_block(
                        tone="info",
                        text=f"No {cat_title.lower()} entries found matching your criteria.",
                    )
                ],
            )

        fetch_limit = min(args.limit, 25)
        stmt = (
            select(Entry)
            .where(*conditions)
            .order_by(Entry.occurred_at.desc(), Entry.created_at.desc())
            .limit(fetch_limit)
        )
        result = await db.execute(stmt)
        entries = list(result.scalars().all())

    # Build data payload for LLM
    entry_items: List[Dict[str, Any]] = []
    for e in entries:
        item: Dict[str, Any] = {
            "id": str(e.id),
            "date": e.occurred_at.isoformat(),
            "category": e.category,
            "subcategory": e.subcategory or "",
            "value": float(e.value),
            "unit": e.unit or "",
            "notes": e.notes or "",
        }
        if e.max_value is not None:
            item["max_value"] = float(e.max_value)
        entry_items.append(item)

    # Build TableBlock columns and rows tailored to the category
    columns: List[TableColumn] = []
    rows: List[Dict[str, Any]] = []

    if args.category == "income_expense":
        columns = [
            TableColumn(key="date", label="Date"),
            TableColumn(key="kind", label="Type"),
            TableColumn(key="category", label="Category"),
            TableColumn(key="amount", label="Amount", align="right"),
        ]
        for e in entries:
            rows.append({
                "id": str(e.id),
                "date": e.occurred_at.isoformat(),
                "kind": (e.notes or "expense").strip().capitalize(),
                "category": sanitize_label(e.subcategory or "General"),
                "amount": f"₹{float(e.value):,.2f}",
            })
    elif args.category == "savings":
        columns = [
            TableColumn(key="date", label="Date"),
            TableColumn(key="vault", label="Vault"),
            TableColumn(key="amount", label="Amount", align="right"),
        ]
        for e in entries:
            rows.append({
                "id": str(e.id),
                "date": e.occurred_at.isoformat(),
                "vault": sanitize_label(e.subcategory or "General"),
                "amount": f"₹{float(e.value):,.2f}",
            })
    elif args.category == "study":
        columns = [
            TableColumn(key="date", label="Date"),
            TableColumn(key="subject", label="Subject"),
            TableColumn(key="hours", label="Hours", align="right"),
            TableColumn(key="topic", label="Topic"),
        ]
        for e in entries:
            rows.append({
                "id": str(e.id),
                "date": e.occurred_at.isoformat(),
                "subject": sanitize_label(e.subcategory or "General"),
                "hours": f"{float(e.value):g} hrs",
                "topic": sanitize_label(e.notes or "—"),
            })
    elif args.category == "academic":
        columns = [
            TableColumn(key="date", label="Date"),
            TableColumn(key="course", label="Course"),
            TableColumn(key="assessment", label="Assessment"),
            TableColumn(key="score", label="Score", align="right"),
        ]
        for e in entries:
            score_str = f"{float(e.value):g}/{float(e.max_value):g}" if e.max_value else f"{float(e.value):g}"
            rows.append({
                "id": str(e.id),
                "date": e.occurred_at.isoformat(),
                "course": sanitize_label(e.subcategory or "General"),
                "assessment": sanitize_label(e.notes or "—"),
                "score": score_str,
            })
    elif args.category == "fitness":
        columns = [
            TableColumn(key="date", label="Date"),
            TableColumn(key="activity", label="Activity"),
            TableColumn(key="duration", label="Duration", align="right"),
            TableColumn(key="intensity", label="Intensity"),
        ]
        for e in entries:
            rows.append({
                "id": str(e.id),
                "date": e.occurred_at.isoformat(),
                "activity": sanitize_label(e.subcategory or "General"),
                "duration": f"{int(e.value)} min",
                "intensity": sanitize_label(e.notes or "Moderate").capitalize(),
            })
    elif args.category == "habits":
        columns = [
            TableColumn(key="date", label="Date"),
            TableColumn(key="habit", label="Habit"),
            TableColumn(key="status", label="Status", align="center"),
        ]
        for e in entries:
            rows.append({
                "id": str(e.id),
                "date": e.occurred_at.isoformat(),
                "habit": sanitize_label(e.subcategory or "General"),
                "status": "Done" if float(e.value) >= 1.0 else "Missed",
            })

    category_titles = {
        "income_expense": "Income & Expenses Entries",
        "savings": "Savings Entries",
        "study": "Study Entries",
        "academic": "Academic Entries",
        "fitness": "Fitness Entries",
        "habits": "Habits Entries",
    }
    table_block = build_table_block(
        title=category_titles.get(args.category, f"{cat_title} Entries"),
        columns=columns,
        rows=rows,
        total_count=total_matches,
    )

    data = {
        "status": "ok",
        "category": args.category,
        "total_matches": total_matches,
        "returned_count": len(entries),
        "entries": entry_items,
    }

    return ToolExecutionResult(data=cap_data_payload(data), blocks=[table_block])


# ── Registry Definition ──────────────────────────────────────────

@dataclass
class RegisteredTool:
    name: str
    declaration: ToolDeclaration
    args_model: Type[BaseModel]
    handler: Callable[[Any, ToolContext], Coroutine[Any, Any, ToolExecutionResult]]


# ── Tool 4: propose_entry ────────────────────────────────────────

class ProposeEntryArgs(BaseModel):
    category: Literal["income_expense", "savings", "study", "academic", "fitness", "habits"] = Field(
        ...,
        description="Category to create: income_expense, savings, study, academic, fitness, or habits."
    )
    date: Optional[str] = Field(
        default=None,
        description="Date in YYYY-MM-DD format (defaults to user's local date if omitted)."
    )
    data: Dict[str, Any] = Field(
        ...,
        description=(
            "Category-specific data: "
            "income_expense: {kind: 'income'|'expense', amount: number, description: string}; "
            "savings: {amount: number, vault: string}; "
            "study: {subject: string, duration_minutes: number, topic?: string}; "
            "academic: {course: string, assessment: string, obtained_marks: number, maximum_marks: number}; "
            "fitness: {activity: string, duration_minutes: number, intensity?: 'low'|'moderate'|'high'}; "
            "habits: {habit: string, completed?: boolean}."
        )
    )


PROPOSE_ENTRY_DECLARATION = ToolDeclaration(
    name="propose_entry",
    description=(
        "Propose adding a new entry to the user's tracking data. This tool validates the entry "
        "and prepares a confirmation card for the user. It NEVER writes directly to the database; "
        "the user must click Save in the chat widget to confirm."
    ),
    parameters=ProposeEntryArgs.model_json_schema(),
)


async def execute_propose_entry(
    args: ProposeEntryArgs,
    context: ToolContext,
) -> ToolExecutionResult:
    """
    Validate proposed entry data and construct a ConfirmEntryBlock without mutating the database.
    Zero-writes principle: the database is never modified in this tool.
    """
    errors: List[str] = []

    # 1. Validate date
    date_str = args.date.strip() if args.date and args.date.strip() else context.client_date.isoformat()
    parsed_date = _safe_parse_date(date_str)
    if not parsed_date:
        errors.append(f"Invalid date '{date_str}'. Expected format YYYY-MM-DD.")
    else:
        # Check not far future (today + 1 day max)
        max_allowed_date = context.client_date + timedelta(days=1)
        if parsed_date > max_allowed_date:
            errors.append(f"Date {date_str} cannot be in the future (more than 1 day ahead).")

    raw_data = args.data or {}
    payload: Dict[str, Any] = {"date": date_str}
    preview: Dict[str, Any] = {"Date": date_str}
    summary: str = ""

    # 2. Per-category validation and payload mapping
    cat = args.category
    if cat == "income_expense":
        kind = str(raw_data.get("kind", "expense")).strip().lower()
        if kind not in ("income", "expense"):
            errors.append("Type must be 'income' or 'expense'.")

        try:
            amount = float(raw_data.get("amount", 0))
            if amount <= 0:
                errors.append("Amount must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Amount must be a valid positive number.")
            amount = 0.0

        description = str(raw_data.get("description", raw_data.get("label", ""))).strip()
        if not description:
            errors.append("Description is required.")
        elif len(description) > 80:
            errors.append("Description must be under 80 characters.")

        payload.update({
            "kind": kind,
            "amount": round(amount, 2),
            "label": description,
        })
        preview.update({
            "Type": kind.capitalize(),
            "Category / Label": description,
            "Amount": f"₹{amount:,.2f}",
        })
        summary = f"Add {kind}: ₹{amount:,.2f} for {description} on {date_str}"

    elif cat == "savings":
        try:
            amount = float(raw_data.get("amount", 0))
            if amount <= 0:
                errors.append("Amount must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Amount must be a valid positive number.")
            amount = 0.0

        vault = str(raw_data.get("vault", raw_data.get("goal", ""))).strip()
        if not vault:
            errors.append("Vault / Goal name is required.")
        elif len(vault) > 80:
            errors.append("Vault name must be under 80 characters.")

        payload.update({
            "amount": round(amount, 2),
            "vault": vault,
        })
        preview.update({
            "Vault": vault,
            "Amount": f"₹{amount:,.2f}",
        })
        summary = f"Add savings: ₹{amount:,.2f} to {vault} on {date_str}"

    elif cat == "study":
        subject = str(raw_data.get("subject", "")).strip()
        if not subject:
            errors.append("Subject is required.")
        elif len(subject) > 80:
            errors.append("Subject must be under 80 characters.")

        # Accept duration_minutes or hours
        duration_minutes = raw_data.get("duration_minutes")
        if duration_minutes is not None:
            try:
                duration_minutes = float(duration_minutes)
                if duration_minutes <= 0:
                    errors.append("Duration must be greater than 0 minutes.")
            except (ValueError, TypeError):
                errors.append("Duration must be a valid number.")
                duration_minutes = 0.0
        elif "hours" in raw_data:
            try:
                hours = float(raw_data["hours"])
                duration_minutes = hours * 60.0
                if duration_minutes <= 0:
                    errors.append("Duration must be greater than 0.")
            except (ValueError, TypeError):
                errors.append("Hours must be a valid number.")
                duration_minutes = 0.0
        else:
            errors.append("duration_minutes (or hours) is required.")
            duration_minutes = 0.0

        topic = str(raw_data.get("topic", "")).strip()
        if len(topic) > 80:
            errors.append("Topic must be under 80 characters.")

        hours_val = round(duration_minutes / 60.0, 2)
        payload.update({
            "subject": subject,
            "hours": hours_val,
            "topic": topic,
        })
        preview.update({
            "Subject": subject,
            "Duration": f"{int(duration_minutes)} min ({hours_val:g}h)",
            "Topic": topic or "—",
        })
        summary = f"Add study session: {int(duration_minutes)} min of {subject} on {date_str}"

    elif cat == "academic":
        course = str(raw_data.get("course", "")).strip()
        if not course:
            errors.append("Course is required.")
        elif len(course) > 80:
            errors.append("Course must be under 80 characters.")

        assessment = str(raw_data.get("assessment", "")).strip()
        if not assessment:
            errors.append("Assessment name is required.")
        elif len(assessment) > 80:
            errors.append("Assessment name must be under 80 characters.")

        try:
            score = float(raw_data.get("obtained_marks", raw_data.get("score", 0)))
            if score < 0:
                errors.append("Obtained marks cannot be negative.")
        except (ValueError, TypeError):
            errors.append("Obtained marks must be a valid number.")
            score = 0.0

        try:
            max_score = float(raw_data.get("maximum_marks", raw_data.get("maxScore", 0)))
            if max_score <= 0:
                errors.append("Maximum marks must be greater than 0.")
        except (ValueError, TypeError):
            errors.append("Maximum marks must be a valid number.")
            max_score = 0.0

        if score > max_score and max_score > 0:
            errors.append("Obtained marks cannot exceed maximum marks.")

        payload.update({
            "course": course,
            "assessment": assessment,
            "score": round(score, 2),
            "maxScore": round(max_score, 2),
        })
        preview.update({
            "Course": course,
            "Assessment": assessment,
            "Score": f"{score:g} / {max_score:g}",
        })
        summary = f"Add academic score: {score:g}/{max_score:g} for {assessment} in {course} on {date_str}"

    elif cat == "fitness":
        activity = str(raw_data.get("activity", "")).strip()
        if not activity:
            errors.append("Activity is required.")
        elif len(activity) > 80:
            errors.append("Activity must be under 80 characters.")

        try:
            minutes = float(raw_data.get("duration_minutes", raw_data.get("minutes", 0)))
            if minutes <= 0:
                errors.append("Duration must be greater than 0 minutes.")
        except (ValueError, TypeError):
            errors.append("Duration must be a valid number.")
            minutes = 0.0

        intensity = str(raw_data.get("intensity", "moderate")).strip().lower()
        if intensity not in ("low", "moderate", "high"):
            errors.append("Intensity must be 'low', 'moderate', or 'high'.")

        payload.update({
            "activity": activity,
            "minutes": int(minutes),
            "intensity": intensity,
        })
        preview.update({
            "Activity": activity,
            "Duration": f"{int(minutes)} min",
            "Intensity": intensity.capitalize(),
        })
        summary = f"Add fitness: {int(minutes)} min of {activity} ({intensity}) on {date_str}"

    elif cat == "habits":
        habit = str(raw_data.get("habit", "")).strip()
        if not habit:
            errors.append("Habit name is required.")
        elif len(habit) > 80:
            errors.append("Habit name must be under 80 characters.")

        completed_raw = raw_data.get("completed", True)
        if isinstance(completed_raw, str):
            completed = completed_raw.lower() not in ("false", "0", "no")
        else:
            completed = bool(completed_raw)

        payload.update({
            "habit": habit,
            "completed": completed,
        })
        preview.update({
            "Habit": habit,
            "Status": "Completed" if completed else "Missed",
        })
        summary = f"Add habit: {habit} ({'Completed' if completed else 'Missed'}) on {date_str}"

    # 3. Handle errors if any
    if errors:
        return ToolExecutionResult(
            data={
                "status": "invalid",
                "category": cat,
                "errors": errors,
            },
            blocks=[
                build_notice_block(
                    tone="warn",
                    text=f"Cannot propose {cat.replace('_', ' ')} entry: " + "; ".join(errors),
                )
            ],
        )

    # 4. Success: produce ConfirmEntryBlock
    confirm_block = build_confirm_entry_block(
        category=cat,
        payload=payload,
        preview=preview,
        summary=summary,
    )

    data = {
        "status": "ok",
        "category": cat,
        "summary": summary,
        "preview": preview,
        "payload": payload,
    }
    return ToolExecutionResult(data=cap_data_payload(data), blocks=[confirm_block])


# ── Registry Definition ──────────────────────────────────────────

@dataclass
class RegisteredTool:
    name: str
    declaration: ToolDeclaration
    args_model: Type[BaseModel]
    handler: Callable[[Any, ToolContext], Coroutine[Any, Any, ToolExecutionResult]]


# ── Tool 5: propose_delete ───────────────────────────────────────

class ProposeDeleteArgs(BaseModel):
    category: Literal["income_expense", "savings", "study", "academic", "fitness", "habits"] = Field(
        ...,
        description="Category of the entries to delete."
    )
    entry_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=25,
        description="List of entry IDs (UUID strings) to delete."
    )


PROPOSE_DELETE_DECLARATION = ToolDeclaration(
    name="propose_delete",
    description=(
        "Propose deleting one or more existing entries identified by ID. Always call find_entries "
        "first to obtain the exact IDs. This tool validates the entries and prepares a confirmation "
        "card for the user. It NEVER writes directly to the database; the user must click Delete "
        "in the chat widget to confirm."
    ),
    parameters=ProposeDeleteArgs.model_json_schema(),
)


async def execute_propose_delete(
    args: ProposeDeleteArgs,
    context: ToolContext,
) -> ToolExecutionResult:
    """
    Validate proposed entry IDs for deletion without modifying the database.
    Zero-writes principle: the database is never mutated by this tool.
    """
    try:
        user_uuid = uuid.UUID(str(context.user_id))
    except Exception:
        user_uuid = context.user_id

    # Parse UUIDs safely
    parsed_ids: List[uuid.UUID] = []
    invalid_format_ids: List[str] = []
    for raw_id in args.entry_ids:
        try:
            parsed_ids.append(uuid.UUID(str(raw_id).strip()))
        except (ValueError, TypeError):
            invalid_format_ids.append(str(raw_id))

    if invalid_format_ids:
        return ToolExecutionResult(
            data={
                "status": "invalid",
                "error": f"Invalid entry ID format: {', '.join(invalid_format_ids)}",
                "category": args.category,
            },
            blocks=[
                build_notice_block(
                    tone="warn",
                    text=f"Cannot propose deletion: {len(invalid_format_ids)} ID(s) are malformed.",
                )
            ],
        )

    # Query existing active entries belonging to user and category
    async with async_session() as db:
        stmt = (
            select(Entry)
            .where(
                Entry.user_id == user_uuid,
                Entry.category == args.category,
                Entry.id.in_(parsed_ids),
                Entry.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        found_entries = list(result.scalars().all())

    found_by_id = {str(e.id): e for e in found_entries}
    missing_ids = [str(pid) for pid in parsed_ids if str(pid) not in found_by_id]

    if not found_entries:
        return ToolExecutionResult(
            data={
                "status": "not_found",
                "category": args.category,
                "missing_ids": missing_ids,
            },
            blocks=[
                build_notice_block(
                    tone="warn",
                    text=f"None of the requested {args.category.replace('_', ' ')} entries were found or they are already deleted.",
                )
            ],
        )

    # Format found entries for preview
    entries_preview: List[Dict[str, Any]] = []
    for e in found_entries:
        val_str = f"₹{float(e.value):,.2f}" if args.category in ("income_expense", "savings") else f"{float(e.value):g} {e.unit or ''}"
        entries_preview.append({
            "id": str(e.id),
            "date": e.occurred_at.isoformat(),
            "category": e.category,
            "label": sanitize_label(e.subcategory or "General"),
            "value": val_str.strip(),
            "notes": e.notes or "",
        })

    valid_entry_ids = [str(e.id) for e in found_entries]

    if len(valid_entry_ids) == 1:
        e = found_entries[0]
        label = sanitize_label(e.subcategory or "entry")
        summary = f"Delete {args.category.replace('_', ' ')}: {label} from {e.occurred_at.isoformat()}"
    else:
        summary = f"Delete {len(valid_entry_ids)} {args.category.replace('_', ' ')} entries"

    confirm_block = build_confirm_delete_block(
        category=args.category,
        entry_ids=valid_entry_ids,
        entries=entries_preview,
        summary=summary,
    )

    data = {
        "status": "ok",
        "category": args.category,
        "entry_ids": valid_entry_ids,
        "entries": entries_preview,
        "summary": summary,
        **({"warning": f"{len(missing_ids)} ID(s) were not found."} if missing_ids else {}),
    }

    return ToolExecutionResult(data=cap_data_payload(data), blocks=[confirm_block])


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
    "find_entries": RegisteredTool(
        name="find_entries",
        declaration=FIND_ENTRIES_DECLARATION,
        args_model=FindEntriesArgs,
        handler=execute_find_entries,
    ),
    "propose_entry": RegisteredTool(
        name="propose_entry",
        declaration=PROPOSE_ENTRY_DECLARATION,
        args_model=ProposeEntryArgs,
        handler=execute_propose_entry,
    ),
    "propose_delete": RegisteredTool(
        name="propose_delete",
        declaration=PROPOSE_DELETE_DECLARATION,
        args_model=ProposeDeleteArgs,
        handler=execute_propose_delete,
    ),
}


def get_tool_registry() -> Dict[str, RegisteredTool]:
    """Return the global tool registry dictionary."""
    return TOOL_REGISTRY
