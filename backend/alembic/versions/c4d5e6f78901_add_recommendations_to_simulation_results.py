"""add recommendations columns to simulation_results

Revision ID: c4d5e6f78901
Revises: b3c4d5e6f789
Create Date: 2026-09-24 19:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f78901'
down_revision: Union[str, None] = 'b3c4d5e6f789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'simulation_results',
        sa.Column('recommendations', JSONB, nullable=True),
    )
    op.add_column(
        'simulation_results',
        sa.Column(
            'recommendations_status',
            sa.String(20),
            nullable=False,
            server_default='pending',
        ),
    )
    op.add_column(
        'simulation_results',
        sa.Column('recommendation_disclaimer', sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column('simulation_results', 'recommendation_disclaimer')
    op.drop_column('simulation_results', 'recommendations_status')
    op.drop_column('simulation_results', 'recommendations')
