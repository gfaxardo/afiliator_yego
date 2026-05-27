"""
Tests unitarios para lead_created_at_resolver.

NO requiere base de datos. Prueba la logica pura de resolucion.
"""
import pytest
from datetime import date

import sys
sys.path.insert(0, '.')
from app.services.lead_created_at_resolver import (
    resolve_lead_created_at,
    _safe_parse_date,
)


class TestSafeParseDate:
    def test_none(self):
        assert _safe_parse_date(None) is None

    def test_empty_string(self):
        assert _safe_parse_date("") is None
        assert _safe_parse_date("   ") is None

    def test_iso_naive(self):
        assert _safe_parse_date("2026-01-15T14:30:00") == date(2026, 1, 15)

    def test_iso_with_ms(self):
        assert _safe_parse_date("2026-01-15T14:30:00.123") == date(2026, 1, 15)

    def test_iso_with_tz(self):
        assert _safe_parse_date("2026-01-15T14:30:00+00:00") == date(2026, 1, 15)

    def test_iso_with_ms_and_tz(self):
        assert _safe_parse_date("2026-01-15T14:30:00.123+00:00") == date(2026, 1, 15)

    def test_space_separator(self):
        assert _safe_parse_date("2026-01-15 14:30:00") == date(2026, 1, 15)

    def test_date_only(self):
        assert _safe_parse_date("2026-01-15") == date(2026, 1, 15)

    def test_invalid(self):
        assert _safe_parse_date("not-a-date") is None

    def test_garbage_text(self):
        assert _safe_parse_date("helloworld") is None


class TestResolveLeadCreatedAt:
    """Tests for resolve_lead_created_at."""

    def test_cabinet_uses_cabinet_date(self):
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": "2026-04-24T15:34:35",
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] == "2026-04-24"
        assert result["lead_created_at_source"] == "lead_created_at_cabinet"
        assert result["lead_created_at_status"] == "resolved_by_origen"
        assert result["lead_created_at_warning"] is None

    def test_fleet_uses_fleet_date(self):
        result = resolve_lead_created_at({
            "origen": "fleet",
            "lead_created_at_cabinet": None,
            "lead_created_at_fleet": "2026-01-05T12:36:22.34+00:00",
        })
        assert result["lead_created_at_resolved"] == "2026-01-05"
        assert result["lead_created_at_source"] == "lead_created_at_fleet"
        assert result["lead_created_at_status"] == "resolved_by_origen"
        assert result["lead_created_at_warning"] is None

    def test_fleet_ignores_cabinet_date(self):
        result = resolve_lead_created_at({
            "origen": "fleet",
            "lead_created_at_cabinet": "2026-01-01T00:00:00",
            "lead_created_at_fleet": "2026-01-05T12:00:00",
        })
        assert result["lead_created_at_resolved"] == "2026-01-05"
        assert result["lead_created_at_source"] == "lead_created_at_fleet"
        assert result["lead_created_at_status"] == "resolved_by_origen"
        assert result["lead_created_at_warning"] == "both_dates_present"

    def test_cabinet_ignores_fleet_date(self):
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": "2026-04-24T15:34:35",
            "lead_created_at_fleet": "2026-01-05T12:00:00",
        })
        assert result["lead_created_at_resolved"] == "2026-04-24"
        assert result["lead_created_at_source"] == "lead_created_at_cabinet"
        assert result["lead_created_at_status"] == "resolved_by_origen"
        assert result["lead_created_at_warning"] == "both_dates_present"

    def test_unknown_origin_with_cabinet_date(self):
        result = resolve_lead_created_at({
            "origen": None,
            "lead_created_at_cabinet": "2026-04-24T15:34:35",
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] == "2026-04-24"
        assert result["lead_created_at_source"] == "lead_created_at_cabinet"
        assert result["lead_created_at_status"] == "resolved_by_available_date"
        assert result["lead_created_at_warning"] == "origin_unclear"

    def test_unknown_origin_with_fleet_date(self):
        result = resolve_lead_created_at({
            "origen": "",
            "lead_created_at_cabinet": None,
            "lead_created_at_fleet": "2026-01-05T12:00:00",
        })
        assert result["lead_created_at_resolved"] == "2026-01-05"
        assert result["lead_created_at_source"] == "lead_created_at_fleet"
        assert result["lead_created_at_status"] == "resolved_by_available_date"
        assert result["lead_created_at_warning"] == "origin_unclear"

    def test_no_dates_at_all(self):
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": None,
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] is None
        assert result["lead_created_at_source"] == "none"
        assert result["lead_created_at_status"] == "missing"
        assert result["lead_created_at_warning"] == "lead_created_at_missing"

    def test_invalid_date_format(self):
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": "not-a-valid-date-at-all",
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] is None
        assert result["lead_created_at_source"] == "none"
        assert result["lead_created_at_status"] == "invalid_date"
        assert result["lead_created_at_warning"] == "lead_created_at_invalid_format"

    def test_fleet_missing_date(self):
        result = resolve_lead_created_at({
            "origen": "fleet",
            "lead_created_at_cabinet": None,
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] is None
        assert result["lead_created_at_source"] == "none"
        assert result["lead_created_at_status"] == "missing"
        assert result["lead_created_at_warning"] == "lead_created_at_missing"

    def test_cabinet_missing_date(self):
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": None,
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] is None
        assert result["lead_created_at_source"] == "none"
        assert result["lead_created_at_status"] == "missing"
        assert result["lead_created_at_warning"] == "lead_created_at_missing"

    def test_unknown_origin_no_dates(self):
        result = resolve_lead_created_at({
            "origen": "unknown",
            "lead_created_at_cabinet": None,
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] is None
        assert result["lead_created_at_source"] == "none"
        assert result["lead_created_at_status"] == "missing"
        assert result["lead_created_at_warning"] == "lead_created_at_missing"

    def test_legacy_compat_field_not_needed(self):
        """Ensure the resolver does NOT read 'lead_created_at' singular field."""
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": "2026-04-24T15:34:35",
            "lead_created_at_fleet": None,
            "lead_created_at": "should-be-ignored",
        })
        assert result["lead_created_at_resolved"] == "2026-04-24"

    def test_fleet_date_only_date_format(self):
        result = resolve_lead_created_at({
            "origen": "fleet",
            "lead_created_at_cabinet": None,
            "lead_created_at_fleet": "2026-05-15",
        })
        assert result["lead_created_at_resolved"] == "2026-05-15"
        assert result["lead_created_at_source"] == "lead_created_at_fleet"
        assert result["lead_created_at_status"] == "resolved_by_origen"

    def test_cabinet_date_only_format(self):
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": "2026-04-24",
            "lead_created_at_fleet": None,
        })
        assert result["lead_created_at_resolved"] == "2026-04-24"
        assert result["lead_created_at_source"] == "lead_created_at_cabinet"

    def test_empty_strings_treated_as_none(self):
        result = resolve_lead_created_at({
            "origen": "cabinet",
            "lead_created_at_cabinet": "   ",
            "lead_created_at_fleet": "",
        })
        assert result["lead_created_at_resolved"] is None
        assert result["lead_created_at_status"] == "missing"
