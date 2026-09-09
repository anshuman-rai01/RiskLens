"""
SQLAlchemy model registry.

Every model module must be imported here so that Alembic's autogenerate
can discover all tables via ``Base.metadata``.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# ── Import every model module so metadata is populated ───────────
from app.models.user import User  # noqa: E402, F401
from app.models.refresh_token import RefreshToken  # noqa: E402, F401
from app.models.entry import Entry  # noqa: E402, F401
from app.models.goal import Goal  # noqa: E402, F401
from app.models.forecast import Forecast  # noqa: E402, F401
from app.models.alert import Alert  # noqa: E402, F401
from app.models.profile import Profile  # noqa: E402, F401


