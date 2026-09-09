"""
Alert SQLAlchemy ORM model for threshold and trend alerts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class Alert(Base):
    __tablename__ = "alerts"

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
    kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'threshold' | 'trend'
    severity: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )  # 'info' | 'warning' | 'risk'
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    __table_args__ = (
        Index("ix_alerts_user_resolved", "user_id", "resolved_at"),
        Index("ix_alerts_user_category_sub_kind", "user_id", "category", "subcategory", "kind"),
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User",
        back_populates="alerts",
    )
