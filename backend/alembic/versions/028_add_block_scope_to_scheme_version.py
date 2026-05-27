"""028_add_block_scope_to_scheme_version

Agrega block_scope y cohort_target_count a scout_liq_payment_scheme_versions.

Revision ID: 028
Revises: 027
Create Date: 2026-05-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scout_liq_payment_scheme_versions", sa.Column("block_scope", sa.String(50), nullable=True, server_default=sa.text("'driver_global'")))
    op.add_column("scout_liq_payment_scheme_versions", sa.Column("cohort_target_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("scout_liq_payment_scheme_versions", "cohort_target_count")
    op.drop_column("scout_liq_payment_scheme_versions", "block_scope")
