"""002_add_assignment_fields

Fase 2 - Agrega campos status, source_hire_date_raw, source_origin, assigned_by
y crea partial unique index para evitar asignaciones activas duplicadas.

Revision ID: 002
Revises: 001
Create Date: 2026-05-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scout_liq_driver_assignments",
        sa.Column("status", sa.String(50), server_default="active", nullable=False),
    )
    op.add_column(
        "scout_liq_driver_assignments",
        sa.Column("source_hire_date_raw", sa.String(100), nullable=True),
    )
    op.add_column(
        "scout_liq_driver_assignments",
        sa.Column("source_origin", sa.String(100), nullable=True),
    )
    op.add_column(
        "scout_liq_driver_assignments",
        sa.Column("assigned_by", sa.String(100), nullable=True),
    )

    op.execute("""
        UPDATE scout_liq_driver_assignments SET status = 'active' WHERE status IS NULL
    """)

    op.create_index(
        "ix_driver_active_origin",
        "scout_liq_driver_assignments",
        ["driver_id", "source_origin"],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("ix_driver_active_origin", table_name="scout_liq_driver_assignments")
    op.drop_column("scout_liq_driver_assignments", "assigned_by")
    op.drop_column("scout_liq_driver_assignments", "source_origin")
    op.drop_column("scout_liq_driver_assignments", "source_hire_date_raw")
    op.drop_column("scout_liq_driver_assignments", "status")
