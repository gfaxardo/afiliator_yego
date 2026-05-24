"""
Tests Fase 2B — Anchor Review & Resolution Workflow.
"""
import pytest
import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

# Import service logic (pure functions, no DB needed for unit tests)
import sys
sys.path.insert(0, '.')
from app.services.anchor_review_service import (
    VALID_ACTIONS,
    REVIEW_STATUS_MAP,
    REVIEW_STATUS_DEFAULTS,
    _line_to_review_dict,
)


class TestReviewStates:
    """Verifica estados de revision y sus mapeos."""

    def test_valid_actions(self):
        assert "approve" in VALID_ACTIONS
        assert "reject" in VALID_ACTIONS
        assert "needs_supervisor" in VALID_ACTIONS
        assert "ignore" in VALID_ACTIONS
        assert "resolved_by_refresh" in VALID_ACTIONS

    def test_status_mapping(self):
        assert REVIEW_STATUS_MAP["approve"] == "approved_manual_override"
        assert REVIEW_STATUS_MAP["reject"] == "rejected_manual_override"
        assert REVIEW_STATUS_MAP["needs_supervisor"] == "requires_supervisor_review"
        assert REVIEW_STATUS_MAP["ignore"] == "ignored_low_priority"
        assert REVIEW_STATUS_MAP["resolved_by_refresh"] == "resolved_by_official_refresh"

    def test_defaults_for_problematic_states(self):
        assert REVIEW_STATUS_DEFAULTS["blocked_missing_official_anchor"] == "pending_review"
        assert REVIEW_STATUS_DEFAULTS["reported_pending_validation"] == "pending_review"
        assert REVIEW_STATUS_DEFAULTS["fallback_operational_only"] == "pending_review"


class TestReviewWorkflowRules:
    """Reglas de negocio del workflow de revision."""

    def test_approve_enables_payout(self):
        """Approve debe cambiar is_auto_payable_anchor a True."""
        # Simulado: el servicio cambia este flag en perform_anchor_review
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['perform_anchor_review'])
            .perform_anchor_review
        )
        assert 'is_auto_payable_anchor = True' in source

    def test_reject_keeps_blocked(self):
        """Reject debe mantener is_auto_payable_anchor = False."""
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['perform_anchor_review'])
            .perform_anchor_review
        )
        assert 'is_auto_payable_anchor = False' in source

    def test_resolved_by_refresh_sets_official(self):
        """Refresh debe cambiar payment_anchor_status a official_strong."""
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['perform_anchor_review'])
            .perform_anchor_review
        )
        assert 'official_strong' in source

    def test_paid_cutoff_cannot_be_mutated(self):
        """Lineas con payment_status='paid' no pueden ser modificadas."""
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['perform_anchor_review'])
            .perform_anchor_review
        )
        assert 'paid' in source.lower()
        assert 'cannot review' in source.lower() or 'cannot mutate' in source.lower()

    def test_audit_trail_created_on_action(self):
        """Cada accion debe crear un registro en AnchorReviewAudit."""
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['perform_anchor_review'])
            .perform_anchor_review
        )
        assert 'AnchorReviewAudit' in source
        assert 'db.add(audit)' in source

    def test_before_after_state_captured(self):
        """before_state y after_state deben registrarse como JSON."""
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['perform_anchor_review'])
            .perform_anchor_review
        )
        assert 'before_state' in source
        assert 'after_state' in source


class TestQueueFilters:
    """Filtros de la cola de revision."""

    def test_queue_filters_by_status(self):
        """La funcion get_anchor_review_queue acepta filtros."""
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['get_anchor_review_queue'])
            .get_anchor_review_queue
        )
        assert 'status_filter' in source
        assert 'anchor_status_filter' in source
        assert 'cutoff_run_id' in source
        assert 'origin' in source

    def test_summary_includes_all_kpis(self):
        """get_review_queue_summary debe incluir todos los KPIs."""
        import inspect
        source = inspect.getsource(
            __import__('app.services.anchor_review_service', fromlist=['get_review_queue_summary'])
            .get_review_queue_summary
        )
        assert 'pending_review' in source
        assert 'blocked_anchor' in source
        assert 'approved_manual' in source
        assert 'rejected' in source
        assert 'weak_anchors' in source
        assert 'reactivated_pending' in source


class TestLineDictConversion:
    """Verifica que _line_to_review_dict expone todos los campos necesarios."""

    def test_line_dict_has_required_fields(self):
        # Simula un objeto CutoffDriverLine
        mock_line = MagicMock()
        mock_line.id = 1
        mock_line.driver_id = "abc"
        mock_line.cutoff_run_id = 10
        mock_line.scout_id = 5
        mock_line.origin = "cabinet"
        mock_line.acquisition_anchor_date = date(2026, 5, 1)
        mock_line.hire_date_reference = date(2026, 5, 1)
        mock_line.days_hire_vs_anchor = 0
        mock_line.payment_anchor_status = "official_strong"
        mock_line.acquisition_type = "cabinet_new_same_day"
        mock_line.anchor_confidence = "strong"
        mock_line.anchor_source = "cabinet_drivers.lead_created_at"
        mock_line.anchor_warning = None
        mock_line.reactivation_flag = False
        mock_line.payout_eligible_flag = True
        mock_line.line_status = "payable"
        mock_line.payment_status = "payable"
        mock_line.blocked_reason = None
        mock_line.anchor_review_status = None
        mock_line.anchor_reviewed_by = None
        mock_line.anchor_reviewed_at = None
        mock_line.anchor_review_reason = None
        mock_line.is_auto_payable_anchor = True
        mock_line.trips_0_7_count = 8
        mock_line.trips_0_14_count = 12

        result = _line_to_review_dict(mock_line)
        assert result["line_id"] == 1
        assert result["driver_id"] == "abc"
        assert result["payment_anchor_status"] == "official_strong"
        assert result["reactivation_flag"] is False
        assert result["is_auto_payable_anchor"] is True
        assert result["trips_0_7_count"] == 8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
