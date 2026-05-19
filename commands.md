# AFILIATOR - Liquidador de Calidad Scouts Yego
# Comandos de operacion
# Puertos finales: Backend=8000 / Frontend=5173

## Instalar dependencias
cd backend
pip install -r requirements.txt

cd ..\frontend
npm install

## Configurar entorno
cp backend\.env.example backend\.env
# Editar backend\.env con credenciales reales de PostgreSQL

## Ejecutar diagnostico de tabla fuente
python scripts\diagnose_source.py

## Ejecutar migraciones
cd backend
alembic upgrade head

## Ejecutar seed inicial
cd backend
python -m app.seed

## Correr backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

## Correr frontend
cd frontend
npm run dev

## Pruebas Fase 1 (health, diagnostic)
curl http://localhost:8000/scout-liq/health
curl http://localhost:8000/scout-liq/source/diagnostic
curl http://localhost:8000/scout-liq/scouts
curl -X POST http://localhost:8000/scout-liq/scouts -H "Content-Type: application/json" -d "{\"scout_name\":\"Test Scout\"}"

## Pruebas Fase 3 (quality contract, cutoffs, liquidador)
curl http://localhost:8000/scout-liq/source/quality-contract
curl -X POST "http://localhost:8000/scout-liq/cutoffs?cutoff_name=Corte%20Test&hire_date_from=2025-04-01&hire_date_to=2026-05-15&scheme_id=1"
curl http://localhost:8000/scout-liq/cutoffs
curl http://localhost:8000/scout-liq/cutoffs/1/summary
curl http://localhost:8000/scout-liq/cutoffs/1/lines
curl http://localhost:8000/scout-liq/cutoffs/1/export.csv

## Auditoria de conteos reales de viajes
python scripts\audit_trip_counts.py
python scripts\audit_trip_counts.py b4d763d0c64c439aa578993029527dd9
python scripts\audit_trip_counts.py ca915d577b0242b2ab5570924aab3804
