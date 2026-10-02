"""
SimulationResult SQLAlchemy ORM model for cached scenario simulation outputs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class SimulationResult(Base):
    __tablename__ = "simulation_results"

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
    scenario_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    params_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    input_params: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    result_data: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    data_point_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    reliability: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ── Chunk 11: AI Recommendations ──────────────────────────────
    recommendations: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True,
    )
    recommendations_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    recommendation_disclaimer: Mapped[Optional[str]] = mapped_column(
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
            "scenario_type",
            "params_hash",
            name="uq_simulation_results_user_scenario_hash",
        ),
    )

    # Relationships
    user: Mapped[User] = relationship(
        "User",
        back_populates="simulation_results",
    )
