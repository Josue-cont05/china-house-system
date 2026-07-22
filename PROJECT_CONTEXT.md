# Contexto del Proyecto POS

## Qué es

Este proyecto es un POS Flask para Neko Wok / China House. Actualmente funciona como una aplicación monolítica concentrada principalmente en `web_app.py`.

Su objetivo futuro es evolucionar hacia un producto modular llamado provisionalmente **NekoPOS**, reutilizable para otros restaurantes sin perder compatibilidad con la operación actual.

## Estado actual

- `web_app.py` contiene rutas, lógica de negocio, SQL, HTML, CSS, JS embebido, permisos, reportes, cocina, cobro, inventario y cierre.
- SQLite local se usa por defecto.
- PostgreSQL se usa en producción cuando existe `DATABASE_URL`.
- Render toma el proyecto desde GitHub.
- Los scripts locales de impresión dependen de rutas HTTP específicas.

## Visión NekoPOS

NekoPOS debe crecer hacia una plataforma modular para restaurantes:

- Multi restaurante.
- Menú configurable.
- Cocina desacoplada.
- Caja/cobro auditable.
- Inventario separado.
- Reportes claros.
- Impresión local estable.
- Deploy simple en Render u otra plataforma.

## Reglas inquebrantables

- No romper rutas existentes.
- No cambiar contratos JSON de scripts locales sin autorización.
- No mezclar refactor con nueva funcionalidad.
- No modificar base de datos sin plan y respaldo.
- No perder compatibilidad SQLite/PostgreSQL.
- No romper Render.
- Hacer cambios pequeños, reversibles y probables.

## Archivos críticos

- `web_app.py`: punto de entrada actual y núcleo del sistema.
- `requirements.txt`: dependencias de producción.
- `china_house.db`: base SQLite local.
- `scripts_locales/script_comanda_cocina.py`: impresión de comandas.
- `scripts_locales/script_factura.py`: impresión de facturas.
- `DESARROLLO_POS.md`: guía inicial de modularización.
- `docs/`: base documental profesional.

## Rutas críticas

- `/`
- `/login`
- `/logout`
- `/crear_orden`
- `/orden/<int:orden_id>`
- `/agregar/<int:orden_id>/<int:producto_id>`
- `/enviar_cocina/<int:orden_id>`
- `/cobrar/<int:orden_id>`
- `/cocina`
- `/listo/<int:orden_id>`
- `/ordenes_cocina`
- `/facturas_pendientes`
- `/api/tasa`
- `/activar_factura/<int:orden_id>`
- `/reimprimir_factura/<int:orden_id>`
- `/desactivar_factura/<int:orden_id>`
- `/factura/<int:orden_id>`
- `/cierre`
- `/cerrar_jornada`
- `/reportes`
- `/dashboard`
- `/inventario`
- `/compras`
- `/produccion`
- `/recetas`
- `/usuarios`
- `/reset_neko`

## Compatibilidad SQLite/PostgreSQL

La app decide el motor de base de datos con `DATABASE_URL`.

- Sin `DATABASE_URL`: SQLite local.
- Con `DATABASE_URL`: PostgreSQL, normalmente en Render.

El SQL usa `?` como placeholder base y `adaptar_query()` lo convierte a `%s` cuando se usa PostgreSQL.

## Render y GitHub

Render despliega desde GitHub. `web_app.py` debe seguir existiendo como entrada hasta que se haga una migración controlada.

No cambiar imports, estructura de arranque ni comando de deploy sin revisar Render.

## Scripts locales

Los scripts locales son clientes externos del servidor:

- `script_comanda_cocina.py` consulta `/ordenes_cocina`.
- `script_factura.py` consulta `/facturas_pendientes`, `/api/tasa` y `/desactivar_factura/<id>`.

Estas rutas son contratos externos.

## Principios de trabajo

- Leer este archivo antes de modificar.
- Entender flujo completo antes de tocar código.
- Priorizar estabilidad operativa.
- Documentar cada fase.
- Probar manualmente el flujo crítico.

