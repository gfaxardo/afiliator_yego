"""030_add_scout_liq_job_runs

Crea tabla scout_liq_job_runs para tracking de ejecuciones de jobs/procesos.
Append-only. No destructiva.

Revision ID: 030
Revises: 029
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scout_liq_job_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.String(255), nullable=False, index=True),
        sa.Column("job_type", sa.String(50), nullable=False,
                  server_default=text("'health_diagnostic'")),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default=text("'running'")),
        sa.Column("started_at", sa.DateTime(), nullable=False,
                  server_default=text("now()")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("triggered_by", sa.String(50), nullable=False,
                  server_default=text("'system'")),
        sa.Column("steps_executed", sa.Integer(), nullable=True),
        sa.Column("steps_succeeded", sa.Integer(), nullable=True),
        sa.Column("steps_failed", sa.Integer(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False,
                  server_default=text("now()")),
    )

    op.create_index("ix_job_runs_name", "scout_liq_job_runs", ["job_name"])
    op.create_index("ix_job_runs_status", "scout_liq_job_runs", ["status"])
    op.create_index("ix_job_runs_started", "scout_liq_job_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_started", table_name="scout_liq_job_runs")
    op.drop_index("ix_job_runs_status", table_name="scout_liq_job_runs")
    op.drop_index("ix_job_runs_name", table_name="scout_liq_job_runs")
    op.drop_table("scout_liq_job_runs")
