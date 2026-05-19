"""006_dual_layer_attribution_payment

Fase 4.5 fix - Agrega campos dual-layer a historical_import_lines
para separar atribucion y pago en el historico.

Revision ID: 006
Revises: 005
Create Date: 2026-05-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_liq_historical_import_lines", sa.Column("attribution_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("attribution_reason", sa.Text(), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("payment_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("payment_reason", sa.Text(), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("final_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("attribution_id", sa.Integer(), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("assignment_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scout_liq_historical_import_lines", "assignment_id")
    op.drop_column("scout_liq_historical_import_lines", "attribution_id")
    op.drop_column("scout_liq_historical_import_lines", "final_status")
    op.drop_column("scout_liq_historical_import_lines", "payment_reason")
    op.drop_column("scout_liq_historical_import_lines", "payment_status")
    op.drop_column("scout_liq_historical_import_lines", "attribution_reason")
    op.drop_column("scout_liq_historical_import_lines", "attribution_status")
