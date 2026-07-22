# Presentation Templates

## Responsabilidad

Contendra templates HTML cuando se separen las pantallas actualmente embebidas en `web_app.py`.

## Que tipo de archivos viviran aqui

- Templates Jinja.
- Parciales.
- Layouts.
- Fragmentos HTML reutilizables.

## Que NO debe vivir aqui

- Reglas de negocio.
- SQL.
- Calculos de cobro.
- Mutaciones de estado.

## Quien puede depender de esta carpeta

- `presentation/web`

## De que puede depender

- Datos ya preparados por `presentation` o `application`.

## Ejemplos futuros

- `login.html`
- `orden.html`
- `cobrar.html`
- `cocina.html`
- `partials/barra_superior.html`

## Reglas de diseno

- Una pantalla por cambio.
- No cambiar nombres de campos sin plan.
- No mover templates de orden/cobro al inicio.
