# Presentation Static

## Responsabilidad

Contendra CSS, JavaScript e imagenes estaticas del frontend.

## Que tipo de archivos viviran aqui

- CSS.
- JavaScript.
- Imagenes.
- Fuentes o assets visuales si hacen falta.

## Que NO debe vivir aqui

- Reglas de negocio.
- Secretos.
- SQL.
- Logica critica de cobro que solo exista en frontend.

## Quien puede depender de esta carpeta

- Templates y pantallas Flask.

## De que puede depender

- Nada interno de Python.

## Ejemplos futuros

- `css/base.css`
- `css/orden.css`
- `js/orden.js`
- `js/cobro.js`

## Reglas de diseno

- Separar CSS/JS despues de estabilizar templates.
- No cambiar comportamiento visual y negocio en el mismo ticket.
- Probar pantallas criticas.
