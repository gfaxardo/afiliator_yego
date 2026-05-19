"""005_historical_attributions

Fase 4.6 - Tabla de atribuciones historicas scout->conductor
y extension de driver_assignments con trazabilidad de importacion.

Revision ID: 005
Revises: 004
Create Date: 2026-05-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scout_liq_historical_attributions ──
    op.create_table(
        "scout_liq_historical_attributions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=True),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column("source_sheet", sa.String(100), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("cutoff_external_id", sa.String(100), nullable=True),
        sa.Column("scout_id_resolved", sa.Integer(), nullable=True),
        sa.Column("scout_name_raw", sa.String(255), nullable=True),
        sa.Column("supervisor_id_resolved", sa.Integer(), nullable=True),
        sa.Column("supervisor_name_raw", sa.String(255), nullable=True),
        sa.Column("scout_type_raw", sa.String(50), nullable=True),
        sa.Column("origin_raw", sa.String(100), nullable=True),
        sa.Column("driver_license_raw", sa.String(100), nullable=True),
        sa.Column("driver_id_resolved", sa.String(100), nullable=True),
        sa.Column("driver_name_raw", sa.String(255), nullable=True),
        sa.Column("driver_phone_raw", sa.String(50), nullable=True),
        sa.Column("hire_date_raw", sa.String(100), nullable=True),
        sa.Column("hire_date_resolved", sa.Date(), nullable=True),
        sa.Column("assignment_date_raw", sa.String(100), nullable=True),
        sa.Column("assignment_status", sa.String(50), nullable=True),
        sa.Column("payment_status_raw", sa.String(100), nullable=True),
        sa.Column("payment_amount_raw", sa.String(100), nullable=True),
        sa.Column("payment_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("payment_rule_raw", sa.String(255), nullable=True),
        sa.Column("operational_flags_json", sa.Text(), nullable=True),
        sa.Column("import_status", sa.String(50), server_default="pending"),
        sa.Column("import_reason", sa.Text(), nullable=True),
        sa.Column("linked_assignment_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Extender scout_liq_driver_assignments ──
    op.add_column("scout_liq_driver_assignments", sa.Column("source_file", sa.String(255), nullable=True))
    op.add_column("scout_liq_driver_assignments", sa.Column("source_sheet", sa.String(100), nullable=True))
    op.add_column("scout_liq_driver_assignments", sa.Column("source_row", sa.Integer(), nullable=True))
    op.add_column("scout_liq_driver_assignments", sa.Column("import_batch_id", sa.Integer(), nullable=True))
    op.add_column("scout_liq_driver_assignments", sa.Column("license_raw", sa.String(100), nullable=True))

    # ── Indices ──
    op.create_index("ix_attr_batch", "scout_liq_historical_attributions", ["import_batch_id"])
    op.create_index("ix_attr_scout", "scout_liq_historical_attributions", ["scout_id_resolved"])
    op.create_index("ix_attr_driver", "scout_liq_historical_attributions", ["driver_id_resolved"])
    op.create_index("ix_attr_license", "scout_liq_historical_attributions", ["driver_license_raw"])
    op.create_index("ix_attr_status", "scout_liq_historical_attributions", ["import_status"])
    op.create_index("ix_assign_source_file", "scout_liq_driver_assignments", ["source_file"])
    op.create_index("ix_assign_license", "scout_liq_driver_assignments", ["license_raw"])


def downgrade() -> None:
    op.drop_index("ix_assign_license", table_name="scout_liq_driver_assignments")
    op.drop_index("ix_assign_source_file", table_name="scout_liq_driver_assignments")
    op.drop_index("ix_attr_status", table_name="scout_liq_historical_attributions")
    op.drop_index("ix_attr_license", table_name="scout_liq_historical_attributions")
    op.drop_index("ix_attr_driver", table_name="scout_liq_historical_attributions")
    op.drop_index("ix_attr_scout", table_name="scout_liq_historical_attributions")
    op.drop_index("ix_attr_batch", table_name="scout_liq_historical_attributions")

    op.drop_column("scout_liq_driver_assignments", "license_raw")
    op.drop_column("scout_liq_driver_assignments", "import_batch_id")
    op.drop_column("scout_liq_driver_assignments", "source_row")
    op.drop_column("scout_liq_driver_assignments", "source_sheet")
    op.drop_column("scout_liq_driver_assignments", "source_file")

    op.drop_table("scout_liq_historical_attributions")
