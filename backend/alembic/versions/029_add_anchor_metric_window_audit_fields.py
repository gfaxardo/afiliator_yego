"""029_add_anchor_metric_window_audit_fields

Agrega campos de auditoria de fecha base a cutoff_driver_lines:
anchors_fallback_used, metric_window_start, metric_window_end, date_basis.

Revision ID: 029
Revises: 028
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("anchor_fallback_used", sa.Boolean(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("metric_window_start", sa.Date(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("metric_window_end", sa.Date(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("date_basis", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("scout_liq_cutoff_driver_lines", "date_basis")
    op.drop_column("scout_liq_cutoff_driver_lines", "metric_window_end")
    op.drop_column("scout_liq_cutoff_driver_lines", "metric_window_start")
    op.drop_column("scout_liq_cutoff_driver_lines", "anchor_fallback_used")
