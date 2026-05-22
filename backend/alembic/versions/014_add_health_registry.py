"""014_add_health_registry

Crea tablas para auto health monitoring:
- scout_liq_refresh_registry: registro de fuentes/procesos con frecuencia, lag, estado
- scout_liq_health_events: eventos de salud detectados (alertas operativas)

Append-only. No destructiva.

Revision ID: 014
Revises: 013
Create Date: 2026-05-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Refresh Registry ──
    op.create_table(
        "scout_liq_refresh_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(255), nullable=False, unique=True),
        sa.Column("source_type", sa.String(50), nullable=False, server_default=text("'table'")),
        sa.Column("last_seen_data_at", sa.DateTime(), nullable=True),
        sa.Column("last_refresh_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(), nullable=True),
        sa.Column("expected_frequency_minutes", sa.Integer(), nullable=False, server_default=text("1440")),
        sa.Column("lag_minutes", sa.Integer(), nullable=True),
        sa.Column("rows_observed", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=text("'unknown'")),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=text("now()")),
    )

    op.create_index("ix_refresh_registry_source", "scout_liq_refresh_registry", ["source_name"])
    op.create_index("ix_refresh_registry_status", "scout_liq_refresh_registry", ["status"])

    # ── 2. Health Events ──
    op.create_table(
        "scout_liq_health_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default=text("'warning'")),
        sa.Column("source_name", sa.String(255), nullable=True),
        sa.Column("cohort_key", sa.String(20), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=text("'open'")),
        sa.Column("detected_at", sa.DateTime(), nullable=False, server_default=text("now()")),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )

    op.create_index("ix_health_events_source", "scout_liq_health_events", ["source_name"])
    op.create_index("ix_health_events_severity", "scout_liq_health_events", ["severity"])
    op.create_index("ix_health_events_status", "scout_liq_health_events", ["status"])
    op.create_index("ix_health_events_detected", "scout_liq_health_events", ["detected_at"])
    op.create_index("ix_health_events_cohort", "scout_liq_health_events", ["cohort_key"])
    op.create_index("ix_health_events_dedup", "scout_liq_health_events",
                    ["event_type", "source_name", "cohort_key"],
                    postgresql_where=text("status = 'open'"),
                    unique=True)


def downgrade() -> None:
    op.drop_index("ix_health_events_dedup", table_name="scout_liq_health_events")
    op.drop_index("ix_health_events_cohort", table_name="scout_liq_health_events")
    op.drop_index("ix_health_events_detected", table_name="scout_liq_health_events")
    op.drop_index("ix_health_events_status", table_name="scout_liq_health_events")
    op.drop_index("ix_health_events_severity", table_name="scout_liq_health_events")
    op.drop_index("ix_health_events_source", table_name="scout_liq_health_events")
    op.drop_table("scout_liq_health_events")
    op.drop_index("ix_refresh_registry_status", table_name="scout_liq_refresh_registry")
    op.drop_index("ix_refresh_registry_source", table_name="scout_liq_refresh_registry")
    op.drop_table("scout_liq_refresh_registry")
