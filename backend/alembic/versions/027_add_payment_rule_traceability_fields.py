"""027_add_payment_rule_traceability_fields

Agrega campos de trazabilidad de reglas a cutoff_driver_lines y paid_history.
Soporta: rule_code, rule_type, origin_scope, metric_code, block_scope, support_only.

Revision ID: 027
Revises: 026
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scout_liq_cutoff_driver_lines: rule traceability ──
    for col, col_type in [
        ("rule_code", sa.String(100)),
        ("rule_type", sa.String(50)),
        ("origin_scope", sa.String(50)),
        ("metric_code", sa.String(50)),
        ("block_scope", sa.String(50)),
    ]:
        op.add_column("scout_liq_cutoff_driver_lines", sa.Column(col, col_type, nullable=True))
    
    op.add_column("scout_liq_cutoff_driver_lines", sa.Column("support_only", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # ── scout_liq_paid_history: payment rule traceability ──
    for col, col_type in [
        ("rule_code", sa.String(100)),
        ("rule_type", sa.String(50)),
        ("origin_scope", sa.String(50)),
        ("metric_code", sa.String(50)),
        ("block_scope", sa.String(50)),
        ("scheme_version_id", sa.Integer()),
    ]:
        op.add_column("scout_liq_paid_history", sa.Column(col, col_type, nullable=True))
    
    op.add_column("scout_liq_paid_history", sa.Column("support_only", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # ── scout_liq_cutoff_scout_summary: aggregate bonus meta ──
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("cohort_target_count", sa.Integer(), nullable=True))
    op.add_column("scout_liq_cutoff_scout_summary", sa.Column("rule_type", sa.String(50), nullable=True))


def downgrade() -> None:
    trace_cols = ["rule_code", "rule_type", "origin_scope", "metric_code", "block_scope"]
    for col in trace_cols:
        op.drop_column("scout_liq_cutoff_driver_lines", col)
    op.drop_column("scout_liq_cutoff_driver_lines", "support_only")
    
    for col in trace_cols + ["scheme_version_id"]:
        op.drop_column("scout_liq_paid_history", col)
    op.drop_column("scout_liq_paid_history", "support_only")
    
    op.drop_column("scout_liq_cutoff_scout_summary", "cohort_target_count")
    op.drop_column("scout_liq_cutoff_scout_summary", "rule_type")
