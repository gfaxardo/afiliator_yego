"""008_nullable_scout_id

Fase 4.5 fix - Hace scout_id nullable en paid_history para permitir
registros financieros historicos sin scout resuelto.

Revision ID: 008
Revises: 007
Create Date: 2026-05-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("scout_liq_paid_history", "scout_id", nullable=True)


def downgrade() -> None:
    op.alter_column("scout_liq_paid_history", "scout_id", nullable=False)
