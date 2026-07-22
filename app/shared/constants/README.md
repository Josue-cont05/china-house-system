# Shared Constants

## Responsabilidad

Contiene constantes tecnicas y compartidas de bajo riesgo que pueden ser usadas por varias capas del sistema.

## Que constantes viven aqui

- Metodos de pago validos.
- Etiquetas compartidas de metodos de pago.
- Roles de usuario validos.
- Sabores compartidos de refresco.

## Que constantes no deben vivir aqui

- Credenciales o secretos.
- Objetos construidos con librerias externas.
- Configuracion especifica de un restaurante.
- Productos, combos, promociones o categorias propias de Neko Wok.
- Valores que dependan de Flask, base de datos, Render o infraestructura.

## Reglas

- Las constantes no deben contener logica.
- `system.py` no puede depender de Flask.
- `system.py` no puede depender de infraestructura.
- `system.py` no puede importar `web_app.py`.
- `system.py` debe contener solo estructuras de datos simples.

## Ejemplos futuros

- Constantes compartidas de roles.
- Constantes compartidas de metodos de pago.
- Listas simples de opciones globales del POS.
