# ADR-002: Human-in-the-loop antes de crear PR

- **Estado:** Aceptada
- **Fecha:** 2026-04-07

## Contexto

El sistema puede generar cambios de código de forma autónoma, pero el objetivo del producto no es automatizar sin control, sino acelerar entrega manteniendo gobernanza y seguridad.

## Decisión

Introducir un paso de aprobación humana obligatorio después de `security.approved` y antes de `pr.human_approved` / creación final de PR.

## Consecuencias

### Positivas

- Reduce riesgo de merges no deseados o cambios fuera de contexto de negocio.
- Mejora auditabilidad para equipos y stakeholders.
- Alinea la plataforma con adopción progresiva en entornos reales.

### Costes / trade-offs

- Incrementa lead time frente a automatización totalmente autónoma.
- Requiere UX clara en dashboard y gestión de cola de aprobaciones.
- Introduce dependencia en disponibilidad de reviewer humano.

## Alternativas consideradas

- **Automerge tras QA+security:** más rápido, pero con mayor riesgo reputacional y operativo.
- **Aprobación solo en producción:** simplifica dev, pero no crea hábito de gobernanza temprana.

