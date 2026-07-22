# Estándares

## Nombres

- Módulos en minúscula: `orden_service.py`.
- Funciones en snake_case: `calcular_total_orden`.
- Constantes en mayúscula: `METODOS_PAGO_VALIDOS`.

## Carpetas

Estructura futura sugerida:

- `routes/`
- `services/`
- `database/`
- `utils/`
- `templates/`
- `static/`

## Funciones

- Una función debe tener una responsabilidad clara.
- Helpers puros no deben abrir conexiones.
- Servicios pueden coordinar DB y reglas.
- Rutas deben ser delgadas en el futuro.

## SQL

- Usar queries parametrizadas.
- Mantener compatibilidad SQLite/PostgreSQL.
- Evitar concatenar valores de usuario.
- Encapsular SQL específico por motor.

## Errores

- Mensajes claros para operación.
- Logs útiles para diagnóstico.
- No exponer secretos.

## Commits

Formato sugerido:

```text
docs: crear base documental del POS
refactor: extraer helpers de pagos
fix: corregir validacion de refresco
```

## Documentación

- Documentar intención y riesgo.
- Mantener español claro.
- Separar descripción de observación.
- Actualizar contratos si cambia una API.

