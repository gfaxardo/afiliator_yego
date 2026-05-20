"""013_add_semantic_scheme_fields

Agrega campos semanticos multi-esquema a PaymentSchemeVersion:
- volume_rule: regla de volumen minimo (ej. 1V7D, 50V30D)
- min_volume_count: minimo de drivers con volumen
- pays_on_rule: base de pago (ACTIVATED_BASE, QUALITY_HIT, FIXED)
- payout_formula_type: formula de calculo (ACTIVATED_X_TIER, QUALITY_X_FIXED)
- counts_volume_rule: que hito define volumen
- counts_quality_rule: que hito define calidad
- maturity_window_days: ventana de maduracion

Revision ID: 013
Revises: 012
Create Date: 2026-05-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_liq_payment_scheme_versions",
        sa.Column("volume_rule", sa.String(50), nullable=True))
    op.add_column("scout_liq_payment_scheme_versions",
        sa.Column("min_volume_count", sa.Integer(), nullable=True))
    op.add_column("scout_liq_payment_scheme_versions",
        sa.Column("pays_on_rule", sa.String(50), nullable=True))
    op.add_column("scout_liq_payment_scheme_versions",
        sa.Column("payout_formula_type", sa.String(50), nullable=True))
    op.add_column("scout_liq_payment_scheme_versions",
        sa.Column("counts_volume_rule", sa.String(50), nullable=True))
    op.add_column("scout_liq_payment_scheme_versions",
        sa.Column("counts_quality_rule", sa.String(50), nullable=True))
    op.add_column("scout_liq_payment_scheme_versions",
        sa.Column("maturity_window_days", sa.Integer(), nullable=True))

    # Backfill: populate new fields from old fields for existing active/draft versions
    op.execute("""
        UPDATE scout_liq_payment_scheme_versions SET
            volume_rule = activation_rule,
            min_volume_count = min_activated,
            counts_volume_rule = activation_rule,
            counts_quality_rule = quality_rule,
            maturity_window_days = maturity_days,
            pays_on_rule = CASE
                WHEN formula_type = 'ACTIVATED_X_TIER' THEN 'ACTIVATED_BASE'
                WHEN formula_type = 'QUALITY_X_FIXED' THEN 'QUALITY_HIT'
                ELSE formula_type
            END,
            payout_formula_type = formula_type
        WHERE volume_rule IS NULL
    """)


def downgrade() -> None:
    op.drop_column("scout_liq_payment_scheme_versions", "maturity_window_days")
    op.drop_column("scout_liq_payment_scheme_versions", "counts_quality_rule")
    op.drop_column("scout_liq_payment_scheme_versions", "counts_volume_rule")
    op.drop_column("scout_liq_payment_scheme_versions", "payout_formula_type")
    op.drop_column("scout_liq_payment_scheme_versions", "pays_on_rule")
    op.drop_column("scout_liq_payment_scheme_versions", "min_volume_count")
    op.drop_column("scout_liq_payment_scheme_versions", "volume_rule")
