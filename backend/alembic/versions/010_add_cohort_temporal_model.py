"""010_add_cohort_temporal_model

Agrega modelo temporal de cohortes ISO a cutoff_runs:
- cohort_iso_week: semana ISO de la cohorte (ej. "2026-W18")
- cohort_from / cohort_to: lunes-domingo de la semana ISO
- maturity_days: dias para maduracion (default 7)
- maturity_completed_at: fecha en que la cohorte madura
- ready_to_liquidate: flag de madurez
- snapshot_locked_at: timestamp de congelamiento

Revision ID: 010
Revises: 009
Create Date: 2026-05-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_liq_cutoff_runs", sa.Column("cohort_iso_week", sa.String(20), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("cohort_from", sa.Date(), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("cohort_to", sa.Date(), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("maturity_days", sa.Integer(), server_default="7"))
    op.add_column("scout_liq_cutoff_runs", sa.Column("maturity_completed_at", sa.Date(), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("ready_to_liquidate", sa.Boolean(), server_default="false"))
    op.add_column("scout_liq_cutoff_runs", sa.Column("snapshot_locked_at", sa.DateTime(), nullable=True))

    # Index for fast cohort lookup
    op.create_index("ix_cutoff_runs_cohort_iso_week", "scout_liq_cutoff_runs", ["cohort_iso_week"])


def downgrade() -> None:
    op.drop_index("ix_cutoff_runs_cohort_iso_week", "scout_liq_cutoff_runs")
    op.drop_column("scout_liq_cutoff_runs", "snapshot_locked_at")
    op.drop_column("scout_liq_cutoff_runs", "ready_to_liquidate")
    op.drop_column("scout_liq_cutoff_runs", "maturity_completed_at")
    op.drop_column("scout_liq_cutoff_runs", "maturity_days")
    op.drop_column("scout_liq_cutoff_runs", "cohort_to")
    op.drop_column("scout_liq_cutoff_runs", "cohort_from")
    op.drop_column("scout_liq_cutoff_runs", "cohort_iso_week")
