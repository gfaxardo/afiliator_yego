"""
Seed inicial para Liquidador de Calidad Scouts Yego.
Inserta el esquema base "Cabinet Destajo Base" con sus 4 tramos,
y los payment schemes versionados (Cabinet Standard v1, Fleet Standard v1).

Uso:
    python -m app.seed
"""

from sqlalchemy.orm import Session
from decimal import Decimal
from datetime import datetime

from app.database import SessionLocal, engine
from app.models.scout_liq import (
    Base, ConversionScheme, ConversionTier,
    PaymentScheme, PaymentSchemeVersion, PaymentSchemeTier,
)


def _seed_legacy_conversion_scheme(db: Session):
    existing = (
        db.query(ConversionScheme)
        .filter(ConversionScheme.scheme_name == "Cabinet Destajo Base")
        .first()
    )
    if existing:
        print("[SKIP] Legacy conversion scheme ya existe")
        return

    scheme = ConversionScheme(
        scheme_name="Cabinet Destajo Base",
        origin="cabinet",
        scout_type="destajo",
        min_affiliations=8,
        active=True,
    )
    db.add(scheme)
    db.flush()

    tiers_data = [
        (Decimal("0.10"), Decimal("10.00")),
        (Decimal("0.20"), Decimal("20.00")),
        (Decimal("0.30"), Decimal("30.00")),
        (Decimal("0.40"), Decimal("40.00")),
    ]
    for rate, payment in tiers_data:
        db.add(ConversionTier(
            scheme_id=scheme.id,
            min_conversion_rate=rate,
            payment_per_converted_driver=payment,
            currency="PEN",
            active=True,
        ))
    db.commit()
    print(f"[OK] Legacy conversion scheme: {scheme.scheme_name} (ID={scheme.id}, tiers={len(tiers_data)})")


def _seed_payment_scheme(
    db: Session,
    name: str,
    scheme_type: str,
    description: str,
    version_name: str,
    valid_from: str,
    maturity_days: int,
    min_activated: int,
    activation_rule: str,
    quality_rule: str,
    formula_type: str,
    currency: str,
    tiers_data: list,
    volume_rule: str = None,
    pays_on_rule: str = None,
    payout_formula_type: str = None,
    counts_volume_rule: str = None,
    counts_quality_rule: str = None,
    maturity_window_days: int = None,
    min_volume_count: int = None,
):
    scheme = db.query(PaymentScheme).filter(
        PaymentScheme.name == name,
        PaymentScheme.scheme_type == scheme_type,
    ).first()
    if scheme:
        print(f"[SKIP] Payment scheme ya existe: {name} ({scheme_type})")
        return scheme

    scheme = PaymentScheme(
        name=name,
        scheme_type=scheme_type,
        description=description,
        is_active=True,
    )
    db.add(scheme)
    db.flush()

    version = PaymentSchemeVersion(
        scheme_id=scheme.id,
        version_name=version_name,
        valid_from_cohort_iso_week=valid_from,
        valid_to_cohort_iso_week=None,
        maturity_days=maturity_days,
        min_activated=min_activated,
        activation_rule=activation_rule,
        quality_rule=quality_rule,
        formula_type=formula_type,
        currency=currency,
        volume_rule=volume_rule or activation_rule,
        pays_on_rule=pays_on_rule,
        payout_formula_type=payout_formula_type or formula_type,
        counts_volume_rule=counts_volume_rule or activation_rule,
        counts_quality_rule=counts_quality_rule or quality_rule,
        maturity_window_days=maturity_window_days or maturity_days,
        min_volume_count=min_volume_count or min_activated,
        status="active",
        activated_at=datetime.now(),
    )
    db.add(version)
    db.flush()

    for i, (rate, amount) in enumerate(tiers_data):
        db.add(PaymentSchemeTier(
            scheme_version_id=version.id,
            min_conversion_rate=Decimal(str(rate)),
            payout_amount=Decimal(str(amount)),
            sort_order=i,
        ))

    db.commit()
    print(f"[OK] Payment scheme: {name} ({scheme_type}) v={version_name} tiers={len(tiers_data)}")
    return scheme


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        _seed_legacy_conversion_scheme(db)

        _seed_payment_scheme(
            db,
            name="Cabinet Standard",
            scheme_type="cabinet",
            description="Esquema base para scouts cabinet. Activacion: 1 viaje en 7 dias. Calidad: 5 viajes en 7 dias. Pago: activados x tier.",
            version_name="v1",
            valid_from="2026-W01",
            maturity_days=7,
            min_activated=8,
            activation_rule="1V7D",
            quality_rule="5V7D",
            formula_type="ACTIVATED_X_TIER",
            currency="PEN",
            tiers_data=[
                (0.10, 10),
                (0.20, 20),
                (0.30, 30),
                (0.40, 40),
            ],
            volume_rule="1V7D",
            pays_on_rule="ACTIVATED_BASE",
            payout_formula_type="ACTIVATED_X_TIER",
        )

        _seed_payment_scheme(
            db,
            name="Fleet Standard",
            scheme_type="fleet",
            description="Esquema base para scouts fleet. Activacion: 50 viajes en 30 dias. Calidad: 50 viajes en 30 dias. Pago: calidad x fijo.",
            version_name="v1",
            valid_from="2026-W01",
            maturity_days=30,
            min_activated=1,
            activation_rule="50V30D",
            quality_rule="50V30D",
            formula_type="QUALITY_X_FIXED",
            currency="PEN",
            tiers_data=[
                (0.25, 50),
                (0.50, 80),
                (0.75, 120),
            ],
            volume_rule="50V30D",
            pays_on_rule="QUALITY_HIT",
            payout_formula_type="QUALITY_X_FIXED",
        )

    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        db.close()
