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
    MetricItem,
    MetricsBlock,
    NoticeBlock,
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
