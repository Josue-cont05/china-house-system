# Domain

## Responsabilidad

Es el corazon del sistema y del negocio. Contendra entidades, reglas puras y conceptos centrales del POS.

Si manana cambia Flask, SQLite, PostgreSQL, Render o la forma de mostrar pantallas, esta capa deberia permanecer practicamente igual.

## Que tipo de archivos viviran aqui

- Entidades del negocio.
- Objetos de valor.
- Interfaces de repositorios.
- Reglas puras de combos, promociones, pagos, ordenes, inventario y cierre.

## Que NO debe vivir aqui

- Flask.
- SQLite.
- PostgreSQL.
- Render.
- Templates.
- SQL.
- HTML, CSS o JavaScript.
- `request`, `session` o `g`.

## Quien puede depender de esta capa

- `application`
- `infrastructure`
- Pruebas de dominio futuras.

## De que puede depender

- De nadie externo al negocio.
- Puede usar `shared` solo si son componentes realmente puros y estables.

## Ejemplos futuros

- `entities/orden.py`
- `entities/producto.py`
- `entities/pago.py`
- `value_objects/dinero.py`
- `repositories/orden_repository.py`

## Reglas de diseno

- Las reglas puras viven aqui.
- No conoce tecnologia.
- No conoce pantallas.
- No conoce base de datos.
- Debe poder probarse sin levantar Flask.
