# ADMADC CLI

Cliente ligero por línea de comandos para operar la plataforma vía Gateway API.

## Requisitos

- Python 3.10+
- `httpx`: `pip install httpx` (o usar el entorno del proyecto donde ya está)
- (Opcional, para seguimiento en tiempo real) `websockets`: `pip install websockets`

## Uso

Variable de entorno opcional:

- `ADMADC_GATEWAY_URL`: URL base del gateway (por defecto: `http://localhost:8080`)

### Comandos

| Comando | Descripción |
|--------|-------------|
| `python scripts/admadc_cli.py status` | Estado del gateway (conexiones WS, aprobaciones pendientes) |
| `python scripts/admadc_cli.py plan --prompt "..."` | Crear un plan (opciones: `--project`, `--repo-url`, `--mode normal\|ahorro`, `--watch`) |
| `python scripts/admadc_cli.py events [--limit 20]` | Listar eventos recientes |
| `python scripts/admadc_cli.py tasks <plan_id>` | Tareas de un plan |
| `python scripts/admadc_cli.py metrics <plan_id>` | Métricas del plan (tokens, estado del pipeline, duración) |
| `python scripts/admadc_cli.py approvals` | Listar aprobaciones PR pendientes (HITL) |
| `python scripts/admadc_cli.py approve <approval_id>` | Aprobar un PR |
| `python scripts/admadc_cli.py reject <approval_id>` | Rechazar un PR |
| `python scripts/admadc_cli.py replan --payload '{"original_plan_id":"..."}'` | Confirmar un replan (payload completo de `plan.revision_suggested`) |
| `python scripts/admadc_cli.py watch-plan <plan_id>` | Seguir en tiempo real los eventos de un plan (vía WebSocket, requiere `websockets`) |

### Ejemplos

```bash
# Crear plan en modo ahorro
python scripts/admadc_cli.py plan --prompt "Add a /health endpoint" --mode ahorro

# Crear plan y seguirlo en tiempo real en el mismo comando
python scripts/admadc_cli.py plan --prompt "Add a /health endpoint" --watch

# Ver métricas del último plan (usar plan_id devuelto por plan)
python scripts/admadc_cli.py metrics abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Confirmar replan (el payload suele venir del evento plan.revision_suggested en la UI)
echo '{"original_plan_id":"...", "new_plan_id":"...", "reason":"...", "severity":"high", "suggestions":[]}' | python scripts/admadc_cli.py replan

# Seguir en tiempo real un plan concreto
python scripts/admadc_cli.py watch-plan abc12345-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```
