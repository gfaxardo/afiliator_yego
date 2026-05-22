# SCOUT LIQ — Health Refresh Automático

## Resumen

El Health Registry del Liquidador de Calidad Scouts Yego registra snapshots de fuentes,
detecta eventos de salud operativa y calcula un score ejecutivo.

El refresh debe ejecutarse periódicamente para mantener actualizados:
- Registry de fuentes (lag, estado)
- Eventos de salud (alertas)
- Score global

---

## 1. Ejecución manual

```bash
cd /ruta/proyecto/afiliator_yego
python scripts/scout_liq_health_refresh.py
```

Salida esperada (exit code 0):
```
Health Refresh OK
==================================================
  evaluated_at:    2026-05-21
  global_status:   WARNING
  score:           72
  events_open:     3
  events_created:  1
  events_resolved: 2
  source_status:    BLOCKED
  source_lag_days:  360
  duration_ms:      4521
==================================================
```

Si falla (exit code 1):
```
Health Refresh FAILED
==================================================
  error:        relation "scout_liq_health_events" does not exist
  duration_ms:  120
==================================================
```

---

## 2. Cron Linux (recomendado)

Cada 30 minutos:

```cron
*/30 * * * * cd /ruta/proyecto/afiliator_yego && /ruta/venv/bin/python scripts/scout_liq_health_refresh.py >> logs/scout_liq_health_refresh.log 2>&1
```

Crear directorio de logs:
```bash
mkdir -p logs
```

---

## 3. Systemd Timer (opcional)

### Servicio: `/etc/systemd/system/scout-liq-health-refresh.service`

```ini
[Unit]
Description=Scout Liq Health Refresh
After=network.target

[Service]
Type=oneshot
User=deploy
WorkingDirectory=/ruta/proyecto/afiliator_yego
ExecStart=/ruta/venv/bin/python scripts/scout_liq_health_refresh.py
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Timer: `/etc/systemd/system/scout-liq-health-refresh.timer`

```ini
[Unit]
Description=Scout Liq Health Refresh Timer
Requires=scout-liq-health-refresh.service

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

### Activar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable scout-liq-health-refresh.timer
sudo systemctl start scout-liq-health-refresh.timer
sudo systemctl status scout-liq-health-refresh.timer
```

---

## 4. Endpoint HTTP

También disponible via API:

```
POST /scout-liq/health/registry/refresh
```

Respuesta:
```json
{
  "score": {
    "score": 72,
    "status": "WARNING",
    ...
  },
  "registry": {
    "refreshed_at": "2026-05-21T14:30:00",
    "entries": [...],
    "total": 5
  },
  "events_detected": {
    "new_events": 1,
    "events": [...]
  },
  "events_resolved": {
    "resolved_count": 2
  },
  "cycle_completed_at": "2026-05-21T14:32:00",
  "_timing_ms": 4521
}
```

---

## 5. Qué hace cada etapa

| Etapa | Descripción | Tablas |
|--------|-------------|--------|
| `refresh_registry_snapshot` | Evalúa lag de cada fuente (source_table, assignments, cutoff_runs, paid_history, import_batches) | scout_liq_refresh_registry |
| `detect_health_events` | Detecta eventos: source_lag >= 4d, sin carga scouts 7d, drivers sin scout >20%, cohortes problemáticas | scout_liq_health_events |
| `resolve_recovered_events` | Cierra eventos abiertos cuya condición ya no aplica | scout_liq_health_events |
| `compute_health_score_lite` | Calcula score 0-100 a partir de source, scouts, jobs y eventos abiertos | (solo lectura) |

---

## 6. Notas

- Las tablas `scout_liq_refresh_registry` y `scout_liq_health_events` se crean con la migración 014.
- Si alguna etapa falla, las demás continúan (partial health mode).
- El script es idempotente: no duplica eventos ya abiertos.
- No modifica `module_ct_cabinet_drivers` ni tablas de liquidación.
- No imprime credenciales ni connection strings.
