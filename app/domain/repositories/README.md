# Domain Repositories

## Responsabilidad

Contendra contratos o interfaces de repositorios que expresan que necesita el dominio o la aplicacion para guardar y consultar datos.

## Que tipo de archivos viviran aqui

- Interfaces de repositorios.
- Protocolos o contratos de persistencia.
- Nombres de operaciones del negocio sin SQL.

## Que NO debe vivir aqui

- Implementaciones SQLite.
- Implementaciones PostgreSQL.
- Queries SQL.
- Cursores o conexiones.
- Configuracion de entorno.

## Quien puede depender de esta carpeta

- `application`
- `infrastructure/repositories`

## De que puede depender

- `domain/entities`
- `domain/value_objects`

## Ejemplos futuros

- `orden_repository.py`
- `producto_repository.py`
- `usuario_repository.py`
- `factura_repository.py`

## Reglas de diseno

- Define contratos, no detalles tecnicos.
- Usa lenguaje de negocio.
- No menciona tablas salvo que sea inevitable y documentado.
