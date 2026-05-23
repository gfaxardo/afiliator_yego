"""021_add_reconciliation_refresh_log

Crear tabla scout_liq_reconciliation_refresh_log para trackear
el historial de refresh de la vista materializada de reconciliacion.
"""

from alembic import op
import sqlalchemy as sa

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scout_liq_reconciliation_refresh_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('last_refreshed_at', sa.DateTime(), nullable=True),
        sa.Column('refresh_duration_ms', sa.Integer(), nullable=True),
        sa.Column('refresh_status', sa.String(20), nullable=False, server_default='in_progress'),
        sa.Column('refresh_error', sa.Text(), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('scout_liq_reconciliation_refresh_log')
