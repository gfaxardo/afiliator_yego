from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import date, datetime
from decimal import Decimal


class ScoutCreate(BaseModel):
    scout_name: str
    document_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    scout_type: Optional[str] = None
    status: Optional[str] = "active"
    supervisor_name_raw: Optional[str] = None
    supervisor_id: Optional[int] = None
    imported_from: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    external_key: Optional[str] = None
    active_from: Optional[date] = None
    active_to: Optional[date] = None


class ScoutUpdate(BaseModel):
    scout_name: Optional[str] = None
    document_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    scout_type: Optional[str] = None
    status: Optional[str] = None
    supervisor_name_raw: Optional[str] = None
    supervisor_id: Optional[int] = None
    external_key: Optional[str] = None
    active_from: Optional[date] = None
    active_to: Optional[date] = None


class ScoutResponse(BaseModel):
    id: int
    scout_name: str
    document_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    scout_type: Optional[str] = None
    status: Optional[str] = None
    supervisor_name_raw: Optional[str] = None
    supervisor_id: Optional[int] = None
    imported_from: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    external_key: Optional[str] = None
    active_from: Optional[date] = None
    active_to: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConversionTierResponse(BaseModel):
    id: int
    scheme_id: int
    min_conversion_rate: float
    payment_per_converted_driver: float
    currency: str
    active: bool

    model_config = {"from_attributes": True}


class ConversionSchemeCreate(BaseModel):
    scheme_name: str
    origin: Optional[str] = None
    scout_type: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    min_affiliations: int = 0
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class ConversionSchemeResponse(BaseModel):
    id: int
    scheme_name: str
    origin: Optional[str] = None
    scout_type: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    min_affiliations: int
    active: bool
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    tiers: List[ConversionTierResponse] = []
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    status: str
    environment: str
    source_table: str


# --- Fase 2: Source Driver & Assignment Schemas ---

class SourceDriverResponse(BaseModel):
    driver_id: Optional[str] = None
    driver_nombre: Optional[str] = None
    driver_apellido: Optional[str] = None
    driver_placa: Optional[str] = None
    driver_phone: Optional[str] = None
    park_name: Optional[str] = None
    park_id: Optional[str] = None
    license: Optional[str] = None
    origin: Optional[str] = None
    legacy_viajes_0_7_flag: Optional[bool] = None
    legacy_viajes_8_14_flag: Optional[bool] = None
    total_orders: Optional[int] = None
    trips_0_7_count: Optional[int] = None
    trips_8_14_count: Optional[int] = None
    trips_0_14_count: Optional[int] = None
    hire_date_raw: Optional[str] = None
    hire_date_parsed: Optional[str] = None
    source_status: Optional[str] = None
    source_quality_status: Optional[str] = None
    status: Optional[str] = None
    segment: Optional[str] = None
    stage: Optional[str] = None
    conexion: Optional[str] = None
    last_active_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SourceDriverListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    drivers: List[SourceDriverResponse]


class AssignmentCreate(BaseModel):
    driver_id: str
    scout_id: int
    origin: Optional[str] = None
    notes: Optional[str] = None


class AssignmentResponse(BaseModel):
    id: int
    driver_id: str
    scout_id: int
    origin: Optional[str] = None
    hire_date: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    source_hire_date_raw: Optional[str] = None
    source_origin: Optional[str] = None
    assigned_by: Optional[str] = None
    assigned_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    scout_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AssignmentUploadResult(BaseModel):
    total_rows: int
    created: int
    skipped_duplicates: int
    invalid_driver: int
    invalid_scout: int
    missing_hire_date_warnings: int
    errors: List[str] = []
    warnings: List[str] = []


class SourceDiagnosticSummary(BaseModel):
    total_rows: int
    with_hire_date: int
    without_hire_date: int
    legacy_with_trips_0_7: int = 0
    legacy_without_trips_0_7: int = 0
    legacy_with_trips_8_14: int = 0
    legacy_without_trips_8_14: int = 0
    by_origin: List[dict] = []
    assigned_drivers: int = 0
    unassigned_drivers: int = 0


# --- Fase 4: Paid History ---

class PaidHistoryResponse(BaseModel):
    id: int
    cutoff_run_id: Optional[int] = None
    scout_id: int
    driver_id: Optional[str] = None
    origin: Optional[str] = None
    payment_rule: Optional[str] = None
    amount_paid: Optional[float] = None
    currency: Optional[str] = None
    paid_at: Optional[datetime] = None
    payment_reference: Optional[str] = None
    import_source: Optional[str] = None
    import_batch_id: Optional[int] = None
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    driver_license_raw: Optional[str] = None
    scout_name_raw: Optional[str] = None
    supervisor_id: Optional[int] = None
    payment_scheme_id: Optional[int] = None
    payment_scheme_name: Optional[str] = None
    payment_scheme_type: Optional[str] = None
    milestone: Optional[str] = None
    cutoff_external_id: Optional[str] = None
    cutoff_window_from: Optional[date] = None
    cutoff_window_to: Optional[date] = None
    payment_component: Optional[str] = None
    unique_hash: Optional[str] = None
    paid_by: Optional[str] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Fase 4: Historical Import ---

class HistoricalImportLineResponse(BaseModel):
    id: int
    batch_id: int
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    corte_id_raw: Optional[str] = None
    scout_name_raw: Optional[str] = None
    scout_id_resolved: Optional[int] = None
    driver_license_raw: Optional[str] = None
    driver_id_resolved: Optional[str] = None
    driver_name_raw: Optional[str] = None
    payment_scheme_raw: Optional[str] = None
    amount_paid_raw: Optional[str] = None
    amount_paid: Optional[float] = None
    import_status: Optional[str] = None
    import_reason: Optional[str] = None
    paid_history_id: Optional[int] = None
    unique_hash: Optional[str] = None

    model_config = {"from_attributes": True}


class HistoricalImportBatchResponse(BaseModel):
    id: int
    upload_batch_id: Optional[str] = None
    source_file: Optional[str] = None
    uploaded_by: Optional[str] = None
    status: Optional[str] = None
    total_rows: int = 0
    imported_count: int = 0
    rejected_count: int = 0
    manual_review_count: int = 0
    duplicate_count: int = 0
    amount_imported: Optional[float] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class HistoricalImportPreviewResult(BaseModel):
    batch_id: Optional[int] = None
    source_file: Optional[str] = None
    sheet: Optional[str] = None
    total_rows: int = 0
    will_import: int = 0
    will_reject: int = 0
    manual_review: int = 0
    duplicate_count: int = 0
    total_amount: float = 0
    lines: List[dict] = []


# --- Fase 4: Scout Upload ---

class ScoutUploadPreviewResult(BaseModel):
    sheet: Optional[str] = None
    total_rows: int = 0
    will_create: int = 0
    will_update: int = 0
    duplicate_skipped: int = 0
    manual_review: int = 0
    rejected: int = 0
    lines: List[dict] = []


class ScoutUploadCommitResult(BaseModel):
    sheet: Optional[str] = None
    total_rows: int = 0
    created: int = 0
    updated: int = 0
    duplicate_skipped: int = 0
    manual_review: int = 0
    rejected: int = 0


# --- Fase 4: Scheme Import ---

class SchemeVersionResponse(BaseModel):
    id: int
    scheme_name: str
    scheme_type: str
    origin: Optional[str] = None
    scout_type: Optional[str] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    active: bool = True
    config_json: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    change_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class SchemeImportPreviewResult(BaseModel):
    sheet: Optional[str] = None
    total_rows: int = 0
    will_import: int = 0
    will_skip: int = 0
    errors: int = 0
    lines: List[dict] = []


class SchemeImportCommitResult(BaseModel):
    sheet: Optional[str] = None
    total_rows: int = 0
    created: int = 0
    skipped: int = 0
    errors: int = 0


# --- Fase 4: Manual Payments ---

class ManualPaymentCreate(BaseModel):
    cutoff_run_id: Optional[int] = None
    scout_id: int
    supervisor_id: Optional[int] = None
    driver_id: Optional[str] = None
    driver_license_raw: Optional[str] = None
    payment_scheme_id: Optional[int] = None
    payment_rule: Optional[str] = None
    amount: float
    currency: Optional[str] = "PEN"
    reason: str
    payment_component: Optional[str] = "manual_adjustment"
    created_by: Optional[str] = None


class ManualPaymentResponse(BaseModel):
    id: int
    cutoff_run_id: Optional[int] = None
    scout_id: int
    supervisor_id: Optional[int] = None
    driver_id: Optional[str] = None
    driver_license_raw: Optional[str] = None
    payment_scheme_id: Optional[int] = None
    payment_rule: Optional[str] = None
    amount: float
    currency: str
    reason: str
    status: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    paid_history_id: Optional[int] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ManualPaymentApprove(BaseModel):
    approved_by: Optional[str] = None
    payment_reference: Optional[str] = None


# --- Fase 4: Bonuses ---

class ScoutBonusCreate(BaseModel):
    cutoff_run_id: Optional[int] = None
    scout_id: int
    bonus_type: str = "best_scout"
    amount: float
    currency: Optional[str] = "PEN"
    reason: str
    created_by: Optional[str] = None


class ScoutBonusResponse(BaseModel):
    id: int
    cutoff_run_id: Optional[int] = None
    scout_id: int
    bonus_type: str
    amount: float
    currency: str
    reason: str
    status: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    paid_history_id: Optional[int] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ScoutBonusApprove(BaseModel):
    approved_by: Optional[str] = None
    payment_reference: Optional[str] = None


# --- Fase 4: Supervisor Commission ---

class SupervisorCommissionResponse(BaseModel):
    id: int
    cutoff_run_id: Optional[int] = None
    supervisor_id: int
    base_amount: Optional[float] = None
    commission_rate: Optional[float] = None
    commission_amount: Optional[float] = None
    status: str
    paid_history_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# --- Fase 4.6: Historical Attributions ---

class AttributionLineResponse(BaseModel):
    id: int
    import_batch_id: Optional[int] = None
    source_file: Optional[str] = None
    source_sheet: Optional[str] = None
    source_row: Optional[int] = None
    cutoff_external_id: Optional[str] = None
    scout_id_resolved: Optional[int] = None
    scout_name_raw: Optional[str] = None
    supervisor_id_resolved: Optional[int] = None
    supervisor_name_raw: Optional[str] = None
    driver_license_raw: Optional[str] = None
    driver_id_resolved: Optional[str] = None
    driver_name_raw: Optional[str] = None
    origin_raw: Optional[str] = None
    payment_status_raw: Optional[str] = None
    payment_amount: Optional[float] = None
    import_status: Optional[str] = None
    import_reason: Optional[str] = None
    linked_assignment_id: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AttributionImportPreviewResult(BaseModel):
    batch_id: Optional[int] = None
    source_file: Optional[str] = None
    sheet: Optional[str] = None
    total_rows: int = 0
    ready_to_import: int = 0
    manual_review: int = 0
    conflicts: int = 0
    duplicates: int = 0
    rejected: int = 0
    lines: List[dict] = []


class AttributionImportCommitResult(BaseModel):
    batch_id: Optional[int] = None
    assignments_created: int = 0
    assignments_updated: int = 0
    historical_attributions_created: int = 0
    manual_review: int = 0
    conflicts: int = 0
    duplicates: int = 0
    rejected: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# Canonical Operation Snapshot (Fase: fuente maestra)
# ═══════════════════════════════════════════════════════════════════════════

class CanonicalDriverItem(BaseModel):
    driver_id: Optional[str] = None
    driver_name: str = ""
    license: Optional[str] = None
    hire_date: Optional[str] = None
    iso_week: Optional[str] = None
    iso_week_label: Optional[str] = None
    origin: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    scout_id: Optional[int] = None
    scout_name: Optional[str] = None
    supervisor_name: Optional[str] = None
    attribution_status: str = "unassigned"
    trips_7d: int = 0
    trips_14d: int = 0
    trips_0_30: Optional[int] = None
    activated_flag: bool = False
    converted_5v7d: bool = False
    converted_5v14d: bool = False
    driver_lifecycle_status: str = "no_trip"
    legacy_viajes_0_7: Optional[bool] = None
    legacy_viajes_8_14: Optional[bool] = None
    total_orders: Optional[int] = None
    payment_status: str = "not_payable"
    payment_origin: str = "none"
    payment_rule_label: Optional[str] = None
    payment_evidence_label: Optional[str] = None
    payment_trace_status: Optional[str] = "ok"
    payment_trace_warning: Optional[str] = None
    payment_basis_label: Optional[str] = None
    amount: Optional[float] = None
    paid_history_id: Optional[int] = None
    reason: str = "ok"
    counts_as_activated_base: bool = False
    counts_as_quality_5v7d: bool = False
    counts_for_payment: bool = False
    scout_activated_base: int = 0
    scout_quality_5v7d: int = 0
    scout_conversion_rate_5v7d: float = 0.0
    scout_tier_amount: float = 0.0
    scout_tier_threshold: float = 0.0
    payment_formula_label: Optional[str] = ""
    source_driver_status: Optional[str] = None
    source_updated_at: Optional[str] = None


class CanonicalFreshness(BaseModel):
    source_max_hire_date: Optional[str] = None
    data_lag_days: Optional[int] = None
    source_max_updated_at: Optional[str] = None
    source_max_created_at: Optional[str] = None
    total_source_rows: Optional[int] = None
    null_invalid_driver_id_count: Optional[int] = None
    null_hire_date_count: Optional[int] = None
    freshness_status: str = "unknown"


class CanonicalOperationSnapshotResponse(BaseModel):
    total: int = 0
    limit: int = 100
    offset: int = 0
    items: List[CanonicalDriverItem] = []
    freshness: CanonicalFreshness = CanonicalFreshness()


class OperationDiagnosticResponse(BaseModel):
    source_table: str = ""
    filters_applied: dict = {}
    base_counts: dict = {}
    trip_metrics: dict = {}
    payment_metrics: dict = {}
    freshness: dict = {}
    attribution_quality: dict = {}


# ── Cohort temporal model ──

class CohortItem(BaseModel):
    cohort_iso_week: str
    cohort_label: str
    iso_year: int
    iso_week: int
    cohort_from: str
    cohort_to: str
    maturity_days: int = 7
    maturity_completed_at: str
    is_mature: bool = False
    total_drivers: int = 0
    drivers_with_scout: int = 0
    drivers_without_scout: int = 0
    activated: int = 0
    converted_5v7d: int = 0
    readiness_status: str = "open"
    cutoff_run_id: Optional[int] = None
    cutoff_status: Optional[str] = None


class CohortListResponse(BaseModel):
    total: int = 0
    cohorts: List[CohortItem] = []


class CohortDiagnosticResponse(BaseModel):
    current_date: str = ""
    total_cohorts: int = 0
    by_readiness: dict = {}
    liquidable_cohorts: List[str] = []
    latest_open: Optional[str] = None
    latest_mature: Optional[str] = None
    latest_mature_matures_on: Optional[str] = None
    open_details: List[dict] = []
    mature_details: List[dict] = []


# ── Payment Scheme Resolver ──

class TierItem(BaseModel):
    min_conversion_rate: float = 0.0
    payout_amount: float = 0.0
    sort_order: int = 0


class ResolvedPaymentScheme(BaseModel):
    scheme_id: int
    scheme_name: str = ""
    scheme_type: str = ""
    description: Optional[str] = None
    scheme_version_id: int
    version_name: str = ""
    valid_from_cohort_iso_week: str = ""
    valid_to_cohort_iso_week: Optional[str] = None
    maturity_days: int = 7
    maturity_window_days: int = 7
    min_activated: int = 8
    min_volume_count: int = 8
    activation_rule: str = "1V7D"
    volume_rule: str = "1V7D"
    quality_rule: str = "5V7D"
    counts_volume_rule: str = "1V7D"
    counts_quality_rule: str = "5V7D"
    formula_type: str = "ACTIVATED_X_TIER"
    pays_on_rule: str = "ACTIVATED_BASE"
    payout_formula_type: str = "ACTIVATED_X_TIER"
    currency: str = "PEN"
    tiers: List[TierItem] = []


# ── Payment Scheme Admin ──

class PaymentSchemeListItem(BaseModel):
    scheme_id: int
    name: str = ""
    scheme_type: str = ""
    description: Optional[str] = None
    is_active: bool = True
    active_version_id: Optional[int] = None
    active_version_name: Optional[str] = None
    active_since_cohort: Optional[str] = None
    version_count: int = 0
    created_at: Optional[str] = None


class PaymentSchemeDetail(BaseModel):
    scheme_id: int
    name: str = ""
    scheme_type: str = ""
    description: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    versions: List[dict] = []


class CreatePaymentSchemeRequest(BaseModel):
    name: str
    scheme_type: str
    description: Optional[str] = None


class TierInput(BaseModel):
    min_conversion_rate: float
    payout_amount: float


class CreateVersionRequest(BaseModel):
    version_name: str
    valid_from_cohort_iso_week: str
    maturity_days: int = 7
    maturity_window_days: Optional[int] = None
    min_activated: int = 8
    min_volume_count: Optional[int] = None
    activation_rule: str = "1V7D"
    volume_rule: Optional[str] = None
    quality_rule: str = "5V7D"
    counts_volume_rule: Optional[str] = None
    counts_quality_rule: Optional[str] = None
    formula_type: str = "ACTIVATED_X_TIER"
    pays_on_rule: Optional[str] = None
    payout_formula_type: Optional[str] = None
    currency: str = "PEN"
    tiers: List[TierInput]


class VersionCreatedResponse(BaseModel):
    version_id: int
    version_name: str = ""
    scheme_id: int
    valid_from_cohort_iso_week: str = ""
    status: str = "draft"
    tiers_count: int = 0


class VersionActivatedResponse(BaseModel):
    version_id: int
    version_name: str = ""
    scheme_id: int
    status: str = "active"
    valid_from_cohort_iso_week: str = ""
    activated_at: Optional[str] = None
    previous_active_archived: Optional[str] = None
    previous_active_closed_at: Optional[str] = None


class SchemeCreatedResponse(BaseModel):
    scheme_id: int
    name: str = ""
    scheme_type: str = ""


# ── Manual Overrides ──

class ManualOverrideResponse(BaseModel):
    id: int
    driver_id: str = ""
    cohort_iso_week: Optional[str] = None
    scout_id_before: Optional[int] = None
    scout_id_after: Optional[int] = None
    override_type: str = ""
    amount: Optional[float] = None
    currency: str = "PEN"
    reason: str = ""
    notes: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    status: str = "pending"
    blocks_future_payment: bool = False
    paid_history_id: Optional[int] = None


class CreateManualOverrideRequest(BaseModel):
    driver_id: str
    override_type: str
    reason: str
    cohort_iso_week: Optional[str] = None
    scout_id: Optional[int] = None
    scout_id_before: Optional[int] = None
    amount: Optional[float] = None
    currency: str = "PEN"
    notes: Optional[str] = None
    created_by: Optional[str] = None


# ── Reconciliation ──

class ReconciliationCompareResponse(BaseModel):
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_rows: int = 0
    amount_mismatch: int = 0
    already_paid: int = 0
    missing_in_system: int = 0
    missing_in_upload: int = 0
    details: List[Any] = []
    suggested_actions: List[str] = []


# ── Unified Load ──

class UnifiedLoadPreviewLine(BaseModel):
    source_row: int = 0
    licencia: str = ""
    scout: str = ""
    supervisor: str = ""
    pagado: str = ""
    monto_pagado: float = 0.0
    fecha_pago: str = ""
    status: str = "ok"
    errors: List[str] = []
    warnings: List[str] = []
    deduced_actions: List[str] = []
    driver_id_resolved: Optional[str] = None
    scout_id_resolved: Optional[int] = None


class UnifiedLoadPreviewResponse(BaseModel):
    total_rows: int = 0
    valid_rows: int = 0
    error_rows: int = 0
    duplicate_rows: int = 0
    drivers_found: int = 0
    drivers_not_found: int = 0
    scouts_to_create: int = 0
    supervisors_to_create: int = 0
    assignments_to_create: int = 0
    assignments_to_change: int = 0
    assignments_already_exist: int = 0
    payments_to_create: int = 0
    already_paid: int = 0
    amount_mismatch: int = 0
    warnings: List[str] = []
    lines: List[UnifiedLoadPreviewLine] = []
    apply_plan: List[Any] = []
    parse_metadata: Any = {}


class UnifiedLoadApplyDetail(BaseModel):
    source_row: int = 0
    status: str = ""
    reason: Optional[str] = None
    driver_id: Optional[str] = None
    scout_id: Optional[int] = None
    scout_name: Optional[str] = None
    payment_created: bool = False
    assignment_created: bool = False
    what_happened: Optional[List[str]] = None
    action_requested: Optional[str] = None
    action_executed: Optional[str] = None
    skipped_reason: Optional[str] = None
    existing_assignment_id: Optional[int] = None


class UnifiedLoadApplyResponse(BaseModel):
    applied: int = 0
    skipped: int = 0
    errors: int = 0
    details: List[UnifiedLoadApplyDetail] = []
    assignments_new: int = 0
    assignments_existing: int = 0
    payments_new: int = 0
    payments_existing: int = 0
    commit_ok: Optional[bool] = None
    commit_error: Optional[str] = None
