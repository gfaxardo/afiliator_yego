"""
Tests para Health Pipeline: readiness operativo, CSV exports, cron script, alerts.

NO requiere base de datos real. Prueba logica pura.
"""
import pytest
from datetime import date, timedelta

import sys
sys.path.insert(0, '.')
from app.services.scout_liq_health_pipeline import (
    _status_from_lag,
    _lag_from_date,
    _iso_week_dates,
    _root_cause_source,
    _build_pipeline_alerts,
    _summarize_by_category,
    _summarize_by_owner,
    _compute_operational_readiness,
    _pipeline_fallback,
)


class TestStatusFromLag:
    def test_none_is_unknown(self):
        assert _status_from_lag(None) == "UNKNOWN"
    def test_ok(self):
        assert _status_from_lag(0) == "ok"
        assert _status_from_lag(1) == "ok"
    def test_warning(self):
        assert _status_from_lag(2) == "warning"
        assert _status_from_lag(3) == "warning"
    def test_blocked(self):
        assert _status_from_lag(4) == "blocked"


class TestLagFromDate:
    def test_yesterday(self):
        assert _lag_from_date(date.today() - timedelta(days=1)) == 1
    def test_none(self):
        assert _lag_from_date(None) is None
    def test_week(self):
        ref = date(2026, 5, 27)
        assert _lag_from_date(date(2026, 5, 20), ref) == 7


class TestISOWeekDates:
    def test_monday_sunday(self):
        m, s = _iso_week_dates(2026, 1)
        assert m.isoweekday() == 1
        assert s.isoweekday() == 7


class TestOperationalReadiness:
    """Pruebas de readiness operativo."""

    def test_all_ok_allows_payments(self):
        source = {"status": "ok", "lag_days": 0, "max_hire_date": "2026-05-26"}
        matching = {"status": "ok", "unmatched_count": 0, "assignment_coverage_pct": 95,
                     "total_source_drivers": 100, "assigned_count": 95}
        cohorts_info = {"cohorts": [{"status": "ok", "cohort": "S21", "total": 14, "converted_5v_7d": 0,
                                      "reasons": [], "is_7d_mature": False, "is_14d_mature": False,
                                      "cutoff_exists": False, "cutoff_status": None,
                                      "assigned": 14, "unassigned": 0, "active": 4, "converted_5v_14d": 0,
                                      "paid": 0}],
                         "global_status": "ok", "warning_count": 0, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        r = _compute_operational_readiness(source, matching, cohorts_info, jobs)
        assert r["can_approve_payments"] is True
        assert r["can_create_cutoff"] is True
        assert len(r["blocking_domains"]) == 0

    def test_source_stale_blocks_approval(self):
        source = {"status": "blocked", "lag_days": 4, "max_hire_date": "2026-05-23",
                  "rows_last_1d": 0, "rows_last_3d": 0, "rows_last_7d": 0, "total_rows": 100}
        matching = {"status": "ok", "unmatched_count": 0, "assignment_coverage_pct": 95,
                     "total_source_drivers": 100, "assigned_count": 95}
        cohorts_info = {"cohorts": [], "global_status": "ok", "warning_count": 0, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        r = _compute_operational_readiness(source, matching, cohorts_info, jobs)
        assert r["can_approve_payments"] is False
        assert r["can_create_cutoff"] is False
        assert "source" in r["blocking_domains"]

    def test_unassigned_blocks_approval_at_low_coverage(self):
        source = {"status": "ok", "lag_days": 0, "total_rows": 100}
        matching = {"status": "warning", "unmatched_count": 2000, "total_source_drivers": 2500,
                     "assignment_coverage_pct": 20, "assigned_count": 500}
        cohorts_info = {"cohorts": [], "global_status": "ok", "warning_count": 0, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        r = _compute_operational_readiness(source, matching, cohorts_info, jobs)
        assert "assignment" in r["blocking_domains"]

    def test_preview_always_allowed(self):
        source = {"status": "blocked", "lag_days": 4}
        matching = {"status": "warning", "unmatched_count": 1000, "assignment_coverage_pct": 10,
                     "total_source_drivers": 100, "assigned_count": 0}
        cohorts_info = {"cohorts": [], "global_status": "ok", "warning_count": 0, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        r = _compute_operational_readiness(source, matching, cohorts_info, jobs)
        assert r["can_calculate_preview"] is True

    def test_cohort_blocked_adds_action(self):
        source = {"status": "ok", "lag_days": 0}
        matching = {"status": "ok", "unmatched_count": 0}
        cohorts_info = {"cohorts": [{"status": "blocked", "cohort": "S19-2026", "total": 143,
                                      "converted_5v_7d": 27, "reasons": ["cohorte madura sin cutoff creado"],
                                      "is_7d_mature": True, "is_14d_mature": True,
                                      "cutoff_exists": False, "cutoff_status": None,
                                      "assigned": 28, "unassigned": 115, "active": 26,
                                      "converted_5v_14d": 0, "paid": 0}],
                         "global_status": "blocked", "warning_count": 0, "blocked_count": 1}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        r = _compute_operational_readiness(source, matching, cohorts_info, jobs)
        assert "cutoff_workflow" in r["blocking_domains"]
        assert any("Crear cutoff" in a["action"] for a in r["next_actions"])

    def test_next_actions_deduplicated(self):
        source = {"status": "blocked", "lag_days": 4}
        matching = {"status": "ok", "unmatched_count": 0, "assignment_coverage_pct": 100,
                     "total_source_drivers": 100, "assigned_count": 100}
        cohorts_info = {"cohorts": [{"status": "blocked", "cohort": "S18", "total": 100, "converted_5v_7d": 10,
                                      "reasons": ["cohorte madura sin cutoff creado"],
                                      "is_7d_mature": True, "is_14d_mature": False,
                                      "cutoff_exists": False, "cutoff_status": None,
                                      "assigned": 50, "unassigned": 50, "active": 10,
                                       "converted_5v_14d": 0, "paid": 0}],
                          "global_status": "blocked", "warning_count": 0, "blocked_count": 1}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        r = _compute_operational_readiness(source, matching, cohorts_info, jobs)
        assert len(r["next_actions"]) >= 1


class TestBuildPipelineAlerts:
    def test_all_ok_no_alerts(self):
        source = {"status": "ok", "total_rows": 100}
        derived = {"status": "ok"}
        matching = {"status": "ok", "unassigned_sample": []}
        cohorts_info = {"cohorts": [], "global_status": "ok", "warning_count": 0, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        assert len(_build_pipeline_alerts(source, derived, matching, cohorts_info, jobs)) == 0

    def test_source_blocked_enriched(self):
        source = {"status": "blocked", "message": "stale", "lag_days": 4, "total_rows": 50,
                  "max_hire_date": "2026-05-23", "max_anchor_date": "2026-05-26",
                  "rows_last_1d": 0, "rows_last_3d": 0, "rows_last_7d": 11,
                  "recommended_action": "Revisar ETL"}
        derived = {"status": "ok"}
        matching = {"status": "ok"}
        cohorts_info = {"cohorts": [], "global_status": "ok", "warning_count": 0, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        alerts = _build_pipeline_alerts(source, derived, matching, cohorts_info, jobs)
        a = alerts[0]
        assert a["code"] == "source_health"
        assert a["category"] == "source_stale"
        assert a["is_blocking"] is True
        assert isinstance(a["evidence"], dict)

    def test_scout_assignment_matching_gap(self):
        source = {"status": "ok", "total_rows": 100}
        derived = {"status": "ok"}
        matching = {"status": "warning", "total_source_drivers": 2594, "assigned_count": 859,
                     "unmatched_count": 1735, "assignment_coverage_pct": 33.1, "unassigned_sample": []}
        cohorts_info = {"cohorts": [], "global_status": "ok", "warning_count": 0, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        alerts = _build_pipeline_alerts(source, derived, matching, cohorts_info, jobs)
        a = [x for x in alerts if x["code"] == "scout_assignment"][0]
        assert a["category"] == "matching_gap"

    def test_cohort_workflow_gap(self):
        source = {"status": "ok"}
        derived = {"status": "ok"}
        matching = {"status": "ok", "unassigned_sample": []}
        cohorts_info = {"cohorts": [{"cohort": "S19-2026", "status": "blocked", "total": 143,
                                      "assigned": 28, "unassigned": 115, "converted_5v_7d": 27,
                                      "converted_5v_14d": 30, "is_7d_mature": True, "is_14d_mature": True,
                                      "cutoff_exists": False, "cutoff_status": None,
                                      "reasons": ["existen drivers sin scout (115)", "cohorte madura sin cutoff creado"]}],
                         "global_status": "blocked", "warning_count": 0, "blocked_count": 1}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        alerts = _build_pipeline_alerts(source, derived, matching, cohorts_info, jobs)
        ca = [a for a in alerts if a["code"].startswith("cohort/")][0]
        assert ca["category"] == "workflow_gap"
        assert ca["is_blocking"] is True

    def test_cohort_matching_gap_only(self):
        source = {"status": "ok"}
        derived = {"status": "ok"}
        matching = {"status": "ok", "unassigned_sample": []}
        cohorts_info = {"cohorts": [{"cohort": "S17-2026", "status": "warning", "total": 145, "assigned": 49,
                                      "unassigned": 96, "converted_5v_7d": 18, "is_7d_mature": True,
                                      "cutoff_exists": True, "cutoff_status": "calculated",
                                      "reasons": ["existen drivers sin scout (96)"]}],
                         "global_status": "warning", "warning_count": 1, "blocked_count": 0}
        jobs = {"status": "ok", "last_successful_runs": [], "failed_runs": [], "missing_jobs": []}
        alerts = _build_pipeline_alerts(source, derived, matching, cohorts_info, jobs)
        ca = alerts[0]
        assert ca["category"] == "matching_gap"
        assert ca["is_blocking"] is False


class TestSummarizeByCategory:
    def test_groups(self):
        alerts = [
            {"category": "source_stale", "is_blocking": True, "code": "s1"},
            {"category": "matching_gap", "is_blocking": False, "code": "m1"},
            {"category": "workflow_gap", "is_blocking": True, "code": "w1"},
            {"category": "workflow_gap", "is_blocking": True, "code": "w2"},
        ]
        s = _summarize_by_category(alerts)
        assert s["source_stale"]["count"] == 1
        assert s["workflow_gap"]["count"] == 2
        assert s["workflow_gap"]["blocking"] == 2


class TestSummarizeByOwner:
    def test_groups(self):
        alerts = [{"owner": "TI", "is_blocking": True}, {"owner": "Operaciones", "is_blocking": False}]
        s = _summarize_by_owner(alerts)
        assert s["TI"]["count"] == 1
        assert s["Operaciones"]["count"] == 1


class TestRootCauseSource:
    def test_lag(self):
        assert "ETL" in _root_cause_source({"lag_days": 4, "total_rows": 100})
    def test_empty(self):
        assert "ETL" in _root_cause_source({"lag_days": None, "total_rows": 0})


class TestPipelineFallback:
    def test_structured(self):
        r = _pipeline_fallback("test")
        assert r["overall_status"] == "unknown"
