# Historial Técnico

## Estado actual

El proyecto nace como POS Flask monolítico para Neko Wok / China House. La mayor parte del sistema vive en `web_app.py`.

## Scripts locales

Existen scripts locales para impresión:

- Comandas de cocina.
- Facturas.

Estos scripts consultan rutas del servidor desplegado y usan impresoras locales Windows.

## Compatibilidad de base de datos

El sistema soporta:

- SQLite local.
- PostgreSQL en Render mediante `DATABASE_URL`.

## Motivo de esta documentación

La documentación se crea para preparar una modularización segura y convertir el sistema en una base profesional para NekoPOS.

## Próximo paso sugerido

Iniciar modularización por fases:

1. Constantes.
2. Helpers puros.
3. Capa de base de datos.
4. Servicios.
5. Rutas.
6. Templates/static.

No mover rutas críticas al inicio.

