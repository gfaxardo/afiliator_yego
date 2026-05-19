"""
Seed inicial para Liquidador de Calidad Scouts Yego.
Inserta el esquema base "Cabinet Destajo Base" con sus 4 tramos.

Uso:
    python -m app.seed
"""

from sqlalchemy.orm import Session
from decimal import Decimal

from app.database import SessionLocal, engine
from app.models.scout_liq import Base, ConversionScheme, ConversionTier


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        existing = (
            db.query(ConversionScheme)
            .filter(ConversionScheme.scheme_name == "Cabinet Destajo Base")
            .first()
        )
        if existing:
            print("[SKIP] Seed ya existe: Cabinet Destajo Base")
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
            tier = ConversionTier(
                scheme_id=scheme.id,
                min_conversion_rate=rate,
                payment_per_converted_driver=payment,
                currency="PEN",
                active=True,
            )
            db.add(tier)

        db.commit()
        print(f"[OK] Seed creado: {scheme.scheme_name} (ID={scheme.id})")
        print(f"     Tramos: {len(tiers_data)}")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
