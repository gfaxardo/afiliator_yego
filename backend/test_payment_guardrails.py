"""
Tests Fase 2A.2 — Payment Anchor Guardrails.
Verifica que cabinet sin lead_created_at oficial NO sea auto-payable.
"""
import pytest
import sys
sys.path.insert(0, '.')
from datetime import date, datetime

from app.services.acquisition_anchor_service import (
    resolve_acquisition_anchor,
    resolve_payment_anchor_status,
)


class TestPaymentAnchorStatus:
    """Verifica la clasificacion de payment_anchor_status."""

    def test_cabinet_official_strong(self):
        """Cabinet con lead_created_at oficial = official_strong + auto-payable."""
        row = {"driver_id": "c1", "origen": "cabinet",
               "lead_created_at_cabinet": "2026-03-01T10:00:00",
               "hire_date": "2026-03-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert pay["payment_anchor_status"] == "official_strong"
        assert pay["is_auto_payable_anchor"] is True
        assert pay["anchor_payment_block_reason"] is None

    def test_cabinet_official_medium_leads(self):
        """Cabinet con LCA recuperado de leads = official_medium + auto-payable."""
        row = {"driver_id": "c2", "origen": "cabinet",
               "lead_created_at": None,
               "hire_date": "2026-02-10", "created_at": None}
        leads_data = {"lead_created_at": datetime(2026, 2, 8, 12, 0, 0)}
        result = resolve_acquisition_anchor(row, leads_data=leads_data)
        pay = resolve_payment_anchor_status(result)
        assert pay["payment_anchor_status"] == "official_medium"
        assert pay["is_auto_payable_anchor"] is True

    def test_cabinet_fallback_not_auto_payable(self):
        """Cabinet sin LCA usando hire_date fallback = NO auto-payable."""
        row = {"driver_id": "c3", "origen": "cabinet",
               "lead_created_at": None,
               "hire_date": "2026-04-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert pay["payment_anchor_status"] == "fallback_operational_only"
        assert pay["is_auto_payable_anchor"] is False
        assert pay["anchor_payment_block_reason"] is not None
        assert "sin lead_created_at" in pay["anchor_payment_block_reason"].lower()

    def test_cabinet_created_at_fallback_not_auto_payable(self):
        """Cabinet con ETL created_at = fallback + NO auto-payable."""
        row = {"driver_id": "c4", "origen": "cabinet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert pay["is_auto_payable_anchor"] is False
        assert "fallback" in pay["payment_anchor_status"].lower()

    def test_fleet_official_hire_date(self):
        """Fleet con drivers.hire_date = fleet_official + auto-payable."""
        row = {"driver_id": "f1", "origen": "fleet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        drivers = {"hire_date": date(2026, 2, 1)}
        result = resolve_acquisition_anchor(row, drivers_data=drivers)
        pay = resolve_payment_anchor_status(result)
        assert pay["payment_anchor_status"] == "fleet_official_hire_date"
        assert pay["is_auto_payable_anchor"] is True

    def test_fleet_fallback_not_auto_payable(self):
        """Fleet con created_at = fleet_fallback + NO auto-payable."""
        row = {"driver_id": "f2", "origen": "fleet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert pay["payment_anchor_status"] == "fleet_fallback"
        assert pay["is_auto_payable_anchor"] is False

    def test_reported_pending_validation(self):
        """Cabinet con reported_anchor_date = reported_pending_validation."""
        row = {"driver_id": "r1", "origen": "cabinet",
               "lead_created_at": None,
               "hire_date": None, "created_at": datetime(2026, 5, 15)}
        result = resolve_acquisition_anchor(row)
        # Simulate reported_anchor_date being set
        result["reported_anchor_date"] = "2026-03-15"
        pay = resolve_payment_anchor_status(result)
        assert pay["payment_anchor_status"] == "reported_pending_validation"
        assert pay["is_auto_payable_anchor"] is False
        assert "validacion" in (pay["anchor_payment_block_reason"] or "").lower()

    def test_blocked_missing_official_anchor(self):
        """Sin ninguna fecha = blocked_missing_official_anchor."""
        row = {"driver_id": "b1", "origen": "cabinet",
               "lead_created_at": None, "hire_date": None,
               "created_at": None}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert pay["payment_anchor_status"] == "blocked_missing_official_anchor"
        assert pay["is_auto_payable_anchor"] is False


class TestPaymentGuardrailIntegration:
    """Verifica que la resolucion completa produce estados correctos."""

    def test_cabinet_new_driver_auto_payable(self):
        """Driver cabinet nuevo con LCA = official_strong, auto-payable."""
        row = {"driver_id": "n1", "origen": "cabinet",
               "lead_created_at_cabinet": "2026-01-15T10:00:00",
               "hire_date": "2026-01-15", "created_at": None}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert result["anchor_confidence"] == "strong"
        assert pay["is_auto_payable_anchor"] is True
        assert result["reactivation_flag"] is False

    def test_cabinet_reactivated_still_auto_payable(self):
        """Reactivado con LCA sigue siendo auto-payable (tiene LCA oficial)."""
        row = {"driver_id": "r2", "origen": "cabinet",
               "lead_created_at_cabinet": "2026-04-01T10:00:00",
               "hire_date": "2025-09-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert result["reactivation_flag"] is True
        # Reactivated with official LCA is still auto-payable
        assert pay["is_auto_payable_anchor"] is True
        assert pay["payment_anchor_status"] == "official_strong"

    def test_cabinet_without_lca_blocked(self):
        """Driver sin LCA usando hire_date fallback = NO auto-payable."""
        row = {"driver_id": "x1", "origen": "cabinet",
               "lead_created_at": None,
               "hire_date": "2026-03-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert pay["is_auto_payable_anchor"] is False
        assert "operational_only" in pay["payment_anchor_status"] or "fallback" in pay["payment_anchor_status"]

    def test_fleet_fallback_blocked(self):
        """Fleet sin hire_date = fleet_fallback, NO auto-payable."""
        row = {"driver_id": "f3", "origen": "fleet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        result = resolve_acquisition_anchor(row)
        pay = resolve_payment_anchor_status(result)
        assert pay["is_auto_payable_anchor"] is False
        assert "Fleet sin hire_date" in (pay["anchor_payment_block_reason"] or "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
