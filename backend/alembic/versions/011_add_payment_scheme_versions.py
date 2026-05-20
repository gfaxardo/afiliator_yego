"""011_add_payment_scheme_versions

Agrega modelo DB versionado para esquemas de pago:
- scout_liq_payment_schemes: esquemas base (cabinet, fleet, custom)
- scout_liq_payment_scheme_versions: versiones con vigencia por cohorte ISO
- scout_liq_payment_scheme_tiers: tramos configurables por version

Sin alterar tablas existentes.
Sin tocar datos historicos.

Revision ID: 011
Revises: 010
Create Date: 2026-05-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scout_liq_payment_schemes ──
    op.create_table(
        "scout_liq_payment_schemes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scheme_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── scout_liq_payment_scheme_versions ──
    op.create_table(
        "scout_liq_payment_scheme_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_id", sa.Integer(), sa.ForeignKey("scout_liq_payment_schemes.id"), nullable=False),
        sa.Column("version_name", sa.String(100), nullable=False),
        sa.Column("valid_from_cohort_iso_week", sa.String(20), nullable=False),
        sa.Column("valid_to_cohort_iso_week", sa.String(20), nullable=True),
        sa.Column("maturity_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("min_activated", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("activation_rule", sa.String(50), nullable=False, server_default="1V7D"),
        sa.Column("quality_rule", sa.String(50), nullable=False, server_default="5V7D"),
        sa.Column("formula_type", sa.String(50), nullable=False, server_default="ACTIVATED_X_TIER"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="PEN"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scheme_id", "valid_from_cohort_iso_week", name="uq_scheme_version_valid_from"),
    )

    # ── scout_liq_payment_scheme_tiers ──
    op.create_table(
        "scout_liq_payment_scheme_tiers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_version_id", sa.Integer(), sa.ForeignKey("scout_liq_payment_scheme_versions.id"), nullable=False),
        sa.Column("min_conversion_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("payout_amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scout_liq_payment_scheme_tiers")
    op.drop_table("scout_liq_payment_scheme_versions")
    op.drop_table("scout_liq_payment_schemes")
