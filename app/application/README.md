# Application

## Responsabilidad

Contendra los casos de uso del negocio. Esta capa coordina entidades, reglas de dominio y repositorios para ejecutar acciones del POS.

## Que tipo de archivos viviran aqui

- Casos de uso.
- Comandos de aplicacion.
- Coordinadores de flujo.
- DTOs o estructuras simples de entrada/salida si hacen falta.

## Que NO debe vivir aqui

- Rutas Flask.
- HTML, CSS o JavaScript.
- SQL directo.
- Conexiones SQLite/PostgreSQL.
- Lecturas directas de `request`, `session` o `g`.

## Quien puede depender de esta capa

- `presentation`
- Pruebas de aplicacion futuras.

## De que puede depender

- `domain`
- Interfaces o repositorios definidos para acceder a datos.
- `infrastructure` solo a traves de abstracciones o wiring controlado.
- `shared` para componentes reutilizables simples.

## Casos de uso futuros

- `crear_orden`
- `agregar_producto_a_orden`
- `enviar_orden_a_cocina`
- `cobrar_orden`
- `activar_factura`
- `cerrar_jornada`
- `registrar_compra`
- `registrar_produccion`

## Reglas de diseno

- Un caso de uso expresa una accion del negocio.
- No importa Flask.
- No renderiza HTML.
- No ejecuta SQL directamente.
- Debe usar interfaces o repositorios para persistencia.
- Debe mantener reglas criticas fuera de las rutas.
