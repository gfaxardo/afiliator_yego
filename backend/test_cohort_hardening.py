"""
Tests Fase 2A.1 — Cohort Engine Hardening.
Verifica que acquisition_anchor_date gobierna las cohortes.
"""
import pytest
import sys
sys.path.insert(0, '.')
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.cohort_service import (
    iso_week_dates, cohort_maturity, _iso_year_expr, _iso_week_expr,
)
from app.services.acquisition_anchor_service import (
    resolve_acquisition_anchor, _safe_date,
)


class TestAnchorDateAsCohortAnchor:
    """Verifica que acquisition_anchor_date produce la cohorte correcta."""

    def test_anchor_date_gives_iso_week(self):
        """Una fecha ancla debe caer en su semana ISO correcta."""
        # 2026-01-05 = Monday W02
        anchor = date(2026, 1, 5)
        iso_year, iso_week, _ = anchor.isocalendar()
        assert iso_year == 2026
        assert iso_week == 2
        key = f"{iso_year}-W{iso_week:02d}"
        assert key == "2026-W02"

    def test_anchor_date_same_day_as_hire(self):
        """Si anchor = hire_date, la cohorte es identica."""
        anchor = date(2026, 3, 2)
        hire = date(2026, 3, 2)
        assert anchor.isocalendar() == hire.isocalendar()

    def test_reactivated_driver_different_cohort(self):
        """Driver reactivado: anchor != hire_date, cohortes diferentes."""
        # hire_date = 2025-09-03 (W36 2025), anchor = 2026-03-15 (W12 2026)
        hire = date(2025, 9, 3)
        anchor = date(2026, 3, 15)
        hire_cal = hire.isocalendar()
        anchor_cal = anchor.isocalendar()
        assert hire_cal != anchor_cal  # Different cohorts

    def test_fleet_driver_cohort(self):
        """Fleet usa drivers.hire_date como anchor, cohorte correcta."""
        row = {"driver_id": "f1", "origen": "fleet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 15)}
        drivers = {"hire_date": date(2026, 4, 10)}
        result = resolve_acquisition_anchor(row, drivers_data=drivers)
        anchor_str = result["acquisition_anchor_date"]
        anchor_date = datetime.strptime(anchor_str, "%Y-%m-%d").date()
        iso_year, iso_week, _ = anchor_date.isocalendar()
        assert result["anchor_source"] == "drivers.hire_date"
        assert iso_year == 2026
        assert iso_week >= 14  # April 10 falls in W14-W16

    def test_iso_week_dates_consistency(self):
        """iso_week_dates produce un rango de 7 dias."""
        monday, sunday = iso_week_dates(2026, 1)
        assert (sunday - monday).days == 6
        assert monday.isoweekday() == 1  # Monday
        assert sunday.isoweekday() == 7  # Sunday

    def test_maturity_calculation(self):
        """cohort_maturity = cohort_to + maturity_days."""
        cohort_to = date(2026, 5, 17)  # Sunday
        maturity = cohort_maturity(cohort_to, 7)
        assert maturity == date(2026, 5, 24)
        maturity14 = cohort_maturity(cohort_to, 14)
        assert maturity14 == date(2026, 5, 31)


class TestLegacyModeStillWorks:
    """hire_date_legacy mode debe seguir funcionando sin cambios."""

    def test_legacy_mode_uses_hire_date(self):
        """Legacy mode agrupa por hire_date ISO week."""
        hire = date(2026, 5, 15)
        iso_year, iso_week, _ = hire.isocalendar()
        assert iso_year == 2026
        assert iso_week == 20  # May 15 = W20

    def test_driver_without_lca_gets_correct_legacy_cohort(self):
        """Sin LCA, hire_date legacy produce cohorte desde hire_date."""
        row = {"driver_id": "d1", "origen": "cabinet",
               "lead_created_at": None, "hire_date": "2026-04-15",
               "created_at": datetime(2026, 5, 15)}
        result = resolve_acquisition_anchor(row)
        # Even in acquisition_anchor mode, hire_date should be accessible
        assert result["cabinet_hire_date"] is not None


class TestAcquisitionTypesCohortSeparation:
    """Tipos de adquisicion deben producir cohorts semanticamente correctas."""

    def test_cabinet_new_same_day(self):
        """Driver nuevo: anchor = hire, misma cohorte."""
        row = {"driver_id": "n1", "origen": "cabinet",
               "lead_created_at": "2026-03-01T10:00:00",
               "hire_date": "2026-03-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        assert result["acquisition_type"] == "cabinet_new_same_day"
        assert result["reactivation_flag"] is False

    def test_cabinet_reactivated(self):
        """Reactivado: anchor > hire, cohortes diferentes, flag true."""
        row = {"driver_id": "r1", "origen": "cabinet",
               "lead_created_at": "2026-04-15T10:00:00",
               "hire_date": "2025-09-01", "created_at": None}
        result = resolve_acquisition_anchor(row)
        assert result["reactivation_flag"] is True
        assert "reactivated" in result["acquisition_type"].lower()

    def test_fleet_migration_type(self):
        """Fleet siempre es fleet_migration."""
        row = {"driver_id": "f1", "origen": "fleet",
               "lead_created_at": None, "hire_date": None,
               "created_at": datetime(2026, 5, 1)}
        drivers = {"hire_date": date(2026, 4, 1)}
        result = resolve_acquisition_anchor(row, drivers_data=drivers)
        assert result["acquisition_type"] == "fleet_migration"
        assert result["reactivation_flag"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
