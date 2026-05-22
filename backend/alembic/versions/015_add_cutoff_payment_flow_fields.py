"""015_add_cutoff_payment_flow_fields

Agrega campos para flujo completo de pagos:
- notes: notas del corte (Text)
- cancelled_at: timestamp de cancelacion (DateTime)
- cancelled_reason: motivo de cancelacion (Text)

Append-only. No destructiva.

Revision ID: 015
Revises: 014
Create Date: 2026-05-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_liq_cutoff_runs",
                  sa.Column("notes", sa.Text(), nullable=True))
    op.add_column("scout_liq_cutoff_runs",
                  sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.add_column("scout_liq_cutoff_runs",
                  sa.Column("cancelled_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scout_liq_cutoff_runs", "cancelled_reason")
    op.drop_column("scout_liq_cutoff_runs", "cancelled_at")
    op.drop_column("scout_liq_cutoff_runs", "notes")
