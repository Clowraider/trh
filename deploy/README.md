# Deploy TRH (systemd + nginx)

## 1) Servicio systemd para el panel

Copiar unidad:

```bash
sudo cp deploy/trh-panel.service /etc/systemd/system/trh-panel.service
sudo systemctl daemon-reload
sudo systemctl enable trh-panel
sudo systemctl start trh-panel
sudo systemctl status trh-panel
```

Logs:

```bash
journalctl -u trh-panel -f
```

## 2) Nginx como reverse proxy

Copiar config:

```bash
sudo cp deploy/nginx-trh.conf /etc/nginx/sites-available/trh
sudo ln -s /etc/nginx/sites-available/trh /etc/nginx/sites-enabled/trh
sudo nginx -t
sudo systemctl reload nginx
```

Con esto, nginx recibe en `:80` y reenvía al panel Flask en `127.0.0.1:5000`.

## 3) Operación recomendada

- `proceso.py` por cron (pipeline)
- `app.py` como servicio systemd (panel siempre arriba)
- nginx expone el panel hacia red

## Notas

- Si tu usuario NO es `ren`, editá `User=` en `deploy/trh-panel.service`.
- Si el repo no está en `/home/ren/TRH`, ajustá `WorkingDirectory`, `EnvironmentFile`, `PATH` y `ExecStart`.
- Para HTTPS (recomendado), luego agregá Certbot sobre este server block.
