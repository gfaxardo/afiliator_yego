"""003_add_cutoff_quality_fields

Fase 3 - Agrega campos de conteo real de viajes a cutoff tables.
Prepara el sistema para liquidar basado en conteos, no booleanos.

Revision ID: 003
Revises: 002
Create Date: 2026-05-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scout_liq_cutoff_runs ──
    op.add_column("scout_liq_cutoff_runs", sa.Column("quality_data_contract_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("conversion_metric_code", sa.String(50), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("conversion_metric_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("source_mapping_snapshot", sa.Text(), nullable=True))
    op.add_column("scout_liq_cutoff_runs", sa.Column("excluded_invalid_hire_date_count", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_runs", sa.Column("excluded_missing_trip_counts_count", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_runs", sa.Column("unassigned_count", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_runs", sa.Column("total_source_drivers_count", sa.Integer(), server_default="0"))

    # ── scout_liq_cutoff_driver_lines ──
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("trips_0_7_count", sa.Integer(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("trips_8_14_count", sa.Integer(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("trips_0_14_count", sa.Integer(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("total_orders", sa.Integer(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("legacy_viajes_0_7_flag", sa.Boolean(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("legacy_viajes_8_14_flag", sa.Boolean(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("source_quality_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("source_warning", sa.Text(), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("line_status", sa.String(50), nullable=True))
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("payment_rule", sa.String(255), nullable=True))

    # ── scout_liq_cutoff_scout_summary ──
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("drivers_1plus_0_7", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("drivers_5plus_0_7", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("drivers_1plus_8_14", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("drivers_5plus_0_14", sa.Integer(), server_default="0"))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("conversion_1plus_0_7_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("conversion_5plus_0_7_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("conversion_5plus_0_14_rate", sa.Numeric(5, 4), nullable=True))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("metric_used", sa.String(100), nullable=True))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("summary_status", sa.String(50), nullable=True))


def downgrade() -> None:
    # scout_liq_cutoff_scout_summary
    op.drop_column("scout_liq_cutoff_scout_summary", "summary_status")
    op.drop_column("scout_liq_cutoff_scout_summary", "metric_used")
    op.drop_column("scout_liq_cutoff_scout_summary", "conversion_5plus_0_14_rate")
    op.drop_column("scout_liq_cutoff_scout_summary", "conversion_5plus_0_7_rate")
    op.drop_column("scout_liq_cutoff_scout_summary", "conversion_1plus_0_7_rate")
    op.drop_column("scout_liq_cutoff_scout_summary", "drivers_5plus_0_14")
    op.drop_column("scout_liq_cutoff_scout_summary", "drivers_1plus_8_14")
    op.drop_column("scout_liq_cutoff_scout_summary", "drivers_5plus_0_7")
    op.drop_column("scout_liq_cutoff_scout_summary", "drivers_1plus_0_7")

    # scout_liq_cutoff_driver_lines
    op.drop_column("scout_liq_cutoff_driver_lines", "payment_rule")
    op.drop_column("scout_liq_cutoff_driver_lines", "line_status")
    op.drop_column("scout_liq_cutoff_driver_lines", "source_warning")
    op.drop_column("scout_liq_cutoff_driver_lines", "source_quality_status")
    op.drop_column("scout_liq_cutoff_driver_lines", "legacy_viajes_8_14_flag")
    op.drop_column("scout_liq_cutoff_driver_lines", "legacy_viajes_0_7_flag")
    op.drop_column("scout_liq_cutoff_driver_lines", "total_orders")
    op.drop_column("scout_liq_cutoff_driver_lines", "trips_0_14_count")
    op.drop_column("scout_liq_cutoff_driver_lines", "trips_8_14_count")
    op.drop_column("scout_liq_cutoff_driver_lines", "trips_0_7_count")

    # scout_liq_cutoff_runs
    op.drop_column("scout_liq_cutoff_runs", "total_source_drivers_count")
    op.drop_column("scout_liq_cutoff_runs", "unassigned_count")
    op.drop_column("scout_liq_cutoff_runs", "excluded_missing_trip_counts_count")
    op.drop_column("scout_liq_cutoff_runs", "excluded_invalid_hire_date_count")
    op.drop_column("scout_liq_cutoff_runs", "source_mapping_snapshot")
    op.drop_column("scout_liq_cutoff_runs", "conversion_metric_status")
    op.drop_column("scout_liq_cutoff_runs", "conversion_metric_code")
    op.drop_column("scout_liq_cutoff_runs", "quality_data_contract_status")
