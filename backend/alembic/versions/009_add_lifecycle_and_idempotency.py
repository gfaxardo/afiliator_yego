"""009_add_lifecycle_and_idempotency

Corrige regla de pago: conversion se calcula sobre activados, pago sobre activados × tier.
Agrega campos de ciclo de vida, snapshots, idempotencia y bloqueo formal.

Revision ID: 009
Revises: 008
Create Date: 2026-05-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scout_liq_cutoff_driver_lines ──
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("activated_flag", sa.Boolean(), server_default="false"))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("is_converted_5trips_14d", sa.Boolean(), server_default="false"))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("driver_lifecycle_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("payment_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("payout_eligible_flag", sa.Boolean(), server_default="false"))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("calculated_amount", sa.Numeric(10, 2), nullable=True))

    # Unique constraint for idempotency — one line per driver per cutoff
    op.create_unique_constraint(
        "uq_cutoff_driver_line",
        "scout_liq_cutoff_driver_lines",
        ["cutoff_run_id", "scout_id", "driver_id"],
    )

    # ── scout_liq_cutoff_scout_summary ──
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("total_activated", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("total_converted_5v14d", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("conversion_rate_5v7d", sa.Numeric(5, 4), nullable=True))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("payout_per_activated", sa.Numeric(10, 2), nullable=True))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("total_payable", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    # scout_liq_cutoff_scout_summary
    op.drop_column("scout_liq_cutoff_scout_summary", "total_payable")
    op.drop_column("scout_liq_cutoff_scout_summary", "payout_per_activated")
    op.drop_column("scout_liq_cutoff_scout_summary", "conversion_rate_5v7d")
    op.drop_column("scout_liq_cutoff_scout_summary", "total_converted_5v14d")
    op.drop_column("scout_liq_cutoff_scout_summary", "total_activated")

    # scout_liq_cutoff_driver_lines
    op.drop_constraint("uq_cutoff_driver_line", "scout_liq_cutoff_driver_lines", type_="unique")
    op.drop_column("scout_liq_cutoff_driver_lines", "calculated_amount")
    op.drop_column("scout_liq_cutoff_driver_lines", "payout_eligible_flag")
    op.drop_column("scout_liq_cutoff_driver_lines", "payment_status")
    op.drop_column("scout_liq_cutoff_driver_lines", "driver_lifecycle_status")
    op.drop_column("scout_liq_cutoff_driver_lines", "is_converted_5trips_14d")
    op.drop_column("scout_liq_cutoff_driver_lines", "activated_flag")
