"""add_operational_source_universe_columns

Revision ID: 00df6028e1f1
Revises: 021
Create Date: 2026-05-24 11:25:34.877594
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '00df6028e1f1'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # DriverAssignment: operational source tracking
    for col, col_type in [
        ("operational_source_universe", sa.String(50)),
        ("source_confidence", sa.String(20)),
        ("payable_source_status", sa.String(50)),
        ("source_warning", sa.Text()),
        ("matched_in_drivers", sa.Boolean()),
        ("matched_in_official_source", sa.Boolean()),
        ("official_source_origin_tag", sa.String(50)),
    ]:
        op.add_column("scout_liq_driver_assignments", sa.Column(col, col_type, nullable=True))

    # CutoffDriverLine: origin_tag and financial warning persistence
    for col, col_type in [
        ("origin_tag", sa.String(50)),
        ("operational_source_universe", sa.String(50)),
        ("source_confidence", sa.String(20)),
        ("payable_source_status", sa.String(50)),
        ("official_source_origin_tag", sa.String(50)),
        ("approving_with_source_warnings", sa.Boolean()),
    ]:
        op.add_column("scout_liq_cutoff_driver_lines", sa.Column(col, col_type, nullable=True))

    # CutoffRun: approval with source warnings
    op.add_column("scout_liq_cutoff_runs", sa.Column(
        "approving_with_source_warnings", sa.Boolean(), nullable=True
    ))
    op.add_column("scout_liq_cutoff_runs", sa.Column(
        "warning_acknowledged", sa.Boolean(), nullable=True
    ))


def downgrade() -> None:
    for col in [
        "operational_source_universe", "source_confidence", "payable_source_status",
        "source_warning", "matched_in_drivers", "matched_in_official_source",
        "official_source_origin_tag",
    ]:
        op.drop_column("scout_liq_driver_assignments", col)

    for col in [
        "origin_tag", "operational_source_universe", "source_confidence",
        "payable_source_status", "official_source_origin_tag",
        "approving_with_source_warnings",
    ]:
        op.drop_column("scout_liq_cutoff_driver_lines", col)

    for col in ["approving_with_source_warnings", "warning_acknowledged"]:
        op.drop_column("scout_liq_cutoff_runs", col)
