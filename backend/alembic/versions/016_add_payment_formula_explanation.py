"""016_add_payment_formula_explanation

Revision ID: 016
Revises: 015
Create Date: 2026-05-22

Agrega columna payment_formula_explanation a CutoffDriverLine
para trazabilidad humana de por que cada driver paga/no paga.
"""
from alembic import op
import sqlalchemy as sa

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'scout_liq_cutoff_driver_lines',
        sa.Column('payment_formula_explanation', sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column('scout_liq_cutoff_driver_lines', 'payment_formula_explanation')
