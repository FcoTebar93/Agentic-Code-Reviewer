## ADMADC – Plataforma agentica de Dev & QA

ADMADC es una **plataforma agentica de desarrollo de software**: un conjunto de microservicios que colaboran para:

- Entender un **prompt de alto nivel**.
- Generar un **plan de trabajo** y descomponerlo en tareas.
- **Escribir y editar código** usando LLMs y herramientas estáticas.
- Pasar por una **puerta de calidad (QA)** y una **puerta de seguridad**.
- Abrir **pull requests en GitHub**, siempre con **aprobación humana final**.

Todo el pipeline se ejecuta localmente con **Docker Compose**, usando un **bus de eventos**, un **almacén de memoria central** y un **frontend** para observar y controlar el flujo.

---

## Arquitectura general

La arquitectura se puede ver como una línea de ensamblaje impulsada por eventos:

- **Frontend (React/Vite)**
  - Dashboard para crear planes, ver eventos y tareas, revisar métricas de tokens y gestionar aprobaciones humanas (HITL).
  - Se comunica **solo** con el Gateway (HTTP + WebSocket).

- **Gateway Service (`gateway_service`)**
  - Única puerta de entrada HTTP/WS.
  - Expone:
    - `POST /api/plan` → envía la petición al Meta Planner.
    - `POST /api/replan` → confirma un replan sugerido por el Replanner.
    - `GET /api/events`, `GET /api/tasks/{plan_id}` → proxy al Memory Service.
    - `GET /api/plan_metrics/{plan_id}` → agrega métricas de tokens y estado del pipeline.
    - `GET /api/status` y `GET /api/approvals` → salud y aprobaciones pendientes.
    - WebSocket `/ws` → difunde todos los eventos y las aprobaciones pendientes a la UI.
  - Implementa la capa **Human‑In‑The‑Loop (HITL)**:
    - Recibe `security.approved`, genera `pr.pending_approval` y mantiene una cola de aprobaciones internas.
    - Tras la decisión humana en la UI:
      - Emite `pr.human_approved` (lo consume `github_service`).
      - O `pr.human_rejected`.
      - Emite también `pipeline.conclusion` con el resumen final del plan.

- **Meta Planner (`meta_planner`)**
  - Agente “arquitecto” que:
    - Recibe un prompt de usuario vía `POST /plan` o evento `plan.requested`.
    - Usa el LLM + memoria (eventos y búsqueda semántica) para crear un **plan** y un conjunto de **tareas**.
  - Publica:
    - `plan.created` con la definición del plan.
    - `task.assigned` por cada tarea (con `group_id` y metadatos del archivo objetivo).
    - `metrics.tokens_used` por cada llamada al LLM del planner.
  - Gestiona **replanning**:
    - Recibe `plan.revision_suggested` (desde Replanner) y `plan.revision_confirmed` (desde Gateway/API).
    - Reconstruye prompts enriquecidos y crea **nuevos planes** a partir de resultados fallidos.

- **Spec Service (`spec_service`)**
  - Agente de **especificaciones y tests**.
  - Escucha `task.assigned` y genera:
    - Especificaciones de alto nivel y sugerencias de pruebas.
    - Evento `spec.generated` con esa información.
  - En modo “save” puede evitar gastar tokens en tareas triviales (por ejemplo, tareas muy cortas).

- **Dev Service (`dev_service`)**
  - Agente “desarrollador”.
  - Escucha `task.assigned` (junto con `spec.generated` cuando existe).
  - Para cada tarea:
    - Construye un contexto rico:
      - Eventos recientes del plan (`/events` en Memory Service).
      - Estado y snapshots de tareas (`/tasks/{plan_id}`).
      - Ficheros de proyecto (`list_project_files`).
      - Contenido actual de archivos (`read_file`).
      - Especificación generada por `spec_service`.
    - Usa el LLM y herramientas (`run_tests`, etc.) para **generar o editar código**.
  - Publica:
    - `code.generated` con el código propuesto, reasoning y metadata (lenguaje, ruta, intento de QA, etc.).
    - `metrics.tokens_used` por cada llamada al LLM.
  - Actualiza tareas en Memory Service (`/tasks`) con estados `in_progress` / `completed`.

- **QA Service (`qa_service`)**
  - Puerta de **calidad** entre Dev y GitHub.
  - Escucha `code.generated`.
  - Flujo:
    1. Ejecuta herramientas estáticas (por configuración):
       - `python_lint` (ruff).
       - `python_security_scan` (Bandit).
       - `semgrep_scan` (multi‑lenguaje).
       - Opcionales: linters JS/TS y Java (`js_ts_lint`, `java_lint`).
    2. Ejecuta una revisión LLM estructurada con:
       - Contexto del plan y la tarea.
       - Razonamiento del Dev.
       - Resultados de linters y herramientas.
    3. Produce un veredicto estructurado:
       - `qa.passed` / `qa.failed`.
       - `ISSUES`, `REQUIRED_CHANGES`, `OPTIONAL_IMPROVEMENTS`.
  - En PASS:
    - Marca la tarea como `qa_passed` en Memory Service.
    - Cuando **todas** las tareas de un plan están en `qa_passed`, agrega los cambios y emite `pr.requested`.
  - En FAIL:
    - Reencola la tarea como `task.assigned` con `qa_feedback` (hasta `MAX_QA_RETRIES`).
    - Si se agotan los intentos, emite `qa.failed`.

- **Security Service (`security_service`)**
  - Puerta de **seguridad** previa a la aprobación humana.
  - Escucha `pr.requested`.
  - Aplica un escaneo determinista:
    - Reglas basadas en patrones/regex propias.
    - Opcionalmente Bandit y Semgrep (configurables por entorno).
  - Publica:
    - `security.approved` con contexto completo del PR (archivos, reasoning, severidad).
    - O `security.blocked` con detalle de los problemas detectados.
  - Registra sus resultados en Memory Service como eventos.

- **Replanner Service (`replanner_service`)**
  - Agente especializado en **replanning**.
  - Escucha:
    - `qa.failed`.
    - `security.blocked`.
  - Usa:
    - LLM.
    - Memoria semántica de resultados anteriores (`semantic_outcome_memory`).
  - Decide si es necesario **replantear el plan**:
    - Si sí, emite `plan.revision_suggested` con:
      - Severidad.
      - Razones.
      - Grupos de archivos afectados.
  - También emite `metrics.tokens_used` por cada análisis de outcome.

- **Memory Service (`memory_service`)**
  - Fachada única sobre:
    - **PostgreSQL**: eventos y estado de tareas.
    - **Qdrant**: memoria semántica de eventos y patrones de fallo.
    - **Redis**: caché y pequeñas claves de estado.
  - API HTTP:
    - `POST /events` / `GET /events` → almacén de eventos con filtros (`plan_id`, `event_type`, `limit`, etc.).
    - `POST /tasks` / `GET /tasks/{plan_id}` → estado y snapshots de tareas.
    - `POST /cache` / `GET /cache/{key}` → caché genérico sobre Redis.
    - `POST /semantic/search` → búsqueda semántica sobre eventos.
    - `GET /patterns/failures` → patrones agregados de fallos históricos.
  - Todos los agentes leen/escriben memoria **solo** a través de este servicio.

- **GitHub Service (`github_service`)**
  - Agente de **materialización** en Git.
  - Escucha `pr.human_approved` (tras la aprobación en Gateway/UI).
  - Para cada aprobación:
    - Recupera el repo (clonado o workspace local).
    - Escribe cambios en disco.
    - Crea rama, commit y PR en GitHub (usando `PyGithub`) si hay `GITHUB_TOKEN`.
    - O, si no hay token, aplica cambios en un workspace local para revisión manual.
  - Publica `pr.created` con información del PR resultante.

- **Shared libs (`shared/`)**
  - `shared/contracts/events.py` → contratos tipados de todos los eventos (plan, tareas, QA, seguridad, PRs, métricas…).
  - `shared/utils` → EventBus (aio‑pika), memoria de corto plazo, helpers HTTP para hablar con Memory Service, etc.
  - `shared/tools` → registro y ejecución de herramientas (`read_file`, `list_project_files`, `run_tests`, linters, semgrep, búsqueda semántica…).
  - `shared/llm_adapter` → factoría de proveedores LLM (OpenAI, Groq, Gemini, OpenRouter, local…) con caché opcional en Redis.
  - `shared/logging`, `shared/observability` → logging estructurado y métricas Prometheus.
  - SLIs acordados para paneles y alertas: `infrastructure/observability/SLIS.md` (dashboard Grafana **ADMADC · SLIs**, reglas Prometheus en `infrastructure/prometheus/rules/slis_alerts.yml`).

- **Frontend (`frontend/`)**
  - Aplicación React/TypeScript + Vite.
  - Usa Tailwind CSS para el diseño.
  - Se conecta al Gateway vía:
    - `VITE_GATEWAY_HTTP_URL`.
    - `VITE_GATEWAY_WS_URL`.

- **CLI (`scripts/admadc_cli.py`)**
  - Cliente ligero en Python para el Gateway.
  - Comandos principales:
    - `status`, `plan`, `events`, `tasks`, `metrics`, `approvals`, `approve`, `reject`, `replan`.
  - Usa la variable `ADMADC_GATEWAY_URL` (por defecto `http://localhost:8080`).

---

## Librerías y tecnologías principales

- **Backend (Python)**
  - **FastAPI**, **Uvicorn** → APIs HTTP de cada servicio.
  - **Pydantic v2** → modelos de datos y contratos de eventos.
  - **aio‑pika** → integración asíncrona con **RabbitMQ** (EventBus).
  - **httpx** → llamadas HTTP entre servicios (Gateway ↔ Meta Planner/Memory, Agentes ↔ Memory).
  - **SQLAlchemy [asyncio]**, **asyncpg** → acceso asíncrono a PostgreSQL.
  - **qdrant‑client** → memoria vectorial (Qdrant).
  - **redis[hiredis]** → caché y estados ligeros.
  - **prometheus‑client** → métrica `/metrics` en cada servicio.
  - **OpenAI Python SDK** → acceso unificado a LLMs OpenAI‑compatibles (OpenAI, Groq, Gemini, OpenRouter, servidores locales).
  - **PyGithub** → integración con GitHub para crear PRs.
  - **Herramientas de calidad y seguridad**:
    - `ruff`, `bandit`, `semgrep`.
    - Opcionalmente ESLint y `javac` (JS/TS y Java).

- **Frontend**
  - **React**, **React DOM**.
  - **TypeScript**.
  - **Vite** + `@vitejs/plugin-react`.
  - **Tailwind CSS**, **PostCSS**, **Autoprefixer**.

- **Infraestructura**
  - **Docker** y **Docker Compose**.
  - **PostgreSQL** (almacén relacional).
  - **RabbitMQ** (bus de eventos).
  - **Qdrant** (vector DB).
  - **Redis** (caché).
  - **Prometheus** + **Grafana** + **Loki** / **Promtail** (observabilidad).

---

## Despliegue local

1. **Clonar el repositorio**

```bash
git clone https://github.com/FcoTebar93/Agentic-Project.git
cd Agentic-Project
```

2. **Configurar variables de entorno**

- Copia el archivo de ejemplo:

```bash
cp .env.example .env
```

- Ajusta en `.env` como mínimo:
  - **Base de datos y colas**
    - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
    - `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`.
    - `REDIS_PASSWORD`.
    - `RABBITMQ_URL`, `DATABASE_URL`, `QDRANT_URL`, `REDIS_URL`, `MEMORY_SERVICE_URL`.
  - **LLM global y tiering**
    - `LLM_PROVIDER` (p. ej. `mock`, `local`, `groq`…).
    - `LLM_API_KEY` / `OPENAI_API_KEY` (según proveedor).
    - `LLM_BASE_URL` (para servidores locales tipo Ollama/LM Studio).
    - `LLM_MODEL`.
    - Opcional: `META_PLANNER_LLM_PROVIDER`, `DEV_LLM_PROVIDER`, `QA_LLM_PROVIDER`, `REPLANNER_LLM_PROVIDER`.
    - Costes estimados:
      - `LLM_PROMPT_PRICE_PER_1K`, `LLM_COMPLETION_PRICE_PER_1K` (solo para métricas/UI).
  - **GitHub**
    - `GITHUB_TOKEN` (si quieres crear PRs reales).
    - `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`.

3. **Levantar el stack con Docker Compose**

```bash
docker compose up --build
```

Esto arranca:

- Servicios agenticos: gateway, meta_planner, spec, dev, qa, security, replanner, memory, github.
- Servicios de soporte: PostgreSQL, RabbitMQ, Redis, Qdrant.
- Observabilidad: Prometheus, Grafana, Loki (logs vía Promtail).
- Frontend: panel web.

4. **Acceder a la plataforma**

- **Frontend**: abre en tu navegador la URL expuesta en `docker-compose.yml` (por defecto suele ser `http://localhost:3001`).
  - Desde ahí puedes:
    - Crear nuevos planes.
    - Observar el flujo plan → tareas → dev → QA → seguridad.
    - Gestionar aprobaciones humanas de PRs.
- **Gateway API** (para debug o uso directo):
  - HTTP: `http://localhost:8080`.
  - WebSocket: `ws://localhost:8080/ws`.

5. **Opcional: habilitar linters JS/TS y Java en QA**

- Edita `infrastructure/docker/qa_service/Dockerfile` y descomenta el bloque de instalación de:
  - `nodejs`, `npm`, `openjdk-17-jdk`, `eslint`, `typescript`.
- Reconstruye y levanta solo QA si lo necesitas:

```bash
docker compose build qa_service
docker compose up qa_service
```

---

## Variables de entorno (resumen)

### Infraestructura básica

- **PostgreSQL**
  - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
- **RabbitMQ**
  - `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`, `RABBITMQ_URL`.
- **Redis**
  - `REDIS_PASSWORD`, `REDIS_URL`.
- **Memory Service**
  - `DATABASE_URL`, `QDRANT_URL`, `MEMORY_SERVICE_URL`.

### LLM global y por servicio

- **Global**
  - `LLM_PROVIDER` (`mock`, `openai`, `groq`, `gemini`, `openrouter`, `local`, …).
  - `LLM_API_KEY` / `OPENAI_API_KEY`.
  - `LLM_BASE_URL` (para `local`).
  - `LLM_MODEL`.
  - `LLM_PROMPT_PRICE_PER_1K`, `LLM_COMPLETION_PRICE_PER_1K`.

- **Tiering por servicio (opcionales)**
  - `META_PLANNER_LLM_PROVIDER`.
  - `DEV_LLM_PROVIDER`.
  - `QA_LLM_PROVIDER`.
  - `REPLANNER_LLM_PROVIDER`.

### Config específica de servicios (ejemplos)

- **Gateway**
  - `RABBITMQ_URL`, `MEMORY_SERVICE_URL`, `META_PLANNER_URL`.
  - `LOG_LEVEL`.
  - TTL e idempotencia configurables en código (por ejemplo, para `/api/plan`).

- **Meta Planner**
  - `RABBITMQ_URL`, `MEMORY_SERVICE_URL`.
  - `META_PLANNER_LLM_PROVIDER` o fallback a `LLM_PROVIDER`.
  - Parámetros de agente: nombre, objetivo, estrategia, presupuesto de tokens.

- **Dev Service**
  - `RABBITMQ_URL`, `MEMORY_SERVICE_URL`, `REDIS_URL`.
  - `DEV_LLM_PROVIDER` o `LLM_PROVIDER`.
  - `DEV_ENABLE_AUTO_TESTS` y comandos:
    - `DEV_TEST_COMMAND_PYTHON`.
    - `DEV_TEST_COMMAND_JAVASCRIPT`.
    - `DEV_TEST_COMMAND_TYPESCRIPT`.
    - `DEV_TEST_COMMAND_JAVA`.

- **QA Service**
  - `RABBITMQ_URL`, `MEMORY_SERVICE_URL`, `REDIS_URL`.
  - `QA_LLM_PROVIDER` o `LLM_PROVIDER`.
  - `MAX_QA_RETRIES`.
  - Flags de herramientas:
    - `QA_ENABLE_SEMGREP`.
    - `QA_ENABLE_JS_LINT`.
    - `QA_ENABLE_JAVA_LINT`.

- **Security Service**
  - `RABBITMQ_URL`, `MEMORY_SERVICE_URL`, `REDIS_URL`.
  - `SECURITY_ENABLE_BANDIT`, `SECURITY_ENABLE_SEMGREP`.

- **Replanner Service**
  - `RABBITMQ_URL`, `MEMORY_SERVICE_URL`.
  - `REPLANNER_LLM_PROVIDER` o `LLM_PROVIDER`.

- **Memory Service**
  - `DATABASE_URL`, `QDRANT_URL`, `REDIS_URL`, `RABBITMQ_URL`.
  - `MEMORY_STARTUP_RETRIES`, `MEMORY_STARTUP_DELAY_SEC` para reintentos de arranque robustos.

- **GitHub Service**
  - `RABBITMQ_URL`.
  - `GITHUB_TOKEN`, `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`.
  - `GITHUB_WORKSPACE` (workspace local para cambios si no hay integración real con GitHub).

- **Frontend / CLI**
  - `VITE_GATEWAY_HTTP_URL`, `VITE_GATEWAY_WS_URL`.
  - `ADMADC_GATEWAY_URL` (CLI).

---

## Descripción de cada agente/servicio

### Gateway Service

- **Rol**: puerta única para el frontend y capa HITL.
- **Responsabilidades**:
  - Exponer endpoints HTTP para planes, métricas, eventos, tareas y aprobaciones.
  - Gestionar conexiones WebSocket y retransmitir todos los eventos del bus.
  - Convertir `security.approved` en `pr.pending_approval` y orquestar el flujo de aprobación humana.
  - Emitir `pr.human_approved` / `pr.human_rejected` y `pipeline.conclusion`.

### Meta Planner Service

- **Rol**: agente de planificación.
- **Responsabilidades**:
  - Convertir un prompt de alto nivel en un plan detallado y una lista de tareas.
  - Usar memoria semántica y eventos recientes para evitar planes redundantes.
  - Publicar `plan.created` y `task.assigned`.
  - Gestionar re‑planning a partir de `plan.revision_suggested` y `plan.revision_confirmed`.

### Spec Service

- **Rol**: generador de especificaciones y tests sugeridos.
- **Responsabilidades**:
  - Escuchar `task.assigned`.
  - Producir `spec.generated` con especificaciones, criterios de aceptación y tests sugeridos.
  - Aportar contexto adicional al Dev Service y al QA.

### Dev Service

- **Rol**: agente desarrollador.
- **Responsabilidades**:
  - Consumir `task.assigned` (y `spec.generated` cuando exista).
  - Construir un contexto completo (memoria, archivos, specs, eventos) para cada tarea.
  - Llamar al LLM, ejecutar herramientas y opcionalmente tests automáticos.
  - Publicar `code.generated` y `metrics.tokens_used`.
  - Mantener el estado de tareas en Memory Service.

### QA Service

- **Rol**: puerta de calidad.
- **Responsabilidades**:
  - Recibir `code.generated`.
  - Ejecutar linters y herramientas estáticas (Python, multi‑lenguaje y opcionales JS/TS/Java).
  - Ejecutar una revisión LLM estructurada.
  - Emitir `qa.passed` / `qa.failed`, reencolar tareas con feedback o marcar `qa_passed`.
  - Cuando todo un plan pasa QA, agregar cambios y emitir `pr.requested`.

### Security Service

- **Rol**: filtro de seguridad previo a PR/HITL.
- **Responsabilidades**:
  - Escuchar `pr.requested`.
  - Escanear los cambios con reglas deterministas (y opcionalmente Bandit/Semgrep).
  - Emitir `security.approved` (con contexto de PR) o `security.blocked`.
  - Registrar resultados en Memory Service.

### Replanner Service

- **Rol**: agente de replanning inteligente.
- **Responsabilidades**:
  - Escuchar `qa.failed` y `security.blocked`.
  - Usar memoria semántica de outcomes para entender patrones de fallo.
  - Decidir si hace falta replantear el plan y, en ese caso, emitir `plan.revision_suggested`.

### Memory Service

- **Rol**: almacén de memoria y estado centralizado.
- **Responsabilidades**:
  - Ser la única puerta hacia:
    - Eventos (event log).
    - Estado de tareas.
    - Búsqueda semántica de recuerdos.
    - Caché de claves.
  - Exponer API HTTP (`/events`, `/tasks`, `/semantic/search`, `/cache`, `/patterns/failures`).
  - Arrancar de forma robusta con reintentos configurables.

### GitHub Service

- **Rol**: ejecutor Git/PR.
- **Responsabilidades**:
  - Consumir `pr.human_approved`.
  - Materializar cambios en un repositorio Git:
    - Crear ramas, escribir archivos, hacer commit/push.
    - Crear PRs en GitHub (si hay `GITHUB_TOKEN`).
    - O escribir en un workspace local para revisión manual.
  - Publicar `pr.created`.

### Frontend

- **Rol**: panel de control y observabilidad.
- **Responsabilidades**:
  - Lanzar nuevos planes y replans.
  - Visualizar:
    - Estado de planes, tareas y eventos.
    - Métricas de tokens y duración del pipeline.
    - Razonamiento de Dev/QA/Seguridad.
  - Gestionar aprobaciones humanas de PRs (HITL).

### CLI (`scripts/admadc_cli.py`)

- **Rol**: acceso por terminal al Gateway.
- **Responsabilidades**:
  - Permitir:
    - Crear planes (`plan`).
    - Consultar eventos (`events`) y tareas (`tasks`).
    - Ver métricas de un plan (`metrics`).
    - Listar y gestionar aprobaciones (`approvals`, `approve`, `reject`).
    - Confirmar replans (`replan`).
  - Ser una alternativa rápida al frontend para usuarios avanzados.

---

Con esto, el README refleja el estado actual de la plataforma, sus agentes y la forma recomendada de desplegarla y configurarla en local.

