"""
Health Registry Service — Auto Health Monitoring.

Registra snapshots de refresh, detecta eventos, calcula health score.
Append-only: solo INSERT e UPDATE status, nunca DELETE ni TRUNCATE.
"""

import time as _time
import json as _json
import logging
import traceback as _traceback
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.config import settings
from app.services.scout_liq_health_service import (
    get_source_health,
    get_scout_assignment_health,
    get_cohort_health,
    get_jobs_health,
    _status_from_lag,
    _status_from_gap,
)

_logger = logging.getLogger("scout_liq_health_registry")

SOURCE_TABLE = settings.SOURCE_TABLE
STATEMENT_TIMEOUT = "SET LOCAL statement_timeout = '30000ms'"

REGISTRY_TABLE = "scout_liq_refresh_registry"
EVENTS_TABLE = "scout_liq_health_events"

# Source definitions for registry
REGISTRY_SOURCES = [
    {
        "source_name": SOURCE_TABLE,
        "source_type": "source_table",
        "expected_frequency_minutes": 1440,
    },
    {
        "source_name": "scout_assignments",
        "source_type": "table",
        "expected_frequency_minutes": 10080,
    },
    {
        "source_name": "cutoff_runs",
        "source_type": "table",
        "expected_frequency_minutes": 10080,
    },
    {
        "source_name": "paid_history",
        "source_type": "table",
        "expected_frequency_minutes": 10080,
    },
    {
        "source_name": "historical_import_batches",
        "source_type": "table",
        "expected_frequency_minutes": 10080,
    },
]


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _table_exists(db: Session, table_name: str) -> bool:
    try:
        row = db.execute(text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :tbl)"
        ), {"tbl": table_name}).scalar()
        return bool(row)
    except Exception:
        return False


def _upsert_to_registry(db: Session, entries: list, now: datetime):
    if not _table_exists(db, REGISTRY_TABLE):
        _logger.warning(f"[_upsert_to_registry] Tabla {REGISTRY_TABLE} no existe. Omitiendo persistencia.")
        return
    try:
        for e in entries:
            existing = db.execute(text("""
                SELECT id FROM scout_liq_refresh_registry WHERE source_name = :sn
            """), {"sn": e["source_name"]}).scalar()
            if existing:
                db.execute(text("""
                    UPDATE scout_liq_refresh_registry SET
                        last_seen_data_at = :lsda,
                        last_refresh_at = :lra,
                        last_success_at = :lsa,
                        lag_minutes = :lm,
                        rows_observed = :ro,
                        status = :st,
                        reason_text = :rt,
                        updated_at = NOW()
                    WHERE id = :id
                """), {
                    "lsda": e["last_seen_data_at"],
                    "lra": e["last_refresh_at"],
                    "lsa": now.isoformat() if e["status"] == "OK" else None,
                    "lm": e["lag_minutes"],
                    "ro": e["rows_observed"],
                    "st": e["status"],
                    "rt": e["reason_text"],
                    "id": existing,
                })
            else:
                db.execute(text("""
                    INSERT INTO scout_liq_refresh_registry
                        (source_name, source_type, last_seen_data_at, last_refresh_at,
                         last_success_at, expected_frequency_minutes, lag_minutes,
                         rows_observed, status, reason_text)
                    VALUES
                        (:sn, :stype, :lsda, :lra, :lsa, :efm, :lm, :ro, :status, :rt)
                """), {
                    "sn": e["source_name"],
                    "stype": e["source_type"],
                    "lsda": e["last_seen_data_at"],
                    "lra": e["last_refresh_at"],
                    "lsa": now.isoformat() if e["status"] == "OK" else None,
                    "efm": e["expected_frequency_minutes"],
                    "lm": e["lag_minutes"],
                    "ro": e["rows_observed"],
                    "status": e["status"],
                    "rt": e["reason_text"],
                })
    except Exception as e:
        _logger.error(f"[_upsert_to_registry] Error en persistencia: {e}. Continuando sin guardar.")


# ═══════════════════════════════════════════════════════════════════════════
# 1. REFRESH REGISTRY SNAPSHOT
# ═══════════════════════════════════════════════════════════════════════════

def refresh_registry_snapshot(db: Session) -> Dict[str, Any]:
    try:
        return _safe_refresh_registry_snapshot(db)
    except Exception as e:
        _logger.error(f"[refresh_registry_snapshot] {e}\n{_traceback.format_exc()}")
        return {
            "refreshed_at": _now_iso(),
            "entries": [],
            "total": 0,
            "error": True,
            "error_code": "REFRESH_FAILED",
            "message": str(e),
            "_timing_ms": 0,
        }


def _safe_refresh_registry_snapshot(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))
    now = datetime.utcnow()
    today = date.today()

    entries = []

    for src in REGISTRY_SOURCES:
        source_name = src["source_name"]
        source_type = src["source_type"]
        freq = src["expected_frequency_minutes"]

        last_seen = None
        last_refresh = None
        rows_observed = None
        lag_minutes = None
        status = "UNKNOWN"
        reason_text = None

        if source_name == SOURCE_TABLE:
            row = db.execute(text(f"""
                SELECT MAX(hire_date::date), MAX(updated_at), MAX(created_at), COUNT(*)
                FROM {SOURCE_TABLE}
                WHERE hire_date IS NOT NULL AND hire_date != ''
            """)).fetchone()
            if row and row[0]:
                last_seen = row[1] if row[1] else row[2]
                last_refresh = now
                rows_observed = row[3] or 0
                if row[0]:
                    lag_minutes = int((today - row[0]).total_seconds() / 60) if row[0] else None
                    status = _status_from_lag((today - row[0]).days) if row[0] else "UNKNOWN"

        elif source_name == "scout_assignments":
            row = db.execute(text("""
                SELECT MAX(created_at), COUNT(*) FROM scout_liq_driver_assignments
                WHERE status = 'active'
            """)).fetchone()
            if row:
                last_seen = row[0]
                last_refresh = now
                rows_observed = row[1] or 0
                if row[0]:
                    if hasattr(row[0], 'strftime'):
                        lag_minutes = int((now - row[0]).total_seconds() / 60)
                    elif hasattr(row[0], 'isoformat'):
                        lag_minutes = int((now - datetime.fromisoformat(str(row[0]))).total_seconds() / 60)
                    status = _status_from_gap(lag_minutes / 60) if lag_minutes else "UNKNOWN"

        elif source_name == "cutoff_runs":
            row = db.execute(text("""
                SELECT MAX(created_at), COUNT(*) FROM scout_liq_cutoff_runs
            """)).fetchone()
            if row:
                last_seen = row[0]
                last_refresh = now
                rows_observed = row[1] or 0
                if row[0]:
                    if hasattr(row[0], 'strftime'):
                        lag_minutes = int((now - row[0]).total_seconds() / 60)
                    elif hasattr(row[0], 'isoformat'):
                        lag_minutes = int((now - datetime.fromisoformat(str(row[0]))).total_seconds() / 60)
                    status = _status_from_gap(lag_minutes / 60) if lag_minutes else "UNKNOWN"

        elif source_name == "paid_history":
            row = db.execute(text("""
                SELECT MAX(created_at), COUNT(*) FROM scout_liq_paid_history
            """)).fetchone()
            if row:
                last_seen = row[0]
                last_refresh = now
                rows_observed = row[1] or 0
                if row[0]:
                    if hasattr(row[0], 'strftime'):
                        lag_minutes = int((now - row[0]).total_seconds() / 60)
                    elif hasattr(row[0], 'isoformat'):
                        lag_minutes = int((now - datetime.fromisoformat(str(row[0]))).total_seconds() / 60)
                    status = _status_from_gap(lag_minutes / 60) if lag_minutes else "UNKNOWN"

        elif source_name == "historical_import_batches":
            try:
                row = db.execute(text("""
                    SELECT MAX(created_at), COUNT(*) FROM scout_liq_historical_import_batches
                """)).fetchone()
            except Exception:
                row = None
            if row:
                last_seen = row[0]
                last_refresh = now
                rows_observed = row[1] or 0
                if row[0]:
                    if hasattr(row[0], 'strftime'):
                        lag_minutes = int((now - row[0]).total_seconds() / 60)
                    elif hasattr(row[0], 'isoformat'):
                        lag_minutes = int((now - datetime.fromisoformat(str(row[0]))).total_seconds() / 60)
                    status = _status_from_gap(lag_minutes / 60) if lag_minutes else "UNKNOWN"
            else:
                reason_text = "Tabla opcional no existe"

        if lag_minutes is not None and status == "UNKNOWN":
            if lag_minutes <= freq:
                status = "OK"

        entries.append({
            "source_name": source_name,
            "source_type": source_type,
            "last_seen_data_at": str(last_seen) if last_seen else None,
            "last_refresh_at": str(last_refresh),
            "expected_frequency_minutes": freq,
            "lag_minutes": lag_minutes,
            "lag_hours": round(lag_minutes / 60.0, 1) if lag_minutes is not None else None,
            "lag_days": round(lag_minutes / 1440.0, 1) if lag_minutes is not None else None,
            "rows_observed": rows_observed,
            "status": status,
            "reason_text": reason_text,
        })

    # Upsert into DB (safe: skips if table doesn't exist)
    _upsert_to_registry(db, entries, now)

    db.commit()

    return {
        "refreshed_at": now.isoformat(),
        "entries": entries,
        "total": len(entries),
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. COMPUTE HEALTH SCORE
# ═══════════════════════════════════════════════════════════════════════════

def compute_health_score(db: Session) -> Dict[str, Any]:
    try:
        return _safe_compute_health_score(db)
    except Exception as e:
        _logger.error(f"[compute_health_score] {e}\n{_traceback.format_exc()}")
        return {
            "score": None,
            "status": "UNKNOWN",
            "reason_text": f"No se pudo calcular health score: {e}",
            "breakdown": {},
            "max_score": 100,
            "evaluated_at": date.today().isoformat(),
            "_timing_ms": 0,
        }


def _safe_compute_health_score(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()

    source = get_source_health(db)
    scouts = get_scout_assignment_health(db)
    cohorts = get_cohort_health(db, weeks_limit=4, skip_trips=True)
    jobs = get_jobs_health(db)

    def _score(status: str, weight: int) -> float:
        if status == "OK":
            return weight * 1.0
        elif status == "WARNING":
            return weight * 0.5
        elif status == "BLOCKED":
            return weight * 0.0
        elif status == "INFO":
            return weight * 0.6
        elif status == "UNKNOWN":
            return weight * 0.25
        return 0

    source_status = source.get("status", "UNKNOWN") if source else "UNKNOWN"
    scouts_status = scouts.get("status", "UNKNOWN") if scouts else "UNKNOWN"
    cohorts_status = (cohorts or {}).get("global_status", "UNKNOWN")
    jobs_status = (jobs or {}).get("global_status", "UNKNOWN")

    breakdown = {
        "source": {"weight": 35, "status": source_status, "score": _score(source_status, 35)},
        "scouts": {"weight": 25, "status": scouts_status, "score": _score(scouts_status, 25)},
        "cohorts": {"weight": 25, "status": cohorts_status, "score": _score(cohorts_status, 25)},
        "jobs": {"weight": 15, "status": jobs_status, "score": _score(jobs_status, 15)},
    }

    total_score = round(sum(b["score"] for b in breakdown.values()))

    if total_score >= 85:
        status = "OK"
    elif total_score >= 60:
        status = "WARNING"
    else:
        status = "BLOCKED"

    reason_parts = []
    if source and source.get("status") != "OK":
        reason_parts.append(source.get("reason_text", ""))
    if scouts and scouts.get("status") != "OK":
        reason_parts.append(scouts.get("reason_text", ""))
    if cohorts and cohorts.get("global_status") != "OK":
        reason_parts.append(cohorts.get("global_reason", ""))
    reason_text = "; ".join(reason_parts) if reason_parts else "Sistema saludable"

    _logger.info(f"[compute_health_score] score={total_score} status={status} ms={round((_time.perf_counter() - t0) * 1000)}")

    return {
        "score": total_score,
        "status": status,
        "reason_text": reason_text,
        "breakdown": breakdown,
        "max_score": 100,
        "evaluated_at": date.today().isoformat(),
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


def compute_health_score_lite(db: Session) -> Dict[str, Any]:
    """Health score rápido. NO consulta cohorts, NO trips.
    Deriva puntaje de cohortes desde eventos abiertos."""
    try:
        return _safe_compute_health_score_lite(db)
    except Exception as e:
        _logger.error(f"[compute_health_score_lite] {e}\n{_traceback.format_exc()}")
        return {
            "score": None,
            "status": "UNKNOWN",
            "reason_text": f"No se pudo calcular: {e}",
            "breakdown": {},
            "max_score": 100,
            "evaluated_at": date.today().isoformat(),
            "mode": "lite",
            "_timing_ms": 0,
        }


def _safe_compute_health_score_lite(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()

    source = get_source_health(db)
    scouts = get_scout_assignment_health(db)
    jobs = get_jobs_health(db)

    db.execute(text(STATEMENT_TIMEOUT))
    event_rows = db.execute(text("""
        SELECT severity, COUNT(*) FROM scout_liq_health_events
        WHERE status = 'open' GROUP BY severity
    """)).fetchall()
    blocked_events = 0
    warning_events = 0
    for r in event_rows:
        if (r[0] or "").upper() == "BLOCKED":
            blocked_events = r[1] or 0
        elif (r[0] or "").upper() == "WARNING":
            warning_events = r[1] or 0

    def _score(status: str, weight: int) -> float:
        if status == "OK":
            return weight * 1.0
        elif status == "WARNING":
            return weight * 0.5
        elif status == "BLOCKED":
            return weight * 0.0
        elif status == "INFO":
            return weight * 0.6
        elif status == "UNKNOWN":
            return weight * 0.25
        return 0

    source_status = source.get("status", "UNKNOWN") if source else "UNKNOWN"
    scouts_status = scouts.get("status", "UNKNOWN") if scouts else "UNKNOWN"
    jobs_status = (jobs or {}).get("global_status", "UNKNOWN")

    if blocked_events > 0:
        event_score_25 = 0.0
        event_label = "BLOCKED"
    elif warning_events > 0:
        event_score_25 = 12.5
        event_label = "WARNING"
    else:
        event_score_25 = 25.0
        event_label = "OK"

    breakdown = {
        "source": {"weight": 35, "status": source_status, "score": _score(source_status, 35)},
        "scouts": {"weight": 25, "status": scouts_status, "score": _score(scouts_status, 25)},
        "events_cohorts": {"weight": 25, "status": event_label, "score": event_score_25,
                           "blocked_count": blocked_events, "warning_count": warning_events},
        "jobs": {"weight": 15, "status": jobs_status, "score": _score(jobs_status, 15)},
    }

    total_score = round(sum(b["score"] for b in breakdown.values()))

    if total_score >= 85:
        status = "OK"
    elif total_score >= 60:
        status = "WARNING"
    else:
        status = "BLOCKED"

    reason_parts = []
    if source_status != "OK":
        reason_parts.append(source.get("reason_text", ""))
    if scouts_status != "OK":
        reason_parts.append(scouts.get("reason_text", ""))
    if blocked_events > 0:
        reason_parts.append(f"{blocked_events} eventos criticos activos")
    elif warning_events > 0:
        reason_parts.append(f"{warning_events} eventos con advertencias")
    reason_text = "; ".join(reason_parts) if reason_parts else "Sistema saludable"

    _logger.info(f"[compute_health_score_lite] score={total_score} status={status} ms={round((_time.perf_counter() - t0) * 1000)}")

    return {
        "score": total_score,
        "status": status,
        "reason_text": reason_text,
        "breakdown": breakdown,
        "max_score": 100,
        "evaluated_at": date.today().isoformat(),
        "mode": "lite",
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. DETECT HEALTH EVENTS
# ═══════════════════════════════════════════════════════════════════════════

def detect_health_events(db: Session) -> Dict[str, Any]:
    try:
        return _safe_detect_health_events(db)
    except Exception as e:
        _logger.error(f"[detect_health_events] {e}\n{_traceback.format_exc()}")
        return {
            "new_events": 0,
            "skipped_duplicates": 0,
            "events": [],
            "detected_at": _now_iso(),
            "error": True,
            "error_message": str(e),
            "_timing_ms": 0,
        }


def _safe_detect_health_events(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    source = get_source_health(db)
    scouts = get_scout_assignment_health(db)
    cohorts = get_cohort_health(db, weeks_limit=8)

    new_events = []
    skipped_duplicates = 0

    table_ok = _table_exists(db, EVENTS_TABLE)

    def _emit(event_type: str, severity: str, source_name: str | None,
              cohort_key: str | None, title: str, message: str):
        nonlocal new_events, skipped_duplicates
        if not table_ok:
            return
        # Check for existing open event with same key
        params = {
            "et": event_type,
            "sn": source_name,
            "ck": cohort_key,
        }
        parts = ["event_type = :et", "status = 'open'"]
        if source_name:
            parts.append("source_name = :sn")
        else:
            parts.append("source_name IS NULL")
        if cohort_key:
            parts.append("cohort_key = :ck")
        else:
            parts.append("cohort_key IS NULL")

        existing = db.execute(text(
            f"SELECT id FROM scout_liq_health_events WHERE {' AND '.join(parts)} LIMIT 1"
        ), params).scalar()

        if existing:
            skipped_duplicates += 1
            return

        db.execute(text("""
            INSERT INTO scout_liq_health_events
                (event_type, severity, source_name, cohort_key, title, message, status, detected_at)
            VALUES (:et, :sev, :sn, :ck, :title, :msg, 'open', NOW())
        """), {
            "et": event_type, "sev": severity, "sn": source_name,
            "ck": cohort_key, "title": title, "msg": message,
        })
        new_events.append({"event_type": event_type, "severity": severity, "title": title})

    # 1. Fuente con lag >= 4 dias
    lag = source.get("data_lag_days")
    if lag is not None and lag >= 4:
        _emit("source_lag_blocked", "BLOCKED", SOURCE_TABLE, None,
              f"Fuente operativa atrasada {lag} dias",
              source.get("reason_text", f"Lag de {lag} dias detectado"))

    # 2. Sin carga de scouts reciente
    if scouts["metrics"].get("assignments_last_7d", 0) == 0:
        _emit("scout_load_stale", "WARNING", "scout_assignments", None,
              "Sin carga de scouts reciente (7d)",
              scouts.get("reason_text", "No hay asignaciones nuevas"))

    # 3. Drivers sin scout por encima de umbral (20%+)
    without = scouts["metrics"].get("drivers_without_scout", 0)
    total = scouts["metrics"].get("total_source_drivers", 1)
    if total > 0 and (without / total) >= 0.2:
        _emit("high_unassigned_drivers", "WARNING", "scout_assignments", None,
              f"{without} drivers sin scout ({round(without/total*100)}%)",
              scouts.get("reason_text", "Alto porcentaje de drivers sin scout"))

    # 4. Eventos por cohorte
    for c in cohorts.get("cohorts", []):
        ck = c["cohort_key"]
        flags = c.get("flags", {})
        diags = c.get("diagnostics", [])

        if flags.get("missing_scout_load_flag"):
            _emit("cohort_no_scouts", "BLOCKED", "cohort", ck,
                  f"Cohorte {c['cohort_label']} sin scouts",
                  c.get("reason_text", "Cohorte sin scouts asignados"))

        if flags.get("no_activity_flag"):
            _emit("cohort_no_activity", "WARNING", "cohort", ck,
                  f"Cohorte {c['cohort_label']} madura sin activaciones",
                  c.get("reason_text", "Cohorte madura 7D sin activaciones"))

        if flags.get("missing_conversion_flag"):
            _emit("cohort_no_conversion", "WARNING", "cohort", ck,
                  f"Cohorte {c['cohort_label']} sin conversion 5V7D",
                  c.get("reason_text", "Sin conversion a pesar de tener activaciones"))

        if flags.get("stale_cohort_flag"):
            _emit("cohort_stale", "WARNING", "cohort", ck,
                  f"Cohorte {c['cohort_label']} madura sin cutoff",
                  c.get("reason_text", "Cohorte madura sin cutoff creado"))

        if c.get("expected_14d_matured") and c.get("activated_1_trip", 0) == 0:
            if "cohort_matured_without_activity" in diags:
                _emit("cohort_14d_no_data", "BLOCKED", "cohort", ck,
                      f"Cohorte {c['cohort_label']} madura 14D sin data",
                      c.get("reason_text", "Cohorte madura 14D sin datos de viajes"))

    db.commit()

    return {
        "new_events": len(new_events),
        "skipped_duplicates": skipped_duplicates,
        "events": new_events,
        "detected_at": _now_iso(),
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. RESOLVE RECOVERED EVENTS
# ═══════════════════════════════════════════════════════════════════════════

def resolve_recovered_events(db: Session) -> Dict[str, Any]:
    try:
        return _safe_resolve_recovered_events(db)
    except Exception as e:
        _logger.error(f"[resolve_recovered_events] {e}\n{_traceback.format_exc()}")
        return {
            "resolved_count": 0,
            "total_open_before": 0,
            "resolved_at": _now_iso(),
            "error": True,
            "error_message": str(e),
            "_timing_ms": 0,
        }


def _safe_resolve_recovered_events(db: Session) -> Dict[str, Any]:
    t0 = _time.perf_counter()
    db.execute(text(STATEMENT_TIMEOUT))

    if not _table_exists(db, EVENTS_TABLE):
        _logger.warning(f"[resolve_recovered_events] Tabla {EVENTS_TABLE} no existe. Nada que resolver.")
        return {
            "resolved_count": 0,
            "total_open_before": 0,
            "resolved_at": _now_iso(),
            "_timing_ms": round((_time.perf_counter() - t0) * 1000),
        }

    source = get_source_health(db)
    scouts = get_scout_assignment_health(db)
    cohorts = get_cohort_health(db, weeks_limit=8)

    resolved_count = 0
    now = datetime.utcnow()

    open_events = db.execute(text("""
        SELECT id, event_type, source_name, cohort_key
        FROM scout_liq_health_events WHERE status = 'open'
    """)).fetchall()

    for ev in open_events:
        eid, etype, esrc, eck = ev
        should_resolve = False

        if etype == "source_lag_blocked":
            lag = source.get("data_lag_days")
            if lag is not None and lag < 4:
                should_resolve = True

        elif etype == "scout_load_stale":
            if scouts["metrics"].get("assignments_last_7d", 0) > 0:
                should_resolve = True

        elif etype == "high_unassigned_drivers":
            without = scouts["metrics"].get("drivers_without_scout", 0)
            total = scouts["metrics"].get("total_source_drivers", 1)
            if total > 0 and (without / total) < 0.2:
                should_resolve = True

        elif etype in ("cohort_no_scouts", "cohort_no_activity",
                        "cohort_no_conversion", "cohort_stale", "cohort_14d_no_data"):
            for c in cohorts.get("cohorts", []):
                if c["cohort_key"] == eck and c.get("status") == "OK":
                    should_resolve = True
                    break

        if should_resolve:
            db.execute(text("""
                UPDATE scout_liq_health_events
                SET status = 'resolved', resolved_at = :now
                WHERE id = :eid
            """), {"now": now, "eid": eid})
            resolved_count += 1

    db.commit()

    return {
        "resolved_count": resolved_count,
        "total_open_before": len(open_events),
        "resolved_at": now.isoformat(),
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. FULL REFRESH CYCLE
# ═══════════════════════════════════════════════════════════════════════════

def full_refresh_cycle(db: Session) -> Dict[str, Any]:
    """Ejecuta snapshot + detect events + resolve recovered + score.
    Cada etapa es independiente: si una falla, las demas continuan."""
    t0 = _time.perf_counter()

    registry = refresh_registry_snapshot(db)
    events_detected = detect_health_events(db)
    events_resolved = resolve_recovered_events(db)
    score = compute_health_score(db)

    return {
        "score": score,
        "registry": registry,
        "events_detected": events_detected,
        "events_resolved": events_resolved,
        "cycle_completed_at": _now_iso(),
        "_timing_ms": round((_time.perf_counter() - t0) * 1000),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. READ OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_registry(db: Session) -> List[Dict[str, Any]]:
    try:
        return _safe_get_registry(db)
    except Exception as e:
        _logger.error(f"[get_registry] {e}\n{_traceback.format_exc()}")
        return []


def _safe_get_registry(db: Session) -> List[Dict[str, Any]]:
    if not _table_exists(db, REGISTRY_TABLE):
        _logger.warning(f"[get_registry] Tabla {REGISTRY_TABLE} no existe. Devolviendo lista vacia.")
        return []

    db.execute(text(STATEMENT_TIMEOUT))
    rows = db.execute(text("""
        SELECT id, source_name, source_type, last_seen_data_at, last_refresh_at,
               last_success_at, last_error_at, expected_frequency_minutes,
               lag_minutes, rows_observed, status, reason_text,
               created_at::text, updated_at::text
        FROM scout_liq_refresh_registry
        ORDER BY source_name
    """)).fetchall()

    return [
        {
            "id": r[0], "source_name": r[1], "source_type": r[2],
            "last_seen_data_at": str(r[3]) if r[3] else None,
            "last_refresh_at": str(r[4]) if r[4] else None,
            "last_success_at": str(r[5]) if r[5] else None,
            "last_error_at": str(r[6]) if r[6] else None,
            "expected_frequency_minutes": r[7],
            "lag_minutes": r[8],
            "lag_hours": round(r[8] / 60.0, 1) if r[8] is not None else None,
            "lag_days": round(r[8] / 1440.0, 1) if r[8] is not None else None,
            "rows_observed": r[9],
            "status": r[10],
            "reason_text": r[11],
            "created_at": r[12],
            "updated_at": r[13],
        }
        for r in rows
    ]


def get_events(
    db: Session,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    try:
        return _safe_get_events(db, status, severity, limit)
    except Exception as e:
        _logger.error(f"[get_events] status={status} severity={severity} limit={limit}: {e}\n{_traceback.format_exc()}")
        return []


def _safe_get_events(
    db: Session,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    if not _table_exists(db, EVENTS_TABLE):
        _logger.warning(f"[get_events] Tabla {EVENTS_TABLE} no existe. Devolviendo lista vacia.")
        return []

    db.execute(text(STATEMENT_TIMEOUT))

    where_parts = ["1=1"]
    params: Dict[str, Any] = {"limit": limit}

    if status and status != "all":
        where_parts.append("status = :st")
        params["st"] = status
    if severity:
        where_parts.append("severity = :sev")
        params["sev"] = severity

    where_clause = " AND ".join(where_parts)

    rows = db.execute(text(f"""
        SELECT id, event_type, severity, source_name, cohort_key,
               title, message, status, detected_at::text, resolved_at::text
        FROM scout_liq_health_events
        WHERE {where_clause}
        ORDER BY detected_at DESC
        LIMIT :limit
    """), params).fetchall()

    return [
        {
            "id": r[0], "event_type": r[1], "severity": r[2],
            "source_name": r[3], "cohort_key": r[4],
            "title": r[5], "message": r[6],
            "status": r[7], "detected_at": r[8], "resolved_at": r[9],
        }
        for r in rows
    ]
