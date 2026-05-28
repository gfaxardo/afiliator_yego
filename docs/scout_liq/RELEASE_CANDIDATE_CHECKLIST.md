# RELEASE CANDIDATE CHECKLIST — Liquidador de Calidad Scouts Yego

## Version: RC-1 | Fecha: 2026-05-27 | Ambientes: dev (validado) → staging (pendiente)

---

## 1. QUE ESTA VALIDADO (DEV)

- [x] **Centro Operativo**: Carga 810+ drivers, fecha ancla, filtros, drawer.
- [x] **Liquidaciones**: Corte desde cohorte (`/cutoffs/from-cohort`) con scheme versionado.
- [x] **Motor de reglas**: Versionado con PaymentSchemeVersion, rule_type, origin_scope, block_scope.
- [x] **Fecha ancla**: Resolucion por origin (cabinet -> lead_created_at_cabinet, fleet -> hire_date).
- [x] **Preview**: Muestra pagables, bloqueados, explicacion por linea.
- [x] **Exports**: CSV completo y CSV financiero funcionando.
- [x] **Doble pago**: Bloquea drivers ya pagados. 0 duplicados en DB.
- [x] **Mark-paid**: Crea paid_history con blocks_future_payment=true.
- [x] **Cancelacion de corte**: Flujo draft->cancelled implementado.
- [x] **XLSX**: Deshabilitado en UI. Endpoint existe pero no expuesto.
- [x] **No se toca module_ct_cabinet_drivers**: Solo SELECT.
- [x] **Tests**: 12/12 payment_guardrails pass. Build frontend OK.
- [x] **Migraciones**: Columnas criticas existen en ambas tablas (driver_lines + paid_history).
- [x] **QA sin legacy**: PaymentScheme versionado creado (id=16, min=1).
- [x] **UI endpoint versionado**: LiquidacionesView y CentroOperativoView usan from-cohort/sweep.

## 2. QUE NO ESTA VALIDADO

- [ ] **UI manual en navegador**: Verificar visualmente Centro Operativo y Liquidaciones en staging.
- [ ] **Mark-paid con scheme versionado**: El legacy scheme_id=2 no puebla rule_code/rule_type/block_scope en paid_history. Los cortes versionados (from-cohort) SI lo hacen.
- [ ] **Escalabilidad >500 drivers**: Limite temporal subido a 5000 para dev. En prod debe ser configurable.
- [ ] **Fleet payments**: Fleet scheme v2 (50V30D) no probado con datos reales.
- [ ] **Supervisor commissions / Bonuses**: No probados en este ciclo.
- [ ] **XLSX funcional**: Endpoint existe pero no verificado.
- [ ] **npm run lint**: No existe script de lint en frontend.
- [ ] **Staging smoke test**: Flujo completo desde UI en staging (Parte G).

## 3. COMO CREAR UN CORTE SEGURO

### Opcion A: Desde cohorte (recomendado para produccion)

```
POST /scout-liq/cutoffs/from-cohort
  cohort_iso_week: "2026-W22"
  scheme_type: "cabinet"
  date_basis: "acquisition_anchor"
```

### Opcion B: Barrido pagable (sweep)

```
POST /scout-liq/cutoffs/sweep
  scheme_type: "cabinet"
```

**Regla**: NO usar `POST /cutoffs` (legacy) para cortes nuevos. Usa ConversionScheme legacy.
Solo existe para backward compatibility.

## 4. COMO REVISAR PREVIEW

```
GET /scout-liq/cutoffs/{cutoff_id}/summary
GET /scout-liq/cutoffs/{cutoff_id}/lines
```

Verificar:
- summary_count > 0
- pagables_count > 0
- blocked_count = no_pagables + already_paid
- Cada linea tiene: anchor_date, rule_code, block_scope, explanation

## 5. COMO APROBAR

```
POST /scout-liq/payments/{cutoff_run_id}/review   # draft → reviewed
POST /scout-liq/payments/{cutoff_run_id}/approve  # reviewed → approved
```

Solo desde `reviewed`. Requiere revision manual previa del preview.

## 6. COMO EXPORTAR

```
GET /scout-liq/payments/{cutoff_run_id}/export.csv       # CSV completo
GET /scout-liq/cutoffs/{cutoff_id}/export-financial.csv   # CSV financiero
```

Validar que el CSV incluya: resumen, detalle, metadata, snapshot, anchor, explanation.

## 7. CUANDO NO MARCAR PAGADO

- Si `pagables_count = 0` (no hay drivers que cumplan regla).
- Si hay `blocked_missing_official_anchor` sin revision manual.
- Si `already_paid` > 0 sin entender por que (posible duplicado).
- Si el total calculado no cuadra con el esperado.
- **NUNCA en produccion sin autorizacion explicita del responsable.**

## 8. QUE REVISAR ANTES DE MARK-PAID

```
GET /scout-liq/payments/{cutoff_run_id}/report
```

- totals.drivers_payable coincide con lo esperado.
- totals.amount_calculated_total es razonable.
- scout_summaries: cada scout con monto > 0 tiene tier y regla.
- paid_history: vacio (no deberia haber pagos previos para este corte).

## 9. COMO VERIFICAR PAID_HISTORY

```
GET /scout-liq/paid-history?cutoff_run_id={id}
```

Confirmar:
- paid_at no es NULL.
- blocks_future_payment = true.
- amount_paid = calculated_amount de la linea.
- driver_id, scout_id, cutoff_run_id llenos.
- scheme_version_id lleno (si es corte versionado).

## 10. COMO VERIFICAR DOBLE PAGO

Crear un segundo corte solapado (misma ventana, mismo scheme) y verificar:
- Los drivers ya pagados aparecen como `blocked_already_paid`.
- `blocked_reason = "ya pagado en corte anterior"`.
- La explanation indica pago previo.

Query SQL:
```sql
SELECT driver_id, rule_code, metric_code, origin_scope, block_scope, COUNT(*)
FROM scout_liq_paid_history
WHERE blocks_future_payment = true
GROUP BY driver_id, rule_code, metric_code, origin_scope, block_scope
HAVING COUNT(*) > 1;
```
Debe devolver 0 filas.

## 11. ENDPOINTS PROHIBIDOS PARA NUEVOS CORTES

- `POST /scout-liq/cutoffs` — legacy, sin rule_type ni block_scope.
- Cualquier endpoint que use `scheme_id` de `ConversionScheme` (no `PaymentSchemeVersion`).

Usar siempre:
- `POST /scout-liq/cutoffs/from-cohort` (con scheme_type).
- `POST /scout-liq/cutoffs/sweep` (con scheme_type).

## 12. QUE HACER SI...

### Hay fallback hire_date
- El driver usa hire_date como anchor porque no tiene lead_created_at.
- En production, estos drivers deben revisarse manualmente (NO auto-payable).
- En dev/staging, aceptable para testing.

### Hay cutoff_too_large
- Significa que hay mas de 500 (o el limite configurado) drivers en la ventana.
- Reducir la ventana de fechas o procesar por lotes.
- NO subir el limite en produccion sin evaluar performance.

### Hay blocked_missing_official_anchor
- Cabinet drivers sin lead_created_at_cabinet.
- Requieren validacion manual antes de autorizar pago.
- Se pueden aprobar individualmente via anchor review.

## 13. QUE QUEDA FUERA DEL MVP

- [ ] Dashboard final de metricas y KPIs.
- [ ] XLSX habilitado en UI.
- [ ] Optimizacion >500/1500 drivers (batch processing).
- [ ] UI avanzada de reglas (crear/editar PaymentSchemeVersion desde UI).
- [ ] Notificaciones de corte listo.
- [ ] Integracion con sistema de pagos externo.
- [ ] Fleet payment full validation.

---

## RESUMEN DE ESTADO

| Metrica | Valor |
|---------|-------|
| Cutoff shadow | #44 (43 pagables, S/4,030) |
| Cutoff mark-paid E2E | #48 (66 pagables, S/2,540 paid) |
| Overlap doble pago | #49 (78 bloqueadas, 0 duplicados) |
| Tests payment_guardrails | 12/12 pass |
| Frontend build | OK |
| Backend compile | OK |
| UI usa endpoints versionados | SI |
| Legacy solo backward compat | SI |
| module_ct_cabinet_drivers intacto | SI |
| Columnas criticas | Todas existen |
| Migraciones | 029 (head) |

**ESTADO: GO para staging. Pendiente: validacion UI manual + smoke test en staging.**

---

## 14. DESPLIEGUE STAGING — COMANDOS

### Pre-deploy (local)
```bash
cd backend
alembic upgrade head
python -m compileall app
pytest -q test_payment_guardrails.py -v
cd ../frontend
npm run build
```

### En servidor staging

**Backup:**
```bash
pg_dump -h STAGING_HOST -U STAGING_USER STAGING_DB > staging_backup_$(date +%Y%m%d_%H%M%S).sql
```

**Migraciones:**
```bash
cd backend
alembic current
alembic upgrade head
alembic current  # Debe mostrar 029
```

**Verificar columnas:**
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'scout_liq_cutoff_driver_lines'
AND column_name IN (
  'anchor_fallback_used','anchor_warning','date_basis',
  'anchor_source','anchor_confidence','metric_window_start',
  'metric_window_end','rule_code','rule_type','origin_scope',
  'metric_code','block_scope','support_only'
);

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'scout_liq_paid_history'
AND column_name IN (
  'scheme_version_id','rule_code','rule_type','origin_scope',
  'metric_code','block_scope','support_only'
);
```

**Health check:**
```bash
curl -s http://STAGING_HOST/scout-liq/health
```

**Smoke test (flujo completo en UI):**
1. Entrar a Centro Operativo — verificar carga de drivers.
2. Entrar a Liquidaciones — verificar listado de cortes.
3. Crear corte QA: `POST /scout-liq/cutoffs/from-cohort` con scheme_type=cabinet.
4. Preview — verificar pagables, bloqueados, explanation.
5. Exportar CSV y financiero.
6. Review + Approve.
7. Mark-paid (SOLO EN STAGING).
8. Validar paid_history creado.
9. Crear corte solapado — verificar doble pago bloqueado.
10. Query de duplicados — debe devolver 0.

**NO OLVIDAR:**
- NO marcar pagado en produccion.
- NO modificar module_ct_cabinet_drivers.
- NO modificar trips2025/trips2026.
- NO cambiar reglas productivas.
