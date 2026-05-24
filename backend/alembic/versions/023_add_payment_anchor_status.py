"""023_add_payment_anchor_status

Agrega campos de payment anchor guardrails a scout_liq_cutoff_driver_lines.
Fase 2A.2: Cabinet sin lead_created_at oficial NO debe ser auto-payable.
"""

from alembic import op
import sqlalchemy as sa

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('payment_anchor_status', sa.String(50), nullable=True,
                  comment="official_strong|official_medium|reported_pending_validation|"
                          "fallback_operational_only|blocked_missing_official_anchor|"
                          "fleet_official_hire_date|fleet_fallback"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('reported_anchor_date', sa.Date(), nullable=True,
                  comment="Fecha ancla reportada por carga masiva/scout (NO oficial)"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('reported_anchor_source', sa.String(100), nullable=True,
                  comment="Origen de la fecha reportada: upload_csv, upload_xlsx, manual_assignment"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('reported_anchor_warning', sa.Text(), nullable=True,
                  comment="Advertencia sobre fecha reportada"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_payment_block_reason', sa.Text(), nullable=True,
                  comment="Razon por la que el anchor bloquea el pago automatico"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('is_auto_payable_anchor', sa.Boolean(), nullable=False,
                  server_default=sa.text('false'),
                  comment="TRUE si el anchor es oficial y permite pago automatico"))


def downgrade():
    op.drop_column('scout_liq_cutoff_driver_lines', 'is_auto_payable_anchor')
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_payment_block_reason')
    op.drop_column('scout_liq_cutoff_driver_lines', 'reported_anchor_warning')
    op.drop_column('scout_liq_cutoff_driver_lines', 'reported_anchor_source')
    op.drop_column('scout_liq_cutoff_driver_lines', 'reported_anchor_date')
    op.drop_column('scout_liq_cutoff_driver_lines', 'payment_anchor_status')
