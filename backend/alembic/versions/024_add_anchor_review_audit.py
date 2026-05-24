"""024_add_anchor_review_audit

Crea tabla scout_liq_anchor_review_audit para trazabilidad
del workflow de revision manual de acquisition anchors.
Fase 2B — Anchor Review & Resolution Workflow.
"""

from alembic import op
import sqlalchemy as sa

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scout_liq_anchor_review_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('line_id', sa.Integer(), nullable=False,
                  comment="FK a scout_liq_cutoff_driver_lines.id"),
        sa.Column('action', sa.String(50), nullable=False,
                  comment="approve | reject | needs_supervisor | ignore | resolved_by_refresh"),
        sa.Column('actor', sa.String(100), nullable=True,
                  comment="Quien ejecuto la accion"),
        sa.Column('reason', sa.Text(), nullable=True,
                  comment="Justificacion de la decision"),
        sa.Column('notes', sa.Text(), nullable=True,
                  comment="Notas adicionales del reviewer"),
        sa.Column('reviewed_anchor_date', sa.Date(), nullable=True,
                  comment="Fecha ancla aprobada manualmente si se proporciono"),
        sa.Column('before_state', sa.Text(), nullable=True,
                  comment="JSON con el estado anterior de los campos anchor"),
        sa.Column('after_state', sa.Text(), nullable=True,
                  comment="JSON con el estado posterior de los campos anchor"),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ar_audit_line_id', 'scout_liq_anchor_review_audit', ['line_id'])
    op.create_index('ix_ar_audit_action', 'scout_liq_anchor_review_audit', ['action'])
    op.create_index('ix_ar_audit_created_at', 'scout_liq_anchor_review_audit', ['created_at'])

    # Add anchor_review_status to cutoff_driver_lines
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_review_status', sa.String(50), nullable=True,
                  server_default=sa.text("'pending_review'"),
                  comment="pending_review|approved_manual_override|rejected_manual_override|"
                          "requires_supervisor_review|resolved_by_official_refresh|ignored_low_priority"))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_reviewed_by', sa.String(100), nullable=True))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_reviewed_at', sa.DateTime(), nullable=True))
    op.add_column('scout_liq_cutoff_driver_lines',
        sa.Column('anchor_review_reason', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_review_reason')
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_reviewed_at')
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_reviewed_by')
    op.drop_column('scout_liq_cutoff_driver_lines', 'anchor_review_status')
    op.drop_index('ix_ar_audit_created_at', 'scout_liq_anchor_review_audit')
    op.drop_index('ix_ar_audit_action', 'scout_liq_anchor_review_audit')
    op.drop_index('ix_ar_audit_line_id', 'scout_liq_anchor_review_audit')
    op.drop_table('scout_liq_anchor_review_audit')
