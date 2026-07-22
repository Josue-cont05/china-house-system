# Infrastructure

## Responsabilidad

Contendra detalles tecnicos e integraciones externas. Aqui viven SQLite, PostgreSQL, Render, configuracion, variables de entorno, repositorios concretos, migraciones y adaptadores.

## Que tipo de archivos viviran aqui

- Conexion a base de datos.
- Adaptadores SQLite/PostgreSQL.
- Repositorios SQL concretos.
- Configuracion de entorno.
- Migraciones runtime futuras.
- Adaptadores para Cashea, WhatsApp, Delivery, impresoras o APIs externas.

## Que NO debe vivir aqui

- Reglas puras de negocio.
- Decisiones de combos o promociones.
- Renderizado HTML.
- Rutas Flask.
- Logica de presentacion.

## Quien puede depender de esta capa

- `application` cuando necesite implementaciones concretas mediante wiring.
- `presentation` para configuracion tecnica puntual si el ticket lo permite.

## De que puede depender

- `domain` para reconstruir entidades.
- `shared` para utilidades tecnicas puras.

## Ejemplos futuros

- `database/connection.py`
- `database/schema.py`
- `repositories/sql_orden_repository.py`
- `config/settings.py`
- `adapters/printer_adapter.py`

## Reglas de diseno

- Encapsular detalles tecnicos.
- No decidir reglas del negocio.
- Mantener compatibilidad SQLite local y PostgreSQL en Render.
- Proteger contratos externos.
