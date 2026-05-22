"""018_add_cutoff_mode

Revision ID: 018
Revises: 017
Create Date: 2026-05-22

Agrega cutoff_mode a CutoffRun para diferenciar:
- COHORT: corte tradicional por cohorte semanal
- PAYABLE_SWEEP: barrido pagable (todos los drivers activos, sin filtro hire_date)
"""
from alembic import op
import sqlalchemy as sa

revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'scout_liq_cutoff_runs',
        sa.Column('cutoff_mode', sa.String(20), nullable=False, server_default=sa.text("'COHORT'"))
    )


def downgrade():
    op.drop_column('scout_liq_cutoff_runs', 'cutoff_mode')
