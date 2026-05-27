"""
Tests unitarios para Acquisition Anchor Service (Fase 1).

NO requiere base de datos. Prueba la lógica pura de resolución de anchor.
"""
import pytest
from datetime import date, datetime


# Import the service functions directly
import sys
sys.path.insert(0, '.')
from app.services.acquisition_anchor_service import (
    resolve_acquisition_anchor,
    _safe_date,
    _resolve_fleet,
    _resolve_cabinet,
)


class TestSafeDate:
    """Test _safe_date parsing."""
    def test_none(self):
        assert _safe_date(None) is None

    def test_empty_string(self):
        assert _safe_date("") is None
        assert _safe_date("   ") is None

    def test_date_object(self):
        d = date(2026, 1, 15)
        assert _safe_date(d) == d

    def test_datetime_object(self):
        dt = datetime(2026, 1, 15, 12, 30, 0)
        assert _safe_date(dt) == date(2026, 1, 15)

    def test_iso_format(self):
        assert _safe_date("2026-01-15T14:30:00") == date(2026, 1, 15)

    def test_yyyy_mm_dd(self):
        assert _safe_date("2026-01-15") == date(2026, 1, 15)

    def test_invalid_string(self):
        assert _safe_date("not-a-date") is None


class TestResolveFleet:
    """Test fleet anchor resolution."""
    def test_fleet_with_drivers_hire_date(self):
        result = _resolve_fleet(None, None, date(2026, 2, 1))
        assert result[0] == date(2026, 2, 1)
        assert result[1] == "drivers.hire_date"
        assert result[2] == "strong"
        assert result[3] is None

    def test_fleet_with_cabinet_hire_date_fallback(self):
        result = _resolve_fleet(date(2026, 1, 15), None, None)
        assert result[0] == date(2026, 1, 15)
        assert result[1] == "cabinet_drivers.hire_date"
        assert result[2] == "medium"
        assert result[3] is not None

    def test_fleet_with_created_at_fallback(self):
        result = _resolve_fleet(None, date(2026, 3, 1), None)
        assert result[0] == date(2026, 3, 1)
        assert result[1] == "cabinet_drivers.created_at"
        assert result[2] == "weak"
        assert result[3] is not None

    def test_fleet_no_data(self):
        result = _resolve_fleet(None, None, None)
        assert result[0] is None
        assert result[1] == "none"
        assert result[2] == "none"


class TestResolveCabinet:
    """Test cabinet anchor resolution."""
    def test_cabinet_with_lca(self):
        result = _resolve_cabinet(
            lca=date(2026, 1, 10),
            cabinet_hd=date(2026, 1, 10),
            cabinet_ca=None,
            drivers_hd=None,
            leads_lca=None,
        )
        assert result[0] == date(2026, 1, 10)
        assert result[1] == "cabinet_drivers.lead_created_at"
        assert result[2] == "strong"
        assert result[4] == "cabinet_new_same_day"  # acquisition_type
        assert result[5] is False  # reactivation_flag

    def test_cabinet_lca_delayed_conversion(self):
        """lca before hire_date = delayed conversion"""
        result = _resolve_cabinet(
            lca=date(2026, 1, 5),
            cabinet_hd=date(2026, 1, 15),
            cabinet_ca=None,
            drivers_hd=None,
            leads_lca=None,
        )
        assert result[0] == date(2026, 1, 5)
        assert result[4] == "cabinet_delayed_conversion"
        assert result[5] is False

    def test_cabinet_lca_reactivated(self):
        """lca after hire_date = reactivated existing driver"""
        result = _resolve_cabinet(
            lca=date(2026, 3, 1),
            cabinet_hd=date(2025, 9, 1),
            cabinet_ca=None,
            drivers_hd=None,
            leads_lca=None,
        )
        assert result[0] == date(2026, 3, 1)
        assert result[4] == "cabinet_reactivated_existing_driver"
        assert result[5] is True

    def test_cabinet_leads_fallback(self):
        """No LCA in cabinet, but available in leads."""
        result = _resolve_cabinet(
            lca=None,
            cabinet_hd=date(2026, 2, 10),
            cabinet_ca=None,
            drivers_hd=None,
            leads_lca=date(2026, 2, 8),
        )
        assert result[0] == date(2026, 2, 8)
        assert result[1] == "cabinet_leads.lead_created_at"
        assert result[2] == "medium"

    def test_cabinet_drivers_hire_date_fallback(self):
        """No LCA, no leads, but drivers.hire_date available."""
        result = _resolve_cabinet(
            lca=None,
            cabinet_hd=None,
            cabinet_ca=None,
            drivers_hd=date(2026, 3, 1),
            leads_lca=None,
        )
        assert result[0] == date(2026, 3, 1)
        assert result[1] == "drivers.hire_date"
        assert result[2] == "medium"

    def test_cabinet_cabinet_hire_date_fallback(self):
        """No LCA, no leads, no drivers.hire_date, but cabinet.hire_date exists."""
        result = _resolve_cabinet(
            lca=None,
            cabinet_hd=date(2026, 4, 1),
            cabinet_ca=None,
            drivers_hd=None,
            leads_lca=None,
        )
        assert result[0] == date(2026, 4, 1)
        assert result[1] == "cabinet_drivers.hire_date"
        assert result[2] == "medium"

    def test_cabinet_created_at_last_resort(self):
        """Only created_at available."""
        result = _resolve_cabinet(
            lca=None,
            cabinet_hd=None,
            cabinet_ca=date(2026, 5, 15),
            drivers_hd=None,
            leads_lca=None,
        )
        assert result[0] == date(2026, 5, 15)
        assert result[1] == "cabinet_drivers.created_at"
        assert result[2] == "weak"

    def test_cabinet_no_data(self):
        """Absolutely no dates."""
        result = _resolve_cabinet(None, None, None, None, None)
        assert result[0] is None
        assert result[1] == "none"


class TestResolveAcquisitionAnchor:
    """Test the full resolve function."""
    def test_cabinet_with_lca_complete(self):
        row = {
            "driver_id": "abc123",
            "origen": "cabinet",
            "lead_created_at_cabinet": "2026-01-10T14:30:00",
            "lead_created_at_fleet": None,
            "hire_date": "2026-01-10",
            "created_at": datetime(2026, 5, 15),
        }
        result = resolve_acquisition_anchor(row)
        assert result["driver_id"] == "abc123"
        assert result["origen"] == "cabinet"
        assert result["acquisition_anchor_date"] == "2026-01-10"
        assert result["anchor_source"] == "cabinet_drivers.lead_created_at"
        assert result["anchor_confidence"] == "strong"
        assert result["acquisition_type"] == "cabinet_new_same_day"
        assert result["reactivation_flag"] is False
        assert result["days_hire_vs_anchor"] == 0

    def test_cabinet_reactivation(self):
        row = {
            "driver_id": "xyz789",
            "origen": "cabinet",
            "lead_created_at_cabinet": "2026-03-15T10:00:00",
            "lead_created_at_fleet": None,
            "hire_date": "2025-09-01",
            "created_at": datetime(2026, 5, 15),
        }
        result = resolve_acquisition_anchor(row)
        assert result["acquisition_type"] == "cabinet_reactivated_existing_driver"
        assert result["reactivation_flag"] is True
        assert result["days_hire_vs_anchor"] < 0  # hire was BEFORE anchor

    def test_fleet_with_drivers_data(self):
        row = {
            "driver_id": "fleet001",
            "origen": "fleet",
            "lead_created_at": None,
            "hire_date": None,
            "created_at": datetime(2026, 5, 15),
        }
        drivers_data = {"hire_date": date(2026, 2, 1)}
        result = resolve_acquisition_anchor(row, drivers_data=drivers_data)
        assert result["acquisition_anchor_date"] == "2026-02-01"
        assert result["anchor_source"] == "drivers.hire_date"
        assert result["anchor_confidence"] == "strong"
        assert result["acquisition_type"] == "fleet_migration"

    def test_leads_fallback(self):
        row = {
            "driver_id": "cab_no_lca",
            "origen": "cabinet",
            "lead_created_at": None,
            "hire_date": "2026-02-10",
            "created_at": datetime(2026, 5, 15),
        }
        leads_data = {"lead_created_at": datetime(2026, 2, 8, 12, 0, 0)}
        result = resolve_acquisition_anchor(row, leads_data=leads_data)
        assert result["anchor_source"] == "cabinet_leads.lead_created_at"
        assert result["anchor_confidence"] == "medium"
        assert result["anchor_warning"] is not None

    def test_weak_fallback(self):
        """Only created_at available."""
        row = {
            "driver_id": "no_dates",
            "origen": "cabinet",
            "lead_created_at": None,
            "hire_date": None,
            "created_at": datetime(2026, 5, 15, 12, 0, 0),
        }
        result = resolve_acquisition_anchor(row)
        assert result["anchor_source"] == "cabinet_drivers.created_at"
        assert result["anchor_confidence"] == "weak"
        assert result["acquisition_type"] == "cabinet_unknown_no_lca"

    def test_multiple_lead_candidates_not_used(self):
        """leads_data should come pre-matched as single. The service trusts the caller."""
        row = {
            "driver_id": "test",
            "origen": "cabinet",
            "lead_created_at": None,
            "hire_date": None,
            "created_at": datetime(2026, 5, 15),
        }
        # leads_data is None = no lead match found (caller's responsibility to only pass unique)
        result = resolve_acquisition_anchor(row, leads_data=None)
        assert result["anchor_source"] != "cabinet_leads.lead_created_at"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
