# Presentation Web

## Responsabilidad

Contendra rutas web Flask y Blueprints orientados a pantallas HTML del POS.

## Que tipo de archivos viviran aqui

- Blueprints web.
- Controladores Flask.
- Adaptadores de formularios.
- Redirects y respuestas HTML.

## Que NO debe vivir aqui

- SQL directo.
- Reglas puras de negocio.
- Templates embebidos grandes.
- Configuracion de base de datos.

## Quien puede depender de esta carpeta

- Solo la inicializacion de Flask o registro de Blueprints.

## De que puede depender

- `application`
- `presentation/templates`
- `shared` para formato visual simple.

## Ejemplos futuros

- `auth_routes.py`
- `orden_routes.py`
- `cobro_routes.py`
- `inventario_routes.py`

## Reglas de diseno

- Preservar URLs existentes.
- Las rutas deben ser delgadas.
- No mezclar refactor con cambios funcionales.
