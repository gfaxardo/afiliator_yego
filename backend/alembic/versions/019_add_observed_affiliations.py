"""019_add_observed_affiliations

Crear tabla scout_liq_observed_affiliations para el flujo de
Atribuciones Observadas: conductores reportados por scouts/supervisores
que no aparecen en module_ct_cabinet_drivers pero si en drivers.

Agregar campos de trazabilidad en CutoffDriverLine:
- attribution_source
- observed_affiliation_id
- line_observation_status
- line_explanation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scout_liq_observed_affiliations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('source_file_id', sa.Integer(), nullable=True),
        sa.Column('row_number', sa.Integer(), nullable=True),
        sa.Column('reported_affiliation_date', sa.Date(), nullable=False),
        sa.Column('reported_origin', sa.String(100), nullable=True),
        sa.Column('reported_scout_name', sa.String(255), nullable=True),
        sa.Column('reported_supervisor_name', sa.String(255), nullable=True),
        sa.Column('reported_driver_name', sa.String(255), nullable=True),
        sa.Column('reported_license', sa.String(100), nullable=True),
        sa.Column('reported_phone', sa.String(50), nullable=True),
        sa.Column('normalized_license', sa.String(100), nullable=True),
        sa.Column('normalized_phone', sa.String(50), nullable=True),
        sa.Column('matched_driver_id', sa.String(100), nullable=True),
        sa.Column('match_status', sa.String(50), nullable=True, server_default='pending'),
        sa.Column('match_confidence', sa.String(20), nullable=True),
        sa.Column('match_reason', sa.Text(), nullable=True),
        sa.Column('official_source_status', sa.String(50), nullable=True),
        sa.Column('review_status', sa.String(50), nullable=False, server_default='observed_pending_review'),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('raw_payload', JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_oa_normalized_license', 'scout_liq_observed_affiliations', ['normalized_license'])
    op.create_index('ix_oa_normalized_phone', 'scout_liq_observed_affiliations', ['normalized_phone'])
    op.create_index('ix_oa_matched_driver_id', 'scout_liq_observed_affiliations', ['matched_driver_id'])
    op.create_index('ix_oa_reported_affiliation_date', 'scout_liq_observed_affiliations', ['reported_affiliation_date'])
    op.create_index('ix_oa_review_status', 'scout_liq_observed_affiliations', ['review_status'])

    op.add_column(
        'scout_liq_cutoff_driver_lines',
        sa.Column('attribution_source', sa.String(50), nullable=False, server_default='official'),
    )
    op.add_column(
        'scout_liq_cutoff_driver_lines',
        sa.Column('observed_affiliation_id', sa.Integer(), nullable=True),
    )
    op.add_column(
        'scout_liq_cutoff_driver_lines',
        sa.Column('line_observation_status', sa.String(50), nullable=True),
    )
    op.add_column(
        'scout_liq_cutoff_driver_lines',
        sa.Column('line_explanation', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column('scout_liq_cutoff_driver_lines', 'line_explanation')
    op.drop_column('scout_liq_cutoff_driver_lines', 'line_observation_status')
    op.drop_column('scout_liq_cutoff_driver_lines', 'observed_affiliation_id')
    op.drop_column('scout_liq_cutoff_driver_lines', 'attribution_source')

    op.drop_table('scout_liq_observed_affiliations')
