# Infrastructure Repositories

## Responsabilidad

Contendra implementaciones concretas de repositorios usando base de datos u otros medios de persistencia.

## Que tipo de archivos viviran aqui

- Repositorios SQL.
- Mapeadores entre filas y entidades.
- Consultas encapsuladas.

## Que NO debe vivir aqui

- Contratos puros del dominio.
- Rutas Flask.
- HTML.
- Reglas de negocio que pertenezcan a `domain` o `application`.

## Quien puede depender de esta carpeta

- Wiring de `application`.
- Pruebas de integracion futuras.

## De que puede depender

- `domain/repositories`
- `domain/entities`
- `infrastructure/database`

## Ejemplos futuros

- `sql_orden_repository.py`
- `sql_producto_repository.py`
- `sql_pago_repository.py`
- `sql_inventario_repository.py`

## Reglas de diseno

- Ocultar SQL a los casos de uso.
- Mantener nombres del negocio en la API publica.
- Probar compatibilidad con ambos motores.
