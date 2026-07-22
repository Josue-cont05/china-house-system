# Infrastructure Database

## Responsabilidad

Contendra acceso tecnico a base de datos y compatibilidad entre SQLite local y PostgreSQL en Render.

## Que tipo de archivos viviran aqui

- Conexion.
- Adaptacion de placeholders.
- Helpers de autoincremento.
- Creacion o migracion de tablas.
- Transacciones.

## Que NO debe vivir aqui

- Reglas de cobro.
- Reglas de cocina.
- Reglas de combos.
- Rutas Flask.
- HTML.

## Quien puede depender de esta carpeta

- `infrastructure/repositories`
- Wiring de aplicacion futuro.

## De que puede depender

- Configuracion tecnica.
- `shared` si requiere utilidades puras.

## Ejemplos futuros

- `connection.py`
- `schema.py`
- `migrations.py`
- `transactions.py`

## Reglas de diseno

- Toda query debe preservar SQLite/PostgreSQL.
- No exponer cursores directamente a capas superiores si existe repositorio.
- No ejecutar cambios de esquema sin ticket y respaldo.
