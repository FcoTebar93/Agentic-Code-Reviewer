# ADR-003: Servicio de memoria centralizado

- **Estado:** Aceptada
- **Fecha:** 2026-04-07

## Contexto

Todos los agentes necesitan acceso consistente a:

- eventos del pipeline,
- estado de tareas,
- memoria semántica,
- patrones históricos de fallo.

Permitir acceso directo de cada servicio a PostgreSQL/Qdrant/Redis aumentaría acoplamiento y divergencia en modelos.

## Decisión

Centralizar acceso en `memory_service` como fachada única y exponer APIs HTTP (`/events`, `/tasks`, `/semantic/search`, `/patterns/failures`, `/cache`).

## Consecuencias

### Positivas

- Contrato único de lectura/escritura para todos los agentes.
- Menor duplicación de lógica de persistencia.
- Facilita gobernanza de datos, observabilidad y evolución del esquema.

### Costes / trade-offs

- Nuevo punto crítico a escalar/proteger (cuello de botella potencial).
- Latencia adicional por salto de red interno.
- Exige diseño cuidadoso de retries/timeouts entre servicios.

## Alternativas consideradas

- **Acceso directo por servicio a cada datastore:** más rendimiento puntual, pero mayor complejidad sistémica y deuda de mantenimiento.
- **Memoria embebida por agente:** simple en local, inviable para consistencia global y analytics del pipeline.

