"""
Entry SQLAlchemy ORM model for user time-series and behavioral data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class Entry(Base):
    __tablename__ = "entries"

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
        index=True,
    )
    subcategory: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    unit: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    # Upper bound for scored entries (academic: "Maximum marks"). NULL for
    # categories where it has no meaning, and for legacy rows created before
    # this column existed (those were logged on a 0-100 scale).
    max_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )
    occurred_at: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )

    # Composite index for user-isolated queries filtered by active status and date
    __table_args__ = (
        Index("ix_entries_user_deleted_occurred", "user_id", "deleted_at", "occurred_at"),
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User",
        back_populates="entries",
    )

    @property
    def intensity(self) -> Optional[str]:
        """Expose intensity for fitness activities stored in notes."""
        if self.category == "fitness":
            return self.notes
        return None

    @intensity.setter
    def intensity(self, val: Optional[str]) -> None:
        if val is not None:
            self.notes = val.strip().lower()
