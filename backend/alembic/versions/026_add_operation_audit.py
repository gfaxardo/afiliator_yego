"""026_add_operation_audit

Crea tabla scout_liq_operation_audit para trazabilidad
de acciones operacionales sobre lineas de cutoff.

Fase 3 — Operational Action Layer.
"""

from alembic import op
import sqlalchemy as sa

revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scout_liq_operation_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('line_id', sa.Integer(), nullable=False,
                  comment="FK a scout_liq_cutoff_driver_lines.id"),
        sa.Column('cutoff_run_id', sa.Integer(), nullable=True,
                  comment="FK a scout_liq_cutoff_runs.id"),
        sa.Column('driver_id', sa.String(100), nullable=True,
                  comment="Driver ID para busqueda rapida"),
        sa.Column('action', sa.String(50), nullable=False,
                  comment="approve | block | manual_review | mark_paid | unblock"),
        sa.Column('actor', sa.String(100), nullable=True,
                  comment="Quien ejecuto la accion"),
        sa.Column('reason', sa.Text(), nullable=True,
                  comment="Motivo operacional"),
        sa.Column('notes', sa.Text(), nullable=True,
                  comment="Comentario del operador"),
        sa.Column('previous_line_status', sa.String(50), nullable=True),
        sa.Column('previous_payment_status', sa.String(50), nullable=True),
        sa.Column('new_line_status', sa.String(50), nullable=True),
        sa.Column('new_payment_status', sa.String(50), nullable=True),
        sa.Column('override_reason', sa.Text(), nullable=True,
                  comment="Override reason cuando se salta un bloqueo"),
        sa.Column('before_state', sa.Text(), nullable=True,
                  comment="JSON con estado anterior de la linea"),
        sa.Column('after_state', sa.Text(), nullable=True,
                  comment="JSON con estado posterior de la linea"),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_op_audit_line_id', 'scout_liq_operation_audit', ['line_id'])
    op.create_index('ix_op_audit_action', 'scout_liq_operation_audit', ['action'])
    op.create_index('ix_op_audit_cutoff', 'scout_liq_operation_audit', ['cutoff_run_id'])
    op.create_index('ix_op_audit_created_at', 'scout_liq_operation_audit', ['created_at'])


def downgrade():
    op.drop_index('ix_op_audit_created_at', 'scout_liq_operation_audit')
    op.drop_index('ix_op_audit_cutoff', 'scout_liq_operation_audit')
    op.drop_index('ix_op_audit_action', 'scout_liq_operation_audit')
    op.drop_index('ix_op_audit_line_id', 'scout_liq_operation_audit')
    op.drop_table('scout_liq_operation_audit')
