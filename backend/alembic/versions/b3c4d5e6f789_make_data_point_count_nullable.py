"""make data_point_count nullable for assumption-based scenarios

Revision ID: b3c4d5e6f789
Revises: 95325bf822ee
Create Date: 2026-09-24 02:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f789'
down_revision: Union[str, None] = '95325bf822ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'simulation_results',
        'data_point_count',
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Set any NULL values to 0 before making non-nullable again
    op.execute("UPDATE simulation_results SET data_point_count = 0 WHERE data_point_count IS NULL")
    op.alter_column(
        'simulation_results',
        'data_point_count',
        existing_type=sa.Integer(),
        nullable=False,
    )
