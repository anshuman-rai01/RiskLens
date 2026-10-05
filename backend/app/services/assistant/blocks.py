"""
Pure builder functions for structured UI blocks.
Generates validated Pydantic block models (MetricsBlock, ChartBlock, NoticeBlock).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Literal, Optional

from app.schemas.assistant import (
    ChartBand,
    ChartBlock,
    ChartSeries,
    ConfirmDeleteBlock,
    ConfirmEntryBlock,
    MetricItem,
    MetricsBlock,
    NoticeBlock,
    TableBlock,
    TableColumn,
)


def make_block_id(prefix: str = "blk") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def build_metrics_block(
    items: List[MetricItem],
    title: Optional[str] = None,
    block_id: Optional[str] = None,
) -> MetricsBlock:
    """Construct a validated MetricsBlock with 1 to 6 metric items."""
    capped_items = items[:6]
    return MetricsBlock(
        id=block_id or make_block_id("metrics"),
        title=title,
        items=capped_items,
    )


def build_chart_block(
    title: str,
    kind: Literal["line", "bar"],
    x_format: Literal["date", "category"],
    y_format: Literal["currency", "number"],
    series: List[ChartSeries],
    data: List[Dict[str, Any]],
    subtitle: Optional[str] = None,
    band: Optional[ChartBand] = None,
    block_id: Optional[str] = None,
) -> ChartBlock:
    """Construct a validated ChartBlock with up to 3 series and at most 120 data rows."""
    capped_series = series[:3]
    capped_data = data[:120]
    return ChartBlock(
        id=block_id or make_block_id("chart"),
        title=title,
        subtitle=subtitle,
        kind=kind,
        x_format=x_format,
        y_format=y_format,
        series=capped_series,
        band=band,
        data=capped_data,
    )


def build_notice_block(
    tone: Literal["info", "warn"],
    text: str,
    block_id: Optional[str] = None,
) -> NoticeBlock:
    """Construct a validated NoticeBlock."""
    return NoticeBlock(
        id=block_id or make_block_id("notice"),
        tone=tone,
        text=text,
    )


def build_table_block(
    title: str,
    columns: List[TableColumn],
    rows: List[Dict[str, Any]],
    total_count: Optional[int] = None,
    block_id: Optional[str] = None,
) -> TableBlock:
    """Construct a validated TableBlock with up to 8 columns and 50 rows."""
    return TableBlock(
        id=block_id or make_block_id("table"),
        title=title,
        columns=columns[:8],
        rows=rows[:50],
        total_count=total_count,
    )


def build_confirm_entry_block(
    category: str,
    payload: Dict[str, Any],
    preview: Dict[str, Any],
    summary: str,
    block_id: Optional[str] = None,
) -> ConfirmEntryBlock:
    """Construct a validated ConfirmEntryBlock for user write confirmation."""
    return ConfirmEntryBlock(
        id=block_id or make_block_id("confirm_entry"),
        category=category,
        payload=payload,
        preview=preview,
        summary=summary,
    )


def build_confirm_delete_block(
    category: str,
    entry_ids: List[str],
    entries: List[Dict[str, Any]],
    summary: str,
    block_id: Optional[str] = None,
) -> ConfirmDeleteBlock:
    """Construct a validated ConfirmDeleteBlock for user delete confirmation."""
    return ConfirmDeleteBlock(
        id=block_id or make_block_id("confirm_delete"),
        category=category,
        entry_ids=entry_ids[:25],
        entries=entries[:25],
        summary=summary,
    )
