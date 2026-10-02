"""
User SQLAlchemy ORM model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.entry import Entry
    from app.models.forecast import Forecast
    from app.models.goal import Goal
    from app.models.profile import Profile
    from app.models.refresh_token import RefreshToken
    from app.models.simulation import SimulationResult


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    refresh_tokens: Mapped[List[RefreshToken]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    entries: Mapped[List[Entry]] = relationship(
        "Entry",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    goals: Mapped[List[Goal]] = relationship(
        "Goal",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    forecasts: Mapped[List[Forecast]] = relationship(
        "Forecast",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[List[Alert]] = relationship(
        "Alert",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    profile: Mapped[Optional[Profile]] = relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    simulation_results: Mapped[List["SimulationResult"]] = relationship(
        "SimulationResult",
        back_populates="user",
        cascade="all, delete-orphan",
    )

