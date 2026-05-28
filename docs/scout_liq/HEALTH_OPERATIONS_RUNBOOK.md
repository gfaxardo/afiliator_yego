# Health Operations Runbook — Liquidador Scouts Yego

Ruta UI: `/scout-liq/salud`

---

## Que significa cada estado

| Estado | Significado | Se puede operar? |
|---|---|---|
| OK | Todo al dia: fuente fresca, scouts asignados, cohortes con cutoff | SI — crear cortes, calcular, aprobar pagos |
| WARNING | Hay pendientes no bloqueantes (ej: pocos sin scout, cohorte no madura) | SI con precaucion — crear cortes, pero revisar drivers sin scout |
| BLOCKED | Hay bloqueantes: fuente atrasada, cohorte madura sin cutoff, o cobertura <20% | SOLO DIAGNOSTICO — Preview permitido, aprobacion bloqueada |

---

## Que hacer si...

### Fuente operativa atrasada

**Sintoma**: Card "Fuente Operativa" en BLOCKED, lag > 1 dia.

**Causa**: `module_ct_cabinet_drivers` no tiene datos al dia.

**Accion TI**:
1. Verificar cronjob/ETL que carga la tabla
2. Validar que `MAX(hire_date)` este al dia
3. Si la fuente esta realmente al dia pero la app muestra stale, ejecutar `POST /scout-liq/health/recompute-derived`

**No se puede**: aprobar pagos hasta que la fuente este fresca.

### Drivers sin scout

**Sintoma**: Card "Matching" en WARNING, cobertura < 80%.

**Accion Operaciones**:
1. Ir a Centro Operativo > Asignar Scout
2. O usar carga masiva desde Excel
3. Descargar CSV: boton "Sin Scout CSV" en Salud de Data

**No bloquea pagos** por si solo si cobertura > 20%, pero los drivers sin scout no seran liquidados.

### Cohortes maduras sin cutoff

**Sintoma**: Cohortes con estado BLOCKED, columna Cutoff = "NO".

**Accion Operaciones / Liquidacion**:
1. Ir a Liquidaciones > Crear corte por cohorte
2. Seleccionar la cohorte madura (ej: S18-2026)
3. Completar el wizard de creacion de corte

**Bloqueante**: no se puede liquidar esa cohorte hasta crear el cutoff.

---

## Como ejecutar recompute manual

**Desde UI**: boton "Recalcular" en la pantalla de Salud de Data.

**Desde API**:
```bash
curl -X POST http://localhost:8000/scout-liq/health/recompute-derived
```

**Desde CLI (cron)**:
```bash
cd /path/to/proyecto/backend
python scripts/run_scout_liq_health_recompute.py
```

---

## Como validar cron

```bash
# Verificar si el timer esta activo
systemctl status scout-liq-health-recompute.timer
systemctl status scout-liq-health-recompute.service

# Verificar crontab
crontab -l | grep health_recompute

# Ver ultimas ejecuciones
# En BD: SELECT * FROM scout_liq_job_runs ORDER BY id DESC LIMIT 5;
```

---

## Cuando se puede aprobar un corte

**SI** cuando:
- `can_approve_payments = true` en el readiness
- Fuente operativa al dia (lag <= 1)
- Cohortes tienen cutoff creado (cutoff_exists = true)
- Preview muestra montos correctos

**NO** cuando:
- `can_approve_payments = false`
- Fuente atrasada (lag > 1): los datos de viajes pueden ser incompletos
- Sin cutoff: no hay calculo que aprobar

---

## Cuando NO se puede aprobar un pago

- Fuente operativa atrasada mas de 1 dia
- Drivers sin scout en la cohorte (no seran incluidos en el calculo)
- Cohorte no madura (aun no pasaron 7 dias desde el cierre)
- Cutoff no calculado o con errores

---

## Descargas operativas

Desde la UI o API:

| Recurso | URL |
|---|---|
| Alertas CSV | `GET /scout-liq/health/alerts.csv` |
| Drivers sin scout CSV | `GET /scout-liq/health/unassigned-drivers.csv` |
| Cohortes bloqueadas CSV | `GET /scout-liq/health/cohorts-blocked.csv` |

---

## Contactos segun dominio bloqueante

| Dominio | Owner |
|---|---|
| source (fuente atrasada) | TI / ETL externo |
| assignment (drivers sin scout) | Operaciones |
| cutoff_workflow (cohorte sin cutoff) | Operaciones / Liquidacion |
| derived_stale (derivados stale) | TI / Automatizar cron |
| missing_job (job no ejecutado) | TI / Deploy |
