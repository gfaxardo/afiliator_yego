from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    Boolean,
    DateTime,
    Date,
    Text,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Scout(Base):
    __tablename__ = "scout_liq_scouts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scout_name = Column(String(255), nullable=False)
    document_number = Column(String(50))
    phone = Column(String(50))
    email = Column(String(255))
    country = Column(String(100))
    city = Column(String(100))
    scout_type = Column(String(50))
    status = Column(String(50), default="active")
    supervisor_name_raw = Column(String(255))
    supervisor_id = Column(Integer)
    imported_from = Column(String(100))
    source_sheet = Column(String(100))
    source_row = Column(Integer)
    external_key = Column(String(100))
    active_from = Column(Date)
    active_to = Column(Date)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    assignments = relationship("DriverAssignment", back_populates="scout")
    cutoff_summaries = relationship("CutoffScoutSummary", back_populates="scout")
    cutoff_lines = relationship("CutoffDriverLine", back_populates="scout")
    paid_history = relationship("PaidHistory", back_populates="scout")
    bonuses = relationship("ScoutBonus", back_populates="scout")
    manual_payments = relationship("ManualPayment", back_populates="scout")


class DriverAssignment(Base):
    __tablename__ = "scout_liq_driver_assignments"
    __table_args__ = (
        UniqueConstraint("driver_id", "scout_id", name="uq_driver_scout_active"),
        Index("ix_driver_active_origin", "driver_id", "source_origin",
              postgresql_where=text("status = 'active'")),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(String(100), nullable=False)
    scout_id = Column(Integer, ForeignKey("scout_liq_scouts.id"), nullable=False)
    origin = Column(String(100))
    assigned_at = Column(DateTime, server_default=func.now())
    hire_date = Column(Date)
    notes = Column(Text)
    status = Column(String(50), default="active", server_default="active")
    source_hire_date_raw = Column(String(100))
    source_origin = Column(String(100))
    assigned_by = Column(String(100))
    source_file = Column(String(255))
    source_sheet = Column(String(100))
    source_row = Column(Integer)
    import_batch_id = Column(Integer)
    license_raw = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    scout = relationship("Scout", back_populates="assignments")


class ConversionScheme(Base):
    __tablename__ = "scout_liq_conversion_schemes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_name = Column(String(255), nullable=False)
    origin = Column(String(100))
    scout_type = Column(String(50))
    country = Column(String(100))
    city = Column(String(100))
    min_affiliations = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    effective_from = Column(Date)
    effective_to = Column(Date)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    tiers = relationship("ConversionTier", back_populates="scheme")


class ConversionTier(Base):
    __tablename__ = "scout_liq_conversion_tiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_id = Column(
        Integer, ForeignKey("scout_liq_conversion_schemes.id"), nullable=False
    )
    min_conversion_rate = Column(Numeric(5, 4), nullable=False)
    payment_per_converted_driver = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="PEN")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    scheme = relationship("ConversionScheme", back_populates="tiers")


class CutoffRun(Base):
    __tablename__ = "scout_liq_cutoff_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cutoff_name = Column(String(255), nullable=False)
    hire_date_from = Column(Date)
    hire_date_to = Column(Date)
    origin_filter = Column(String(100))
    country_filter = Column(String(100))
    city_filter = Column(String(100))
    scout_type_filter = Column(String(50))
    status = Column(String(50), default="draft")
    config_snapshot = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    paid_at = Column(DateTime)
    quality_data_contract_status = Column(String(50))
    conversion_metric_code = Column(String(50))
    conversion_metric_status = Column(String(50))
    source_mapping_snapshot = Column(Text)
    excluded_invalid_hire_date_count = Column(Integer, default=0)
    excluded_missing_trip_counts_count = Column(Integer, default=0)
    unassigned_count = Column(Integer, default=0)
    total_source_drivers_count = Column(Integer, default=0)
    # ── Cohort temporal model ──
    cohort_iso_week = Column(String(20), nullable=True)
    cohort_from = Column(Date, nullable=True)
    cohort_to = Column(Date, nullable=True)
    maturity_days = Column(Integer, default=7)
    maturity_completed_at = Column(Date, nullable=True)
    ready_to_liquidate = Column(Boolean, default=False)
    snapshot_locked_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancelled_reason = Column(Text, nullable=True)
    cutoff_mode = Column(String(20), nullable=False, default="COHORT", server_default=text("'COHORT'"))

    summaries = relationship("CutoffScoutSummary", back_populates="cutoff_run")
    lines = relationship("CutoffDriverLine", back_populates="cutoff_run")
    paid_history = relationship("PaidHistory", back_populates="cutoff_run")
    commissions = relationship("SupervisorCommission", back_populates="cutoff_run")


class CutoffScoutSummary(Base):
    __tablename__ = "scout_liq_cutoff_scout_summary"
    __table_args__ = (
        UniqueConstraint(
            "cutoff_run_id", "scout_id", name="uq_cutoff_scout"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cutoff_run_id = Column(
        Integer, ForeignKey("scout_liq_cutoff_runs.id"), nullable=False
    )
    scout_id = Column(
        Integer, ForeignKey("scout_liq_scouts.id"), nullable=False
    )
    origin = Column(String(100))
    total_affiliations = Column(Integer, default=0)
    total_activated = Column(Integer, default=0)
    converted_5trips_7d = Column(Integer, default=0)
    total_converted_5v14d = Column(Integer, default=0)
    not_converted = Column(Integer, default=0)
    conversion_rate = Column(Numeric(5, 4))
    conversion_rate_5v7d = Column(Numeric(5, 4))
    tier_reached = Column(Numeric(5, 4))
    payment_per_converted_driver = Column(Numeric(10, 2))
    payout_per_activated = Column(Numeric(10, 2))
    amount_calculated = Column(Numeric(12, 2))
    amount_approved = Column(Numeric(12, 2))
    total_payable = Column(Numeric(12, 2))
    status = Column(String(50), default="pending")
    blocked_reason = Column(Text)
    drivers_1plus_0_7 = Column(Integer, default=0)
    drivers_5plus_0_7 = Column(Integer, default=0)
    drivers_1plus_8_14 = Column(Integer, default=0)
    drivers_5plus_0_14 = Column(Integer, default=0)
    conversion_1plus_0_7_rate = Column(Numeric(5, 4))
    conversion_5plus_0_7_rate = Column(Numeric(5, 4))
    conversion_5plus_0_14_rate = Column(Numeric(5, 4))
    metric_used = Column(String(100))
    summary_status = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    cutoff_run = relationship("CutoffRun", back_populates="summaries")
    scout = relationship("Scout", back_populates="cutoff_summaries")


class CutoffDriverLine(Base):
    __tablename__ = "scout_liq_cutoff_driver_lines"
    __table_args__ = (
        UniqueConstraint(
            "cutoff_run_id", "scout_id", "driver_id",
            name="uq_cutoff_driver_line"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cutoff_run_id = Column(
        Integer, ForeignKey("scout_liq_cutoff_runs.id"), nullable=False
    )
    scout_id = Column(
        Integer, ForeignKey("scout_liq_scouts.id"), nullable=False
    )
    driver_id = Column(String(100), nullable=False)
    hire_date = Column(Date)
    origin = Column(String(100))
    trips_7d = Column(Integer, default=0)
    trips_14d = Column(Integer, default=0)
    trips_0_7_count = Column(Integer)
    trips_8_14_count = Column(Integer)
    trips_0_14_count = Column(Integer)
    total_orders = Column(Integer)
    legacy_viajes_0_7_flag = Column(Boolean)
    legacy_viajes_8_14_flag = Column(Boolean)
    source_quality_status = Column(String(50))
    source_warning = Column(Text)
    line_status = Column(String(50))
    payment_rule = Column(String(255))
    activated_flag = Column(Boolean, default=False)
    is_converted_5trips_7d = Column(Boolean, default=False)
    is_converted_5trips_14d = Column(Boolean, default=False)
    driver_lifecycle_status = Column(String(50))
    payment_status = Column(String(50))
    payout_eligible_flag = Column(Boolean, default=False)
    calculated_amount = Column(Numeric(10, 2))
    eligible = Column(Boolean, default=True)
    blocked_reason = Column(Text)
    payment_formula_explanation = Column(Text)
    already_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    cutoff_run = relationship("CutoffRun", back_populates="lines")
    scout = relationship("Scout", back_populates="cutoff_lines")


class PaidHistory(Base):
    __tablename__ = "scout_liq_paid_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cutoff_run_id = Column(Integer, ForeignKey("scout_liq_cutoff_runs.id"), nullable=True)
    scout_id = Column(Integer, ForeignKey("scout_liq_scouts.id"), nullable=True)
    driver_id = Column(String(100))
    origin = Column(String(100))
    payment_rule = Column(String(255))
    amount_paid = Column(Numeric(10, 2))
    currency = Column(String(3), default="PEN")
    paid_at = Column(DateTime)
    payment_reference = Column(String(255))
    import_source = Column(String(50))
    import_batch_id = Column(Integer)
    source_file = Column(String(255))
    source_sheet = Column(String(100))
    source_row = Column(Integer)
    driver_license_raw = Column(String(100))
    scout_name_raw = Column(String(255))
    supervisor_id = Column(Integer)
    payment_scheme_id = Column(Integer)
    payment_scheme_name = Column(String(255))
    payment_scheme_type = Column(String(50))
    milestone = Column(String(100))
    cutoff_external_id = Column(String(100))
    cutoff_window_from = Column(Date)
    cutoff_window_to = Column(Date)
    payment_component = Column(String(50))
    unique_hash = Column(String(255))
    paid_by = Column(String(100))
    reason = Column(Text)
    status = Column(String(50), default="paid")
    resolution_status = Column(String(50))
    blocks_future_payment = Column(Boolean, default=True)
    financial_record_status = Column(String(50))
    original_payment_status_raw = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    cutoff_run = relationship("CutoffRun", back_populates="paid_history")
    scout = relationship("Scout", back_populates="paid_history")


class HistoricalImportBatch(Base):
    __tablename__ = "scout_liq_historical_import_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    upload_batch_id = Column(String(100))
    source_file = Column(String(255))
    uploaded_by = Column(String(100))
    uploaded_at = Column(DateTime, server_default=func.now())
    status = Column(String(50), default="pending")
    total_rows = Column(Integer, default=0)
    imported_count = Column(Integer, default=0)
    rejected_count = Column(Integer, default=0)
    manual_review_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    amount_imported = Column(Numeric(14, 2), default=0)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    lines = relationship("HistoricalImportLine", back_populates="batch")


class HistoricalImportLine(Base):
    __tablename__ = "scout_liq_historical_import_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("scout_liq_historical_import_batches.id"), nullable=False)
    source_sheet = Column(String(100))
    source_row = Column(Integer)
    corte_id_raw = Column(String(100))
    fecha_corte_raw = Column(String(100))
    fecha_pago_raw = Column(String(100))
    estado_pago_raw = Column(String(100))
    scout_name_raw = Column(String(255))
    scout_id_resolved = Column(Integer)
    supervisor_raw = Column(String(255))
    supervisor_id_resolved = Column(Integer)
    scout_type_raw = Column(String(50))
    origin_raw = Column(String(100))
    driver_license_raw = Column(String(100))
    driver_id_resolved = Column(String(100))
    driver_name_raw = Column(String(255))
    hire_date_raw = Column(String(100))
    payment_scheme_raw = Column(String(255))
    payment_rule_raw = Column(String(255))
    milestone_raw = Column(String(100))
    trips_reported_raw = Column(String(100))
    amount_paid_raw = Column(String(100))
    amount_paid = Column(Numeric(10, 2))
    currency = Column(String(3), default="PEN")
    payment_reference = Column(String(255))
    paid_by = Column(String(100))
    import_status = Column(String(50), default="pending")
    import_reason = Column(Text)
    attribution_status = Column(String(50))
    attribution_reason = Column(Text)
    payment_status = Column(String(50))
    payment_reason = Column(Text)
    payment_financial_status = Column(String(50))
    payment_financial_reason = Column(Text)
    payment_blocking_status = Column(String(50))
    payment_blocking_reason = Column(Text)
    blocks_future_payment = Column(Boolean)
    final_status = Column(String(50))
    attribution_id = Column(Integer)
    assignment_id = Column(Integer)
    paid_history_id = Column(Integer)
    unique_hash = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())

    batch = relationship("HistoricalImportBatch", back_populates="lines")


class SchemeVersion(Base):
    __tablename__ = "scout_liq_scheme_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_name = Column(String(255), nullable=False)
    scheme_type = Column(String(50), nullable=False)
    origin = Column(String(100))
    scout_type = Column(String(50))
    valid_from = Column(Date)
    valid_to = Column(Date)
    active = Column(Boolean, default=True)
    config_json = Column(Text)
    source_sheet = Column(String(100))
    source_row = Column(Integer)
    created_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    change_reason = Column(Text)

    change_logs = relationship("SchemeChangeLog", back_populates="scheme")


class SchemeChangeLog(Base):
    __tablename__ = "scout_liq_scheme_change_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_id = Column(Integer, ForeignKey("scout_liq_scheme_versions.id"), nullable=False)
    old_config_json = Column(Text)
    new_config_json = Column(Text)
    changed_by = Column(String(100))
    changed_at = Column(DateTime, server_default=func.now())
    reason = Column(Text)

    scheme = relationship("SchemeVersion", back_populates="change_logs")


class ManualPayment(Base):
    __tablename__ = "scout_liq_manual_payments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cutoff_run_id = Column(Integer)
    scout_id = Column(Integer, ForeignKey("scout_liq_scouts.id"), nullable=False)
    supervisor_id = Column(Integer)
    driver_id = Column(String(100))
    driver_license_raw = Column(String(100))
    payment_scheme_id = Column(Integer)
    payment_rule = Column(String(255))
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="PEN")
    reason = Column(Text, nullable=False)
    status = Column(String(50), default="draft")
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    paid_history_id = Column(Integer)
    created_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    scout = relationship("Scout", back_populates="manual_payments")


class SupervisorCommission(Base):
    __tablename__ = "scout_liq_supervisor_commissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cutoff_run_id = Column(Integer, ForeignKey("scout_liq_cutoff_runs.id"), nullable=True)
    supervisor_id = Column(Integer, nullable=False)
    base_amount = Column(Numeric(14, 2), default=0)
    commission_rate = Column(Numeric(5, 4), default=0.10)
    commission_amount = Column(Numeric(14, 2), default=0)
    status = Column(String(50), default="pending")
    paid_history_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    cutoff_run = relationship("CutoffRun", back_populates="commissions")


class ScoutBonus(Base):
    __tablename__ = "scout_liq_scout_bonuses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cutoff_run_id = Column(Integer)
    scout_id = Column(Integer, ForeignKey("scout_liq_scouts.id"), nullable=False)
    bonus_type = Column(String(50), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="PEN")
    reason = Column(Text, nullable=False)
    status = Column(String(50), default="draft")
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    paid_history_id = Column(Integer)
    created_by = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    scout = relationship("Scout", back_populates="bonuses")


class HistoricalAttribution(Base):
    __tablename__ = "scout_liq_historical_attributions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    import_batch_id = Column(Integer)
    source_file = Column(String(255))
    source_sheet = Column(String(100))
    source_row = Column(Integer)
    cutoff_external_id = Column(String(100))
    scout_id_resolved = Column(Integer)
    scout_name_raw = Column(String(255))
    supervisor_id_resolved = Column(Integer)
    supervisor_name_raw = Column(String(255))
    scout_type_raw = Column(String(50))
    origin_raw = Column(String(100))
    driver_license_raw = Column(String(100))
    driver_id_resolved = Column(String(100))
    driver_name_raw = Column(String(255))
    driver_phone_raw = Column(String(50))
    hire_date_raw = Column(String(100))
    hire_date_resolved = Column(Date)
    assignment_date_raw = Column(String(100))
    assignment_status = Column(String(50))
    payment_status_raw = Column(String(100))
    payment_amount_raw = Column(String(100))
    payment_amount = Column(Numeric(10, 2))
    payment_rule_raw = Column(String(255))
    operational_flags_json = Column(Text)
    import_status = Column(String(50), default="pending")
    import_reason = Column(Text)
    linked_assignment_id = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())


# ═══════════════════════════════════════════════════════════════════════════
# PAYMENT SCHEMES VERSIONADOS
# ═══════════════════════════════════════════════════════════════════════════

class PaymentScheme(Base):
    __tablename__ = "scout_liq_payment_schemes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    scheme_type = Column(String(50), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    versions = relationship("PaymentSchemeVersion", back_populates="scheme")


class PaymentSchemeVersion(Base):
    __tablename__ = "scout_liq_payment_scheme_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_id = Column(Integer, ForeignKey("scout_liq_payment_schemes.id"), nullable=False)
    version_name = Column(String(100), nullable=False)
    valid_from_cohort_iso_week = Column(String(20), nullable=False)
    valid_to_cohort_iso_week = Column(String(20), nullable=True)
    maturity_days = Column(Integer, default=7, nullable=False)
    min_activated = Column(Integer, default=8, nullable=False)
    activation_rule = Column(String(50), nullable=False, default="1V7D")
    quality_rule = Column(String(50), nullable=False, default="5V7D")
    formula_type = Column(String(50), nullable=False, default="ACTIVATED_X_TIER")
    currency = Column(String(3), nullable=False, default="PEN")
    # ── Campos semanticos multi-esquema ──
    volume_rule = Column(String(50), nullable=True)
    min_volume_count = Column(Integer, nullable=True)
    pays_on_rule = Column(String(50), nullable=True)
    payout_formula_type = Column(String(50), nullable=True)
    counts_volume_rule = Column(String(50), nullable=True)
    counts_quality_rule = Column(String(50), nullable=True)
    maturity_window_days = Column(Integer, nullable=True)
    fixed_payout_amount = Column(Numeric(10, 2), nullable=True)
    minimum_enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    status = Column(String(20), nullable=False, default="draft")
    created_at = Column(DateTime, server_default=func.now())
    activated_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)

    scheme = relationship("PaymentScheme", back_populates="versions")
    tiers = relationship("PaymentSchemeTier", back_populates="version")

    __table_args__ = (
        UniqueConstraint(
            "scheme_id", "valid_from_cohort_iso_week",
            name="uq_scheme_version_valid_from"
        ),
    )


class PaymentSchemeTier(Base):
    __tablename__ = "scout_liq_payment_scheme_tiers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_version_id = Column(
        Integer, ForeignKey("scout_liq_payment_scheme_versions.id"), nullable=False
    )
    min_conversion_rate = Column(Numeric(5, 4), nullable=False)
    payout_amount = Column(Numeric(10, 2), nullable=False)
    sort_order = Column(Integer, default=0)

    version = relationship("PaymentSchemeVersion", back_populates="tiers")


# ═══════════════════════════════════════════════════════════════════════════
# MANUAL OVERRIDES
# ═══════════════════════════════════════════════════════════════════════════

class ManualOverride(Base):
    __tablename__ = "scout_liq_manual_overrides"

    id = Column(Integer, primary_key=True, autoincrement=True)
    driver_id = Column(String(100), nullable=False)
    cohort_iso_week = Column(String(20), nullable=True)
    scout_id_before = Column(Integer, nullable=True)
    scout_id_after = Column(Integer, nullable=True)
    override_type = Column(String(50), nullable=False)
    amount = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="PEN")
    reason = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    blocks_future_payment = Column(Boolean, default=False)
    paid_history_id = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH REGISTRY — Auto Health Monitoring
# ═══════════════════════════════════════════════════════════════════════════

class RefreshRegistry(Base):
    __tablename__ = "scout_liq_refresh_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(255), nullable=False, unique=True)
    source_type = Column(String(50), nullable=False, default="table")
    last_seen_data_at = Column(DateTime, nullable=True)
    last_refresh_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    expected_frequency_minutes = Column(Integer, nullable=False, default=1440)
    lag_minutes = Column(Integer, nullable=True)
    rows_observed = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default="unknown")
    reason_text = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class HealthEvent(Base):
    __tablename__ = "scout_liq_health_events"
    __table_args__ = (
        Index("ix_health_events_dedup", "event_type", "source_name", "cohort_key",
              postgresql_where=text("status = 'open'"),
              unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False, default="warning")
    source_name = Column(String(255), nullable=True)
    cohort_key = Column(String(20), nullable=True)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    detected_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime, nullable=True)
    metadata_json = Column(Text, nullable=True)
