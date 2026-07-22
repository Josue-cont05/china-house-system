# Domain Entities

## Responsabilidad

Contendra entidades centrales del negocio, con identidad y comportamiento propio.

## Que tipo de archivos viviran aqui

- Orden.
- Producto.
- Combo.
- Promocion.
- Pago.
- Usuario.
- Inventario.
- Receta.
- Cierre de jornada.

## Que NO debe vivir aqui

- SQL.
- Rutas Flask.
- Templates.
- Adaptadores externos.
- Codigo de impresion.

## Quien puede depender de esta carpeta

- `domain`
- `application`
- `infrastructure` para mapear datos hacia entidades.

## De que puede depender

- `domain/value_objects`
- Reglas puras del dominio.

## Ejemplos futuros

- `orden.py`
- `producto.py`
- `pago.py`
- `inventario.py`

## Reglas de diseno

- Una entidad representa un concepto del negocio.
- No debe saber como se guarda.
- No debe saber como se muestra.
- Debe proteger invariantes del negocio.
