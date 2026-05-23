# Attribution Reconciliation — Operacion Diaria

## Proposito
Este documento describe el flujo operativo diario del modulo de Attribution Reconciliation & Governance en AFILIATOR. Cubre como mantener la vista materializada actualizada, interpretar el dashboard de integridad, y diagnosticar operational gaps antes de usarlos como base de pago.

---

## 1. Flujo Diario

### 1.1 Inicio del dia — Verificar frescura
1. Abrir `AttributionIntegrityDashboard` en el frontend.
2. Revisar la barra de estado de frescura:
   - **Actualizado (verde):** Datos frescos (< 60 min). OK.
   - **Desactualizado (ambar):** Datos entre 60 min y 24h. Refrescar manualmente.
   - **Critico (rojo):** Datos con > 24h de antiguedad. **NO usar para pago.**
   - **Error (rojo):** Fallo el ultimo refresh. Revisar logs y reintentar.
   - **Nunca refrescado:** La vista nunca se ha refrescado. Ejecutar refresh.

3. Si el estado no es `fresh`, hacer click en **"Refrescar Vista"**.
   - El boton ejecuta `POST /scout-liq/reconciliation/refresh-view`.
   - El refresh queda registrado en `scout_liq_reconciliation_refresh_log`.
   - Si falla, se muestra el mensaje de error. Revisar logs del backend.

### 1.2 Revisar Integridad
1. **KPIs principales** (tarjetas superiores):
   - **Integridad:** % de observados validados vs total.
   - **Sin Atribucion:** tasa de drivers sin atribucion observada.
   - **Operational Gaps:** drivers en fuente oficial sin match en observadas.

2. **Aging de pendientes:** revisar items con > 3 dias sin resolver.

### 1.3 Diagnosticar Operational Gaps
El panel de **"Diagnostico de Operational Gaps"** desglosa los gaps por:
- **con_trips_recientes:** Drivers en fuente que tienen viajes pero no atribucion observada oficial.
- **sin_atribucion_observada:** Drivers en fuente sin ningun registro en observadas.
- **con_asignacion_activa:** Drivers con asignacion a scout activa pero sin match oficial.
- **por_origen_X:** Gaps segmentados por origen.

**Regla de interpretacion:** NO asumir que todos los operational gaps representan perdida real. Muchos pueden ser drivers historicos, fuera de ventana de corte, o sin relacion con fleet/cabinet.

### 1.4 Revisar Cola de Observados
1. Ir a `ObservedReviewQueue`.
2. Filtrar por `review_status = Pendiente`.
3. Para cada item:
   - Verificar `confidence` (HIGH > MEDIUM > MANUAL REVIEW).
   - Revisar `classification`.
   - Usar botones **Approve / Reject / Merge** segun corresponda.
4. **Todas las acciones quedan registradas en `scout_liq_reconciliation_audit` con `actor = system_operator`.**

---

## 2. Endpoints Operativos

### 2.1 Refresh de Vista Materializada
```http
POST /scout-liq/reconciliation/refresh-view
```
- Refresca `scout_liq_attribution_reconciliation`.
- Registra log en `scout_liq_reconciliation_refresh_log`.
- Devuelve: `{ status, duration_ms, row_count }`.
- Es seguro ejecutar concurrentemente (usa `CONCURRENTLY`, fallback sin).

### 2.2 Verificar Frescura
```http
GET /scout-liq/reconciliation/freshness
```
- Devuelve: `{ last_refreshed_at, age_minutes, status, last_error, row_count }`.
- Status puede ser: `fresh`, `stale`, `stale_critical`, `never_refreshed`, `error`.

### 2.3 Diagnostico de Operational Gaps
```http
GET /scout-liq/reconciliation/operational-gaps/diagnostic
```
- Devuelve desglose segmentado: total, por origen, con trips, con asignacion, etc.

### 2.4 Acciones de Reconciliacion
```http
POST /scout-liq/reconciliation/{id}/approve
POST /scout-liq/reconciliation/{id}/reject
POST /scout-liq/reconciliation/{id}/merge
```
- Body: `{ reason, assign_scout (solo merge) }`.
- Actor siempre es `system_operator` (no se acepta desde el frontend).
- Cada accion crea un registro en `scout_liq_reconciliation_audit`.

---

## 3. Migraciones

### Migraciones pendientes a ejecutar:
```bash
cd backend
alembic upgrade head
```

Esto aplicara la migracion `021_add_reconciliation_refresh_log` que crea la tabla de log de refresh.

---

## 4. Comandos de Verificacion

### Backend
```bash
cd backend
python -m compileall app
pytest test_reconciliation_qa.py -v --tb=short
```

### Frontend
```bash
cd frontend
npm run build
```

---

## 5. Troubleshooting

| Problema | Causa probable | Solucion |
|---|---|---|
| Dashboard muestra "Nunca refrescado" | Vista nunca se ha refrescado | Ejecutar refresh manual |
| Refresh falla con error | MV corrupta o sin datos | Revisar logs backend, verificar que la tabla `scout_liq_observed_affiliations` tiene datos |
| Operational gaps muy altos | Puede ser normal si hay muchos drivers historicos | Revisar el panel de diagnostico por origen/ventana |
| Audit trail muestra "system_operator" | **Es lo esperado.** El sistema no tiene auth por usuario. | No requiere accion |
| Stale > 24h | No se ha refrescado manualmente | Ejecutar refresh y considerar automatizar con cron externo |

---

## 6. Seguridad del Audit Trail

- El campo `actor` en `scout_liq_reconciliation_audit` **NO es manipulable desde el frontend**.
- Siempre se registra como `"system_operator"`.
- El unico input del frontend aceptado en acciones de reconciliacion es `reason` (motivo).
- Esto garantiza que el audit trail no puede ser falseado por quien opera la UI.

---

## 7. Criterios GO/NO GO para Pago de Observados

| Condicion | Estado |
|---|---|
| MV frescura < 60 min | GO |
| MV frescura 60 min - 24h | GO con advertencia |
| MV frescura > 24h o error | NO GO |
| Operational gaps sin diagnosticar | NO GO |
| Audit trail con actor `system_operator` | GO (es lo esperado) |
| Panel de diagnostico muestra gaps por origen | GO (datos segmentados disponibles) |
