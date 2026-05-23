"""020_add_reconciliation_audit

Crear tabla scout_liq_reconciliation_audit para el trail de auditoria
de reconciliacion (approve/reject/merge entre observed y official).
Crear vista materializada scout_liq_attribution_reconciliation.
Agregar indice para aging queries en observed_affiliations.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scout_liq_reconciliation_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('driver_id', sa.String(100), nullable=False),
        sa.Column('observed_affiliation_id', sa.Integer(), nullable=True),
        sa.Column('observed_review_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('before_state', JSONB(), nullable=True),
        sa.Column('after_state', JSONB(), nullable=True),
        sa.Column('actor', sa.String(100), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('reconciliation_status', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_rec_audit_driver', 'scout_liq_reconciliation_audit', ['driver_id'])
    op.create_index('ix_rec_audit_observed_id', 'scout_liq_reconciliation_audit', ['observed_affiliation_id'])
    op.create_index('ix_rec_audit_action', 'scout_liq_reconciliation_audit', ['action'])
    op.create_index('ix_rec_audit_created', 'scout_liq_reconciliation_audit', ['created_at'])

    op.create_index('ix_oa_aging', 'scout_liq_observed_affiliations', ['review_status', 'created_at'])

    sql = sa.text("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS scout_liq_attribution_reconciliation AS
        SELECT
            o.id AS observed_id,
            o.matched_driver_id AS driver_id,
            o.reported_driver_name,
            o.reported_scout_name,
            o.reported_supervisor_name,
            o.reported_origin,
            o.reported_license,
            o.reported_phone,
            o.match_status,
            o.match_confidence,
            o.official_source_status,
            o.review_status,
            o.review_notes,
            o.reported_affiliation_date,
            o.created_at AS observed_created_at,
            o.updated_at AS observed_updated_at,
            CASE
                WHEN o.match_status = 'manual_review' THEN 'conflicting_scouts'
                WHEN o.matched_driver_id IS NULL THEN 'orphan_driver'
                WHEN o.official_source_status = 'official_found'
                     AND o.match_status = 'matched' THEN 'both_matched'
                WHEN o.official_source_status = 'official_missing'
                     AND o.match_status = 'matched' THEN 'observed_only'
                WHEN o.official_source_status = 'official_found'
                     AND o.match_status = 'unmatched' THEN 'official_only'
                ELSE 'operational_without_attribution'
            END AS reconciliation_class,
            CASE
                WHEN o.match_confidence = 'high'
                     AND o.official_source_status = 'official_found' THEN 'HIGH'
                WHEN o.match_confidence = 'high'
                     AND o.official_source_status = 'official_missing' THEN 'MEDIUM'
                WHEN o.match_confidence = 'medium' THEN 'MEDIUM'
                WHEN o.match_status = 'manual_review' THEN 'LOW'
                WHEN o.match_status = 'unmatched' THEN 'BLOCKED'
                WHEN o.match_confidence IS NULL THEN 'LOW'
                ELSE 'LOW'
            END AS confidence_level,
            CASE
                WHEN o.created_at >= NOW() - INTERVAL '24 hours' THEN 'pending_24h'
                WHEN o.created_at >= NOW() - INTERVAL '3 days' THEN 'pending_1_3d'
                ELSE 'pending_gt_3d'
            END AS aging_bucket,
            EXISTS (
                SELECT 1 FROM scout_liq_driver_assignments a
                WHERE a.driver_id = o.matched_driver_id
                  AND a.status = 'active'
            ) AS has_active_assignment,
            EXISTS (
                SELECT 1 FROM scout_liq_paid_history ph
                WHERE ph.driver_id = o.matched_driver_id
                  AND ph.blocks_future_payment = true
            ) AS has_paid_blocking,
            EXISTS (
                SELECT 1 FROM scout_liq_cutoff_driver_lines cdl
                WHERE cdl.observed_affiliation_id = o.id
            ) AS has_cutoff_line,
            EXISTS (
                SELECT 1 FROM module_ct_cabinet_drivers m
                WHERE m.driver_id = o.matched_driver_id
            ) AS in_official_source_now
        FROM scout_liq_observed_affiliations o
        WHERE o.review_status IN (
            'observed_pending_review',
            'observed_validated',
            'observed_error'
        )
    """)
    op.execute(sql)

    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_rec_view_observed_id "
        "ON scout_liq_attribution_reconciliation (observed_id)"
    ))


def downgrade():
    op.execute(sa.text(
        "DROP MATERIALIZED VIEW IF EXISTS scout_liq_attribution_reconciliation"
    ))
    op.drop_index('ix_oa_aging', table_name='scout_liq_observed_affiliations')
    op.drop_table('scout_liq_reconciliation_audit')
