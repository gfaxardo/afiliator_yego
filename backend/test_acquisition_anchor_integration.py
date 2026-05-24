"""
Tests de integracion Fase 2 — Acquisition-Aware Cutoff Engine.

NO requiere base de datos. Prueba la integracion del anchor en el flujo.
"""
import pytest
import sys
sys.path.insert(0, '.')
from datetime import date, datetime
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.acquisition_anchor_service import (
    resolve_acquisition_anchor,
    _safe_date,
    _resolve_cabinet,
    _resolve_fleet,
)


class TestAnchorIntegration:
    """Test que el anchor se resuelve correctamente para todos los escenarios de cutoff."""

    def test_cabinet_with_lca_gets_strong_anchor(self):
        """Cabinet con lead_created_at → anchor fuerte."""
        row = {"driver_id": "d1", "origen": "cabinet",
               "lead_created_at": "2026-03-01T10:00:00",
               "hire_date": "2026-03-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        assert result["anchor_confidence"] == "strong"
        assert result["anchor_source"] == "cabinet_drivers.lead_created_at"
        assert result["acquisition_type"] == "cabinet_new_same_day"

    def test_cabinet_reactivated_gets_flag(self):
        """Cabinet reactivado (lca > hd) → reactivation_flag=true."""
        row = {"driver_id": "d2", "origen": "cabinet",
               "lead_created_at": "2026-04-01T10:00:00",
               "hire_date": "2025-09-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        assert result["reactivation_flag"] is True
        assert result["acquisition_type"] == "cabinet_reactivated_existing_driver"

    def test_cabinet_delayed_conversion(self):
        """Cabinet delayed (lca < hd) → no reactivation."""
        row = {"driver_id": "d3", "origen": "cabinet",
               "lead_created_at": "2026-01-05T10:00:00",
               "hire_date": "2026-01-15", "created_at": None}
        result = resolve_acquisition_anchor(row)
        assert result["reactivation_flag"] is False
        assert result["acquisition_type"] == "cabinet_delayed_conversion"

    def test_cabinet_no_lca_gets_fallback(self):
        """Cabinet sin lead_created_at → fallback medium."""
        row = {"driver_id": "d4", "origen": "cabinet",
               "lead_created_at": None,
               "hire_date": "2026-02-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        assert result["anchor_confidence"] == "medium"
        assert "hire_date" in result["anchor_source"]

    def test_cabinet_no_lca_no_hd_gets_weak(self):
        """Cabinet sin LCA ni hire_date → fallback weak (created_at)."""
        row = {"driver_id": "d5", "origen": "cabinet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        result = resolve_acquisition_anchor(row)
        assert result["anchor_confidence"] == "weak"
        assert "created_at" in result["anchor_source"]

    def test_fleet_gets_strong_drivers_hd(self):
        """Fleet con drivers.hire_date → anchor strong."""
        row = {"driver_id": "f1", "origen": "fleet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        drivers_data = {"hire_date": date(2026, 2, 1)}
        result = resolve_acquisition_anchor(row, drivers_data=drivers_data)
        assert result["anchor_confidence"] == "strong"
        assert result["anchor_source"] == "drivers.hire_date"
        assert result["acquisition_type"] == "fleet_migration"

    def test_anchor_warnings_generated(self):
        """Verifica que se generan warnings segun confianza."""
        # Weak anchor
        row = {"driver_id": "w1", "origen": "cabinet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        result = resolve_acquisition_anchor(row)
        assert result["anchor_warning"] is not None

        # Strong anchor - no warning in service (warnings added in engine layer)
        row2 = {"driver_id": "w2", "origen": "cabinet",
                "lead_created_at": "2026-03-01T10:00:00",
                "hire_date": "2026-03-01", "created_at": None}
        result2 = resolve_acquisition_anchor(row2)
        assert result2["anchor_warning"] is None  # Service doesn't add warnings

    def test_days_hire_vs_anchor_computed(self):
        """Verifica que days_hire_vs_anchor se calcula correctamente."""
        # Same day
        row = {"driver_id": "g1", "origen": "cabinet",
               "lead_created_at": "2026-03-15T10:00:00",
               "hire_date": "2026-03-15", "created_at": None}
        result = resolve_acquisition_anchor(row)
        assert result["days_hire_vs_anchor"] == 0

        # Gap of 10 days
        row2 = {"driver_id": "g2", "origen": "cabinet",
                "lead_created_at": "2026-03-05T10:00:00",
                "hire_date": "2026-03-15", "created_at": None}
        result2 = resolve_acquisition_anchor(row2)
        assert result2["days_hire_vs_anchor"] == 10

        # Inverted (reactivation): hire before lca by 150 days
        row3 = {"driver_id": "g3", "origen": "cabinet",
                "lead_created_at": "2026-05-01T10:00:00",
                "hire_date": "2025-12-01", "created_at": None}
        result3 = resolve_acquisition_anchor(row3)
        assert result3["days_hire_vs_anchor"] < 0


class TestFallbackPriority:
    """Verifica el orden de prioridad de fallbacks."""

    def test_cabinet_lca_always_first(self):
        """Si LCA existe, siempre se usa primero."""
        row = {"driver_id": "p1", "origen": "cabinet",
               "lead_created_at": "2026-01-01T10:00:00",
               "hire_date": "2026-02-01", "created_at": datetime(2026, 5, 1)}
        drivers = {"hire_date": date(2026, 3, 1)}
        leads = {"lead_created_at": datetime(2026, 4, 1)}

        result = resolve_acquisition_anchor(row, drivers_data=drivers, leads_data=leads)
        assert result["anchor_source"] == "cabinet_drivers.lead_created_at"
        assert "2026-01-01" in result["acquisition_anchor_date"]

    def test_cabinet_leads_fallback_before_drivers_hd(self):
        """Leads LCA se prefiere sobre drivers.hire_date."""
        row = {"driver_id": "p2", "origen": "cabinet",
               "lead_created_at": None,
               "hire_date": None, "created_at": None}
        drivers = {"hire_date": date(2026, 3, 1)}
        leads = {"lead_created_at": datetime(2026, 2, 1)}
        result = resolve_acquisition_anchor(row, drivers_data=drivers, leads_data=leads)
        assert result["anchor_source"] == "cabinet_leads.lead_created_at"
        assert result["anchor_confidence"] == "medium"

    def test_drivers_hd_before_cabinet_hd(self):
        """drivers.hire_date se prefiere sobre cabinet_drivers.hire_date."""
        row = {"driver_id": "p3", "origen": "cabinet",
               "lead_created_at": None,
               "hire_date": "2026-04-01", "created_at": None}
        drivers = {"hire_date": date(2026, 3, 1)}
        result = resolve_acquisition_anchor(row, drivers_data=drivers)
        assert result["anchor_source"] == "drivers.hire_date"

    def test_fleet_priority(self):
        """Fleet: drivers.hd > cabinet.hd > created_at."""
        # drivers.hd available
        r1 = _resolve_fleet(None, date(2026, 5, 15), date(2026, 3, 1))
        assert r1[1] == "drivers.hire_date"
        assert r1[2] == "strong"

        # no drivers.hd, has cabinet.hd
        r2 = _resolve_fleet(date(2026, 4, 1), date(2026, 5, 15), None)
        assert r2[1] == "cabinet_drivers.hire_date"
        assert r2[2] == "medium"

        # no hd at all, only created_at
        r3 = _resolve_fleet(None, date(2026, 5, 15), None)
        assert r3[1] == "cabinet_drivers.created_at"
        assert r3[2] == "weak"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
