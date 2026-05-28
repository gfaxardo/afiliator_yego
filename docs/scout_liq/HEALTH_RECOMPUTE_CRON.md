# Health Recompute — Cron Setup

Ejecuta el recompute completo de salud del Liquidador Scouts cada 30 minutos.

## Cron (Linux / WSL)

Agregar al crontab del usuario que ejecuta el backend:

```cron
*/30 * * * * cd /path/to/proyecto/backend && /path/to/python scripts/run_scout_liq_health_recompute.py >> /var/log/scout_liq_health_recompute.log 2>&1
```

Reemplazar:
- `/path/to/proyecto` → ruta real al proyecto
- `/path/to/python` → ruta al Python con el venv activo (ej: `/home/user/venv/bin/python`)

## Verificar

```bash
# Test manual
cd /path/to/proyecto/backend
python scripts/run_scout_liq_health_recompute.py

# Ver log
tail -f /var/log/scout_liq_health_recompute.log
```

## systemd (opcional, recomendado para produccion)

Crear archivo de servicio:
`/etc/systemd/system/scout-liq-health-recompute.service`

```ini
[Unit]
Description=Scout Liq Health Recompute
After=network.target

[Service]
Type=oneshot
User=appuser
WorkingDirectory=/path/to/proyecto/backend
ExecStart=/path/to/python scripts/run_scout_liq_health_recompute.py
StandardOutput=journal
StandardError=journal
```

Crear archivo de timer:
`/etc/systemd/system/scout-liq-health-recompute.timer`

```ini
[Unit]
Description=Scout Liq Health Recompute every 30 min
Requires=scout-liq-health-recompute.service

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
```

Activar:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now scout-liq-health-recompute.timer
systemctl status scout-liq-health-recompute.timer
```

## Que hace el script

1. Abre sesion DB (misma config que el backend)
2. Ejecuta recompute_derived() — los mismos 5 pasos del endpoint POST
3. Registra ejecucion en `scout_liq_job_runs` con `triggered_by='system'`
4. Detecta y registra eventos de salud en `scout_liq_health_events`
5. Actualiza `scout_liq_refresh_registry`
6. Imprime resumen operativo (sin credenciales)
7. Exit code 0 = OK/WARNING, 1 = FAILED

## Seguridad

- NO modifica `module_ct_cabinet_drivers` (solo SELECT)
- NO modifica `.env`
- NO expone DSN ni passwords en logs
- Solo INSERT en tablas propias `scout_liq_*`
