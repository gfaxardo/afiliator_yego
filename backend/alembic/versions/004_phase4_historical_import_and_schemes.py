"""004_phase4_historical_import_and_schemes

Fase 4 - Historico integral de pagos, esquemas versionados,
carga masiva de scouts, pagos manuales, comision de supervisores,
bonos. No modifica tablas fuente.

Revision ID: 004
Revises: 003
Create Date: 2026-05-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extender scout_liq_scouts ──
    op.add_column("scout_liq_scouts", sa.Column("supervisor_name_raw", sa.String(255), nullable=True))
    op.add_column("scout_liq_scouts", sa.Column("supervisor_id", sa.Integer(), nullable=True))
    op.add_column("scout_liq_scouts", sa.Column("imported_from", sa.String(100), nullable=True))
    op.add_column("scout_liq_scouts", sa.Column("source_sheet", sa.String(100), nullable=True))
    op.add_column("scout_liq_scouts", sa.Column("source_row", sa.Integer(), nullable=True))
    op.add_column("scout_liq_scouts", sa.Column("external_key", sa.String(100), nullable=True))
    op.add_column("scout_liq_scouts", sa.Column("active_from", sa.Date(), nullable=True))
    op.add_column("scout_liq_scouts", sa.Column("active_to", sa.Date(), nullable=True))

    # ── Extender scout_liq_paid_history ──
    op.alter_column("scout_liq_paid_history", "cutoff_run_id", nullable=True)
    op.add_column("scout_liq_paid_history", sa.Column("import_source", sa.String(50), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("import_batch_id", sa.Integer(), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("source_file", sa.String(255), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("source_sheet", sa.String(100), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("source_row", sa.Integer(), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("driver_license_raw", sa.String(100), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("scout_name_raw", sa.String(255), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("supervisor_id", sa.Integer(), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("payment_scheme_id", sa.Integer(), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("payment_scheme_name", sa.String(255), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("payment_scheme_type", sa.String(50), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("milestone", sa.String(100), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("cutoff_external_id", sa.String(100), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("cutoff_window_from", sa.Date(), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("cutoff_window_to", sa.Date(), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("payment_component", sa.String(50), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("unique_hash", sa.String(255), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("paid_by", sa.String(100), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("scout_liq_paid_history", sa.Column("status", sa.String(50), server_default="paid"))
    op.add_column("scout_liq_paid_history", sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))

    # ── scout_liq_historical_import_batches ──
    op.create_table(
        "scout_liq_historical_import_batches",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("upload_batch_id", sa.String(100), nullable=True),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column("uploaded_by", sa.String(100), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("total_rows", sa.Integer(), server_default="0"),
        sa.Column("imported_count", sa.Integer(), server_default="0"),
        sa.Column("rejected_count", sa.Integer(), server_default="0"),
        sa.Column("manual_review_count", sa.Integer(), server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), server_default="0"),
        sa.Column("amount_imported", sa.Numeric(14, 2), server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── scout_liq_historical_import_lines ──
    op.create_table(
        "scout_liq_historical_import_lines",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("source_sheet", sa.String(100), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("corte_id_raw", sa.String(100), nullable=True),
        sa.Column("fecha_corte_raw", sa.String(100), nullable=True),
        sa.Column("fecha_pago_raw", sa.String(100), nullable=True),
        sa.Column("estado_pago_raw", sa.String(100), nullable=True),
        sa.Column("scout_name_raw", sa.String(255), nullable=True),
        sa.Column("scout_id_resolved", sa.Integer(), nullable=True),
        sa.Column("supervisor_raw", sa.String(255), nullable=True),
        sa.Column("supervisor_id_resolved", sa.Integer(), nullable=True),
        sa.Column("scout_type_raw", sa.String(50), nullable=True),
        sa.Column("origin_raw", sa.String(100), nullable=True),
        sa.Column("driver_license_raw", sa.String(100), nullable=True),
        sa.Column("driver_id_resolved", sa.String(100), nullable=True),
        sa.Column("driver_name_raw", sa.String(255), nullable=True),
        sa.Column("hire_date_raw", sa.String(100), nullable=True),
        sa.Column("payment_scheme_raw", sa.String(255), nullable=True),
        sa.Column("payment_rule_raw", sa.String(255), nullable=True),
        sa.Column("milestone_raw", sa.String(100), nullable=True),
        sa.Column("trips_reported_raw", sa.String(100), nullable=True),
        sa.Column("amount_paid_raw", sa.String(100), nullable=True),
        sa.Column("amount_paid", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(3), server_default="PEN"),
        sa.Column("payment_reference", sa.String(255), nullable=True),
        sa.Column("paid_by", sa.String(100), nullable=True),
        sa.Column("import_status", sa.String(50), server_default="pending"),
        sa.Column("import_reason", sa.Text(), nullable=True),
        sa.Column("paid_history_id", sa.Integer(), nullable=True),
        sa.Column("unique_hash", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["batch_id"], ["scout_liq_historical_import_batches.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── scout_liq_scheme_versions ──
    op.create_table(
        "scout_liq_scheme_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_name", sa.String(255), nullable=False),
        sa.Column("scheme_type", sa.String(50), nullable=False),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("scout_type", sa.String(50), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("source_sheet", sa.String(100), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── scout_liq_scheme_change_log ──
    op.create_table(
        "scout_liq_scheme_change_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scheme_id", sa.Integer(), nullable=False),
        sa.Column("old_config_json", sa.Text(), nullable=True),
        sa.Column("new_config_json", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.String(100), nullable=True),
        sa.Column("changed_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["scheme_id"], ["scout_liq_scheme_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── scout_liq_manual_payments ──
    op.create_table(
        "scout_liq_manual_payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cutoff_run_id", sa.Integer(), nullable=True),
        sa.Column("scout_id", sa.Integer(), nullable=False),
        sa.Column("supervisor_id", sa.Integer(), nullable=True),
        sa.Column("driver_id", sa.String(100), nullable=True),
        sa.Column("driver_license_raw", sa.String(100), nullable=True),
        sa.Column("payment_scheme_id", sa.Integer(), nullable=True),
        sa.Column("payment_rule", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="PEN"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("paid_history_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["scout_id"], ["scout_liq_scouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── scout_liq_supervisor_commissions ──
    op.create_table(
        "scout_liq_supervisor_commissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cutoff_run_id", sa.Integer(), nullable=True),
        sa.Column("supervisor_id", sa.Integer(), nullable=False),
        sa.Column("base_amount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("commission_rate", sa.Numeric(5, 4), server_default="0.10"),
        sa.Column("commission_amount", sa.Numeric(14, 2), server_default="0"),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("paid_history_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── scout_liq_scout_bonuses ──
    op.create_table(
        "scout_liq_scout_bonuses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cutoff_run_id", sa.Integer(), nullable=True),
        sa.Column("scout_id", sa.Integer(), nullable=False),
        sa.Column("bonus_type", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="PEN"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), server_default="draft"),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("paid_history_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["scout_id"], ["scout_liq_scouts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── Indices ──
    op.create_index("ix_ph_import_source", "scout_liq_paid_history", ["import_source"])
    op.create_index("ix_ph_unique_hash", "scout_liq_paid_history", ["unique_hash"])
    op.create_index("ix_ph_driver_license", "scout_liq_paid_history", ["driver_license_raw"])
    op.create_index("ix_ph_payment_component", "scout_liq_paid_history", ["payment_component"])
    op.create_index("ix_ph_supervisor", "scout_liq_paid_history", ["supervisor_id"])
    op.create_index("ix_scouts_supervisor", "scout_liq_scouts", ["supervisor_id"])
    op.create_index("ix_historical_lines_batch", "scout_liq_historical_import_lines", ["batch_id"])
    op.create_index("ix_historical_lines_hash", "scout_liq_historical_import_lines", ["unique_hash"])
    op.create_index("ix_scheme_versions_active", "scout_liq_scheme_versions", ["active"])
    op.create_index("ix_scheme_versions_type", "scout_liq_scheme_versions", ["scheme_type"])
    op.create_index("ix_manual_payments_scout", "scout_liq_manual_payments", ["scout_id"])
    op.create_index("ix_commission_supervisor", "scout_liq_supervisor_commissions", ["supervisor_id"])
    op.create_index("ix_commission_cutoff", "scout_liq_supervisor_commissions", ["cutoff_run_id"])
    op.create_index("ix_bonus_scout", "scout_liq_scout_bonuses", ["scout_id"])
    op.create_index("ix_bonus_cutoff", "scout_liq_scout_bonuses", ["cutoff_run_id"])


def downgrade() -> None:
    # Indices
    op.drop_index("ix_bonus_cutoff", table_name="scout_liq_scout_bonuses")
    op.drop_index("ix_bonus_scout", table_name="scout_liq_scout_bonuses")
    op.drop_index("ix_commission_cutoff", table_name="scout_liq_supervisor_commissions")
    op.drop_index("ix_commission_supervisor", table_name="scout_liq_supervisor_commissions")
    op.drop_index("ix_manual_payments_scout", table_name="scout_liq_manual_payments")
    op.drop_index("ix_scheme_versions_type", table_name="scout_liq_scheme_versions")
    op.drop_index("ix_scheme_versions_active", table_name="scout_liq_scheme_versions")
    op.drop_index("ix_historical_lines_hash", table_name="scout_liq_historical_import_lines")
    op.drop_index("ix_historical_lines_batch", table_name="scout_liq_historical_import_lines")
    op.drop_index("ix_scouts_supervisor", table_name="scout_liq_scouts")
    op.drop_index("ix_ph_supervisor", table_name="scout_liq_paid_history")
    op.drop_index("ix_ph_payment_component", table_name="scout_liq_paid_history")
    op.drop_index("ix_ph_driver_license", table_name="scout_liq_paid_history")
    op.drop_index("ix_ph_unique_hash", table_name="scout_liq_paid_history")
    op.drop_index("ix_ph_import_source", table_name="scout_liq_paid_history")

    # Tables
    op.drop_table("scout_liq_scout_bonuses")
    op.drop_table("scout_liq_supervisor_commissions")
    op.drop_table("scout_liq_manual_payments")
    op.drop_table("scout_liq_scheme_change_log")
    op.drop_table("scout_liq_scheme_versions")
    op.drop_table("scout_liq_historical_import_lines")
    op.drop_table("scout_liq_historical_import_batches")

    # Extended paid_history columns
    op.drop_column("scout_liq_paid_history", "updated_at")
    op.drop_column("scout_liq_paid_history", "status")
    op.drop_column("scout_liq_paid_history", "reason")
    op.drop_column("scout_liq_paid_history", "paid_by")
    op.drop_column("scout_liq_paid_history", "unique_hash")
    op.drop_column("scout_liq_paid_history", "payment_component")
    op.drop_column("scout_liq_paid_history", "cutoff_window_to")
    op.drop_column("scout_liq_paid_history", "cutoff_window_from")
    op.drop_column("scout_liq_paid_history", "cutoff_external_id")
    op.drop_column("scout_liq_paid_history", "milestone")
    op.drop_column("scout_liq_paid_history", "payment_scheme_type")
    op.drop_column("scout_liq_paid_history", "payment_scheme_name")
    op.drop_column("scout_liq_paid_history", "payment_scheme_id")
    op.drop_column("scout_liq_paid_history", "supervisor_id")
    op.drop_column("scout_liq_paid_history", "scout_name_raw")
    op.drop_column("scout_liq_paid_history", "driver_license_raw")
    op.drop_column("scout_liq_paid_history", "source_row")
    op.drop_column("scout_liq_paid_history", "source_sheet")
    op.drop_column("scout_liq_paid_history", "source_file")
    op.drop_column("scout_liq_paid_history", "import_batch_id")
    op.drop_column("scout_liq_paid_history", "import_source")
    op.alter_column("scout_liq_paid_history", "cutoff_run_id", nullable=False)

    # Extended scouts columns
    op.drop_column("scout_liq_scouts", "active_to")
    op.drop_column("scout_liq_scouts", "active_from")
    op.drop_column("scout_liq_scouts", "external_key")
    op.drop_column("scout_liq_scouts", "source_row")
    op.drop_column("scout_liq_scouts", "source_sheet")
    op.drop_column("scout_liq_scouts", "imported_from")
    op.drop_column("scout_liq_scouts", "supervisor_id")
    op.drop_column("scout_liq_scouts", "supervisor_name_raw")
