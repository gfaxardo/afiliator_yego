"""
CLI para recalcular un cutoff de forma segura e idempotente.
Uso: python -m app.scripts.recalculate_scout_cutoff --cutoff-id X
"""

import argparse
import sys
import os
import json
from datetime import date
from decimal import Decimal
from typing import Optional

# Ensure the parent dir is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import SessionLocal
from app.services.cutoff_engine import calculate_cutoff
from app.models.scout_liq import CutoffRun


def main():
    parser = argparse.ArgumentParser(description="Recalcular cutoff del liquidador")
    parser.add_argument("--cutoff-id", type=int, required=True, help="ID del cutoff a recalcular")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        run = db.query(CutoffRun).filter(CutoffRun.id == args.cutoff_id).first()
        if not run:
            print(f"[ERROR] Cutoff {args.cutoff_id} no encontrado")
            sys.exit(1)

        if run.status not in ("draft", "calculated"):
            print(f"[ERROR] No se puede recalcular cutoff en estado '{run.status}'. Solo draft/calculated.")
            sys.exit(1)

        print(f"[OK] Recalculando cutoff {args.cutoff_id} ({run.cutoff_name})")
        run.status = "draft"
        db.commit()

        result = calculate_cutoff(db, args.cutoff_id)
        print(f"[OK] Calculo completo: {json.dumps(result, default=str)}")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
