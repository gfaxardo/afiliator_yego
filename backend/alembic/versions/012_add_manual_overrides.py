"""012_add_manual_overrides

Agrega tabla de overrides manuales auditables:
- assign_scout / reassign_scout / force_exclude / force_pay / send_review / resolve_review
- Cada accion queda registrada con motivo, usuario, estado.
- Los overrides aplicados afectan el canonical operation service.

Revision ID: 012
Revises: 011
Create Date: 2026-05-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scout_liq_manual_overrides",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("driver_id", sa.String(100), nullable=False),
        sa.Column("cohort_iso_week", sa.String(20), nullable=True),
        sa.Column("scout_id_before", sa.Integer(), nullable=True),
        sa.Column("scout_id_after", sa.Integer(), nullable=True),
        sa.Column("override_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(3), server_default="PEN"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("blocks_future_payment", sa.Boolean(), server_default="false"),
        sa.Column("paid_history_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_manual_overrides_driver", "scout_liq_manual_overrides", ["driver_id"])
    op.create_index("ix_manual_overrides_status", "scout_liq_manual_overrides", ["status"])
    op.create_index("ix_manual_overrides_type", "scout_liq_manual_overrides", ["override_type"])


def downgrade() -> None:
    op.drop_index("ix_manual_overrides_type", "scout_liq_manual_overrides")
    op.drop_index("ix_manual_overrides_status", "scout_liq_manual_overrides")
    op.drop_index("ix_manual_overrides_driver", "scout_liq_manual_overrides")
    op.drop_table("scout_liq_manual_overrides")
