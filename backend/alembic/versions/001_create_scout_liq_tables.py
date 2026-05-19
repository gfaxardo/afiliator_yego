"""001_create_scout_liq_tables

Fase 1 - Creación de las 8 tablas base del liquidador de scouts.
No modifica ninguna tabla existente.

Revision ID: 001
Revises: None
Create Date: 2026-05-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scout_liq_scouts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scout_name", sa.String(255), nullable=False),
        sa.Column("document_number", sa.String(50), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("scout_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scout_liq_conversion_schemes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_name", sa.String(255), nullable=False),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("scout_type", sa.String(50), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("min_affiliations", sa.Integer(), server_default="0"),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scout_liq_cutoff_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cutoff_name", sa.String(255), nullable=False),
        sa.Column("hire_date_from", sa.Date(), nullable=True),
        sa.Column("hire_date_to", sa.Date(), nullable=True),
        sa.Column("origin_filter", sa.String(100), nullable=True),
        sa.Column("country_filter", sa.String(100), nullable=True),
        sa.Column("city_filter", sa.String(100), nullable=True),
        sa.Column("scout_type_filter", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("config_snapshot", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scout_liq_driver_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("driver_id", sa.String(100), nullable=False),
        sa.Column("scout_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["scout_id"], ["scout_liq_scouts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("driver_id", "scout_id", name="uq_driver_scout_active"),
    )

    op.create_table(
        "scout_liq_conversion_tiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("min_conversion_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("payment_per_converted_driver", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="PEN"),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["scheme_id"], ["scout_liq_conversion_schemes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scout_liq_cutoff_scout_summary",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cutoff_run_id", sa.Integer(), nullable=False),
        sa.Column("scout_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("total_affiliations", sa.Integer(), server_default="0"),
        sa.Column("converted_5trips_7d", sa.Integer(), server_default="0"),
        sa.Column("not_converted", sa.Integer(), server_default="0"),
        sa.Column("conversion_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tier_reached", sa.Numeric(5, 4), nullable=True),
        sa.Column("payment_per_converted_driver", sa.Numeric(10, 2), nullable=True),
        sa.Column("amount_calculated", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount_approved", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cutoff_run_id"], ["scout_liq_cutoff_runs.id"]),
        sa.ForeignKeyConstraint(["scout_id"], ["scout_liq_scouts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cutoff_run_id", "scout_id", name="uq_cutoff_scout"),
    )

    op.create_table(
        "scout_liq_cutoff_driver_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cutoff_run_id", sa.Integer(), nullable=False),
        sa.Column("scout_id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.String(100), nullable=False),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("trips_7d", sa.Integer(), server_default="0"),
        sa.Column("trips_14d", sa.Integer(), server_default="0"),
        sa.Column("is_converted_5trips_7d", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("eligible", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("already_paid", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cutoff_run_id"], ["scout_liq_cutoff_runs.id"]),
        sa.ForeignKeyConstraint(["scout_id"], ["scout_liq_scouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scout_liq_paid_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cutoff_run_id", sa.Integer(), nullable=False),
        sa.Column("scout_id", sa.Integer(), nullable=False),
        sa.Column("driver_id", sa.String(100), nullable=True),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("payment_rule", sa.String(255), nullable=True),
        sa.Column("amount_paid", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(3), server_default="PEN"),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("payment_reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cutoff_run_id"], ["scout_liq_cutoff_runs.id"]),
        sa.ForeignKeyConstraint(["scout_id"], ["scout_liq_scouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scout_liq_paid_history")
    op.drop_table("scout_liq_cutoff_driver_lines")
    op.drop_table("scout_liq_cutoff_scout_summary")
    op.drop_table("scout_liq_conversion_tiers")
    op.drop_table("scout_liq_driver_assignments")
    op.drop_table("scout_liq_cutoff_runs")
    op.drop_table("scout_liq_conversion_schemes")
    op.drop_table("scout_liq_scouts")
