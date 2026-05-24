"""022_add_acquisition_anchor_fields

Agrega campos de acquisition anchor a scout_liq_cutoff_runs y
scout_liq_cutoff_driver_lines para trazabilidad Fase 2.

- cutoff_runs: date_basis, anchor_summary
- driver_lines: acquisition_anchor_date, anchor_source, anchor_confidence,
  acquisition_type, anchor_warning, reactivation_flag,
  hire_date_reference, days_hire_vs_anchor
"""

from alembic import op
import sqlalchemy as sa

revision = '022'
down_revision = '00df6028e1f1'
branch_labels = None
depends_on = None


def upgrade():
    # ── CutoffRun ──
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('date_basis', sa.String(30), nullable=True,
                  comment="acquisition_anchor | hire_date_legacy"))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('anchor_summary', sa.Text(), nullable=True,
                  comment="JSON snapshot con KPIs de calidad de anchor"))

    # ── CutoffDriverLine ──
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('acquisition_anchor_date', sa.Date(), nullable=True,
                  comment="Fecha ancla de adquisicion resuelta"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_source', sa.String(100), nullable=True,
                  comment="Fuente del anchor: cabinet_drivers.lead_created_at, drivers.hire_date, etc."))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_confidence', sa.String(20), nullable=True,
                  comment="strong | medium | weak | none"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('acquisition_type', sa.String(50), nullable=True,
                  comment="cabinet_new_same_day, cabinet_reactivated_existing_driver, fleet_migration, etc."))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_warning', sa.Text(), nullable=True,
                  comment="Advertencia sobre la calidad del anchor"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('reactivation_flag', sa.Boolean(), nullable=False,
                  server_default=sa.text('false'),
                  comment="TRUE si hire_date < acquisition_anchor_date"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('hire_date_reference', sa.Date(), nullable=True,
                  comment="hire_date original de referencia (no usada como anchor)"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('days_hire_vs_anchor', sa.Integer(), nullable=True,
                  comment="Dias entre hire_date_reference y acquisition_anchor_date"))


def downgrade():
    op.drop_column('scout_liq_cutoff_driver_lines', 'days_hire_vs_anchor')
    op.drop_column('scout_liq_cutoff_driver_lines', 'hire_date_reference')
    op.drop_column('scout_liq_cutoff_driver_lines', 'reactivation_flag')
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_warning')
    op.drop_column('scout_liq_cutoff_driver_lines', 'acquisition_type')
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_confidence')
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_source')
    op.drop_column('scout_liq_cutoff_driver_lines', 'acquisition_anchor_date')
    op.drop_column('scout_liq_cutoff_runs', 'anchor_summary')
    op.drop_column('scout_liq_cutoff_runs', 'date_basis')
