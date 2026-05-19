"""007_financial_vs_blocking_payments

Fase 4.7 fix - Separa pago financiero historico de bloqueo futuro.
Agrega campos a paid_history y historical_import_lines.

Revision ID: 007
Revises: 006
Create Date: 2026-05-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scout_liq_paid_history ──
    op.add_column("scout_liq_paid_history", sa.Column("resolution_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("blocks_future_payment", sa.Boolean(), server_default="true"))
    op.add_column("scout_liq_paid_history", sa.Column("financial_record_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("original_payment_status_raw", sa.String(100), nullable=True))

    # Set blocks_future_payment=false for existing records without driver_id
    op.execute("""
        UPDATE scout_liq_paid_history
        SET blocks_future_payment = false,
            resolution_status = 'unresolved_driver'
        WHERE driver_id IS NULL
    """)
    # Set blocks_future_payment=true for records with driver_id
    op.execute("""
        UPDATE scout_liq_paid_history
        SET blocks_future_payment = true,
            resolution_status = 'resolved'
        WHERE driver_id IS NOT NULL AND blocks_future_payment IS NULL
    """)

    # ── scout_liq_historical_import_lines ──
    op.add_column("scout_liq_historical_import_lines", sa.Column("payment_financial_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("payment_financial_reason", sa.Text(), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("payment_blocking_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("payment_blocking_reason", sa.Text(), nullable=True))
    op.add_column("scout_liq_historical_import_lines", sa.Column("blocks_future_payment", sa.Boolean(), nullable=True))

    # Indices
    op.create_index("ix_ph_blocks", "scout_liq_paid_history", ["blocks_future_payment"])
    op.create_index("ix_ph_resolution", "scout_liq_paid_history", ["resolution_status"])


def downgrade() -> None:
    op.drop_index("ix_ph_resolution", table_name="scout_liq_paid_history")
    op.drop_index("ix_ph_blocks", table_name="scout_liq_paid_history")

    op.drop_column("scout_liq_historical_import_lines", "blocks_future_payment")
    op.drop_column("scout_liq_historical_import_lines", "payment_blocking_reason")
    op.drop_column("scout_liq_historical_import_lines", "payment_blocking_status")
    op.drop_column("scout_liq_historical_import_lines", "payment_financial_reason")
    op.drop_column("scout_liq_historical_import_lines", "payment_financial_status")

    op.drop_column("scout_liq_paid_history", "original_payment_status_raw")
    op.drop_column("scout_liq_paid_history", "financial_record_status")
    op.drop_column("scout_liq_paid_history", "blocks_future_payment")
    op.drop_column("scout_liq_paid_history", "resolution_status")
