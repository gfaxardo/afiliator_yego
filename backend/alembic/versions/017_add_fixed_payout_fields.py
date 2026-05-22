"""017_add_fixed_payout_fields

Revision ID: 017
Revises: 016
Create Date: 2026-05-22

Agrega campos para soporte de pago fijo por driver (FIXED_PER_DRIVER).
- fixed_payout_amount: monto fijo por driver que cumple la regla
- minimum_enabled: controla si el minimo de activados aplica
"""
from alembic import op
import sqlalchemy as sa

revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'scout_liq_payment_scheme_versions',
        sa.Column('fixed_payout_amount', sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        'scout_liq_payment_scheme_versions',
        sa.Column('minimum_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )


def downgrade():
    op.drop_column('scout_liq_payment_scheme_versions', 'minimum_enabled')
    op.drop_column('scout_liq_payment_scheme_versions', 'fixed_payout_amount')
