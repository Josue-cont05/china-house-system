# Base de Datos

## SQLite local

Por defecto el sistema usa SQLite con `china_house.db`.

## PostgreSQL en Render

Si existe `DATABASE_URL`, el sistema usa PostgreSQL. Esta es la ruta esperada para producción en Render.

## `get_connection()`

Función central que decide qué motor usar y devuelve una conexión compatible mediante wrappers.

## `adaptar_query()`

Convierte placeholders:

- SQLite: `?`
- PostgreSQL: `%s`

## Tablas principales

- `usuarios`
- `categorias`
- `productos`
- `ordenes`
- `orden_items`
- `pagos`
- `tasa`
- `cierres`
- `cierres_caja`
- `cierre_detalle`
- `inventario`
- `compras`
- `producciones`
- `proveedores`
- `productos_base`
- `recetas`
- `movimientos_inventario`
- `ingredientes`
- `auditoria_emergencias`

## Riesgos de migraciones en runtime

El sistema crea tablas y agrega columnas al arrancar. Esto es práctico, pero delicado:

- Importar la app puede modificar DB.
- No hay migraciones versionadas.
- Errores en una columna pueden afectar producción.

## Reglas de compatibilidad

- Mantener SQL parametrizado.
- No usar SQL específico de PostgreSQL sin wrapper.
- No usar SQL específico de SQLite sin alternativa.
- Probar cambios en ambos motores cuando sea posible.
- Respaldar SQLite antes de pruebas con datos reales.

