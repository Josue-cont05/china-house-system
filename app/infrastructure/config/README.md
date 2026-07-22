# Infrastructure Config

## Responsabilidad

Contendra configuracion tecnica del sistema y lectura de variables de entorno.

## Que tipo de archivos viviran aqui

- Configuracion de Render.
- Lectura de `DATABASE_URL`.
- Configuracion de SQLite local.
- Parametros tecnicos de despliegue.

## Que NO debe vivir aqui

- Reglas de negocio.
- Rutas.
- SQL de dominio.
- Templates.

## Quien puede depender de esta carpeta

- `infrastructure/database`
- Inicializacion futura de la app.

## De que puede depender

- Variables de entorno.
- `shared` solo si hay helpers puros de texto o validacion.

## Ejemplos futuros

- `settings.py`
- `database_url.py`
- `render.py`

## Reglas de diseno

- No cambiar defaults sin plan.
- Mantener comportamiento local y Render.
- Documentar cada variable importante.
