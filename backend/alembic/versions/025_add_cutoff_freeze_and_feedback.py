"""025_add_cutoff_freeze_and_feedback

Fase 2C/2D/2E/2UX: Snapshot integrity + feedback endpoint.
"""

from alembic import op
import sqlalchemy as sa

revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    # ── CutoffRun freeze fields ──
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('frozen_at', sa.DateTime(), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('frozen_by', sa.String(100), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('snapshot_hash', sa.String(64), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('snapshot_version', sa.Integer(), nullable=True, server_default=sa.text('1')))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('anchor_model_version', sa.String(20), nullable=True, server_default=sa.text("'2A.3'")))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('rules_snapshot', sa.Text(), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('totals_snapshot', sa.Text(), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('lines_count_snapshot', sa.Integer(), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('review_started_at', sa.DateTime(), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('review_completed_at', sa.DateTime(), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('exported_at', sa.DateTime(), nullable=True))
    op.add_column('scout_liq_cutoff_runs',
        sa.Column('is_stale', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # ── UX Feedback table ──
    op.create_table('scout_liq_ux_feedback',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('role', sa.String(50), nullable=True),
        sa.Column('screen', sa.String(100), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(20), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('scout_liq_ux_feedback')
    op.drop_column('scout_liq_cutoff_runs', 'is_stale')
    op.drop_column('scout_liq_cutoff_runs', 'exported_at')
    op.drop_column('scout_liq_cutoff_runs', 'review_completed_at')
    op.drop_column('scout_liq_cutoff_runs', 'review_started_at')
    op.drop_column('scout_liq_cutoff_runs', 'lines_count_snapshot')
    op.drop_column('scout_liq_cutoff_runs', 'totals_snapshot')
    op.drop_column('scout_liq_cutoff_runs', 'rules_snapshot')
    op.drop_column('scout_liq_cutoff_runs', 'anchor_model_version')
    op.drop_column('scout_liq_cutoff_runs', 'snapshot_version')
    op.drop_column('scout_liq_cutoff_runs', 'snapshot_hash')
    op.drop_column('scout_liq_cutoff_runs', 'frozen_by')
    op.drop_column('scout_liq_cutoff_runs', 'frozen_at')
