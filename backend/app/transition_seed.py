"""
Seed de transición operacional para Cabinet.
Crea 3 versiones graduales y las activa en orden cronológico.

NO edita versiones activas directamente — usa el flujo del admin service.

Ejecutar:
    python -m app.transition_seed
"""

from app.database import SessionLocal
from app.services.payment_scheme_admin_service import (
    create_payment_scheme_version,
    activate_payment_scheme_version,
    archive_payment_scheme_version,
)
from app.models.scout_liq import PaymentScheme


TIERS_10_20_30_40 = [
    {"min_conversion_rate": 0.10, "payout_amount": 10},
    {"min_conversion_rate": 0.20, "payout_amount": 20},
    {"min_conversion_rate": 0.30, "payout_amount": 30},
    {"min_conversion_rate": 0.40, "payout_amount": 40},
]

VERSIONS = [
    {
        "version_name": "Cabinet Transition v1",
        "valid_from_cohort_iso_week": "2026-W20",
        "min_activated": 4,
        "label": "TRANSICIÓN",
    },
    {
        "version_name": "Cabinet Transition v2",
        "valid_from_cohort_iso_week": "2026-W21",
        "min_activated": 6,
        "label": "TRANSICIÓN",
    },
    {
        "version_name": "Cabinet Standard v1",
        "valid_from_cohort_iso_week": "2026-W22",
        "min_activated": 8,
        "label": "ESTÁNDAR",
    },
]

COMMON = {
    "maturity_days": 7,
    "activation_rule": "1V7D",
    "quality_rule": "5V7D",
    "formula_type": "ACTIVATED_X_TIER",
    "currency": "PEN",
}


def run():
    db = SessionLocal()

    try:
        # ── 1. Find Cabinet scheme ──
        scheme = db.query(PaymentScheme).filter(
            PaymentScheme.scheme_type == "cabinet",
            PaymentScheme.is_active == True,
        ).first()

        if not scheme:
            print("[ERROR] No se encontró Cabinet scheme activo.")
            return

        print(f"[INFO] Cabinet scheme id={scheme.id} name={scheme.name}")

        # ── 2. Archive orphan draft versions ──
        from app.models.scout_liq import PaymentSchemeVersion as PSV
        orphan_drafts = db.query(PSV).filter(
            PSV.scheme_id == scheme.id,
            PSV.status == "draft",
        ).all()

        for od in orphan_drafts:
            try:
                archive_payment_scheme_version(db, od.id)
                print(f"[OK] Archived draft version: {od.version_name} (id={od.id})")
            except Exception as e:
                db.rollback()
                print(f"[WARN] Could not archive draft {od.version_name}: {e}")

        # ── 3. Create the 3 transition versions as draft ──
        created_versions = []
        for vdef in VERSIONS:
            try:
                result = create_payment_scheme_version(
                    db,
                    scheme_id=scheme.id,
                    version_name=vdef["version_name"],
                    valid_from_cohort_iso_week=vdef["valid_from_cohort_iso_week"],
                    maturity_days=COMMON["maturity_days"],
                    min_activated=vdef["min_activated"],
                    activation_rule=COMMON["activation_rule"],
                    quality_rule=COMMON["quality_rule"],
                    formula_type=COMMON["formula_type"],
                    currency=COMMON["currency"],
                    tiers=TIERS_10_20_30_40,
                )
                created_versions.append({
                    "version_id": result["version_id"],
                    "version_name": result["version_name"],
                    "valid_from": vdef["valid_from_cohort_iso_week"],
                    "min_activated": vdef["min_activated"],
                    "label": vdef["label"],
                })
                print(f"[OK] Draft creado: {result['version_name']} (id={result['version_id']}) desde {result['valid_from_cohort_iso_week']}")
            except ValueError as e:
                print(f"[SKIP] {vdef['version_name']}: {e}")
                # Try to find existing version and use it
                existing = db.query(PSV).filter(
                    PSV.scheme_id == scheme.id,
                    PSV.version_name == vdef["version_name"],
                ).first()
                if existing:
                    created_versions.append({
                        "version_id": existing.id,
                        "version_name": existing.version_name,
                        "valid_from": existing.valid_from_cohort_iso_week,
                        "min_activated": existing.min_activated,
                        "label": vdef["label"],
                    })
                    print(f"[INFO] Usando version existente: {existing.version_name} (id={existing.id})")

        # ── 4. Activate versions in chronological order (earliest first) ──
        # Sort by valid_from ascending so each activation closes the previous version properly
        created_versions.sort(key=lambda v: v["valid_from"])

        for cv in created_versions:
            try:
                result = activate_payment_scheme_version(db, cv["version_id"])
                print(f"[OK] Activada: {result['version_name']} desde {result['valid_from_cohort_iso_week']}. "
                      f"Anterior: {result.get('previous_active_archived') or 'N/A'}")
            except ValueError as e:
                if "ya esta activa" in str(e):
                    print(f"[INFO] Ya activa: {cv['version_name']}")
                else:
                    print(f"[WARN] No se pudo activar {cv['version_name']}: {e}")

        db.commit()
        print("\n[DONE] Transición Cabinet configurada.")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
