# Presentation

## Responsabilidad

Contendra Flask, rutas, Blueprints, templates, static, APIs HTTP y pantallas. Esta capa recibe requests y devuelve responses.

Regla principal:

"La presentación muestra información.

Nunca decide reglas del negocio."

## Que tipo de archivos viviran aqui

- Rutas Flask.
- Blueprints.
- Templates HTML.
- Archivos static.
- APIs HTTP para scripts locales.
- Adaptadores de entrada/salida web.

## Que NO debe vivir aqui

- Reglas complejas del negocio.
- SQL directo cuando exista caso de uso/repositorio.
- Calculos de dominio.
- Migraciones.

## Quien puede depender de esta capa

- Ninguna capa interna debe depender de presentacion.
- Flask la usa como borde externo.

## De que puede depender

- `application`
- `infrastructure` para configuracion tecnica puntual.
- `shared` para formato de salida simple.

## Ejemplos futuros

- `web/auth_routes.py`
- `web/orden_routes.py`
- `api/cocina_api.py`
- `templates/orden.html`
- `static/css/base.css`

## Reglas de diseno

- Mantener URLs criticas.
- Mantener contratos JSON de scripts locales.
- Delegar reglas a casos de uso.
- No cambiar nombres de endpoints sin revisar permisos.
