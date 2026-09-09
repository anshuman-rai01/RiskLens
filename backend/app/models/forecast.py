"""
Forecast SQLAlchemy ORM model for cached series forecasts, confidence intervals,
and reliability metrics.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    subcategory: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    horizon_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=14,
    )
    forecast_points: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    data_point_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    reliability: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "category",
            "subcategory",
            name="uq_forecasts_user_category_subcategory",
            postgresql_nulls_not_distinct=True,
        ),
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User",
        back_populates="forecasts",
    )
