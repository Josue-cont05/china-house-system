# Guía para Codex

## Antes de trabajar

Codex debe leer primero:

1. `PROJECT_CONTEXT.md`
2. `DESARROLLO_POS.md`
3. Documento específico en `docs/` según la tarea.

## Reglas

- Nunca modificar rutas críticas sin autorización.
- Nunca cambiar JSON de scripts locales sin autorización.
- Nunca hacer refactor masivo.
- Nunca mezclar refactor con nueva funcionalidad.
- Siempre preservar SQLite y PostgreSQL.
- Siempre preservar Render.
- Siempre trabajar con cambios pequeños.
- Nunca tocar base de datos real sin respaldo.

## Antes de modificar, responder

```text
OBJETIVO
ARCHIVOS A MODIFICAR
FUNCIONES AFECTADAS
RIESGO
PLAN
PRUEBAS
```

## Después de modificar, responder

```text
RESUMEN
ARCHIVOS MODIFICADOS
PRUEBAS RECOMENDADAS
RIESGOS
```

## Buen patrón de trabajo

1. Leer contexto.
2. Revisar `git status`.
3. Identificar rutas y funciones afectadas.
4. Hacer un cambio pequeño.
5. Verificar sintaxis.
6. Recomendar prueba manual.

## Prohibiciones prácticas

- No mover `/cobrar` al inicio de una modularización.
- No mover `/orden/<id>` sin pruebas completas.
- No cambiar `/ordenes_cocina` ni `/facturas_pendientes` sin probar scripts.
- No cambiar `web_app.py` como entrada de Render sin plan.

