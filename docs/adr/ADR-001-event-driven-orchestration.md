# ADR-001: Orquestación event-driven entre agentes

- **Estado:** Aceptada
- **Fecha:** 2026-04-07

## Contexto

La plataforma coordina múltiples agentes especializados (planificación, desarrollo, QA, seguridad, replanning y materialización en GitHub).  
Necesitamos desacoplar productores y consumidores para poder evolucionar el pipeline sin crear dependencias directas frágiles entre servicios.

## Decisión

Adoptar una arquitectura **event-driven** con RabbitMQ como bus y contratos tipados de eventos en `shared/contracts/events.py`.

## Consecuencias

### Positivas

- Acoplamiento bajo entre servicios y despliegue independiente.
- Mejor trazabilidad de decisiones (event log en memory service).
- Reintentos, replay parcial y análisis histórico más simples.

### Costes / trade-offs

- Mayor complejidad operacional (cola, idempotencia, orden de eventos).
- Necesidad de diseño explícito de contratos y versionado.
- Debugging distribuido más exigente que llamadas síncronas directas.

## Alternativas consideradas

- **Orquestación síncrona HTTP pura:** más simple al inicio, pero más acoplada y menos resiliente ante picos/fallos.
- **Monolito con workers internos:** menor coste inicial, peor separación de responsabilidades para escalar equipos y dominios.

