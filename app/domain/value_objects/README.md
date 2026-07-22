# Domain Value Objects

## Responsabilidad

Contendra objetos de valor: conceptos sin identidad propia que encapsulan validacion y significado del negocio.

## Que tipo de archivos viviran aqui

- Dinero.
- Cantidad.
- Metodo de pago.
- Estado de orden.
- Sabor de refresco.
- Fecha de jornada.

## Que NO debe vivir aqui

- Acceso a base de datos.
- Request HTTP.
- HTML.
- Configuracion de Render.
- Mutaciones de infraestructura.

## Quien puede depender de esta carpeta

- `domain/entities`
- `application`
- `infrastructure` al reconstruir objetos desde datos.

## De que puede depender

- Reglas puras de `domain`.
- Componentes puros de `shared` si son necesarios.

## Ejemplos futuros

- `dinero.py`
- `estado_orden.py`
- `metodo_pago.py`

## Reglas de diseno

- Deben ser pequenos y expresivos.
- Deben validar su propio valor.
- No deben tener efectos secundarios.
