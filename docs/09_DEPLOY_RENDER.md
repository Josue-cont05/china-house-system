# Deploy en Render

## Relación con GitHub

Render despliega el proyecto desde GitHub. Cualquier cambio subido puede afectar producción.

## Entrada actual

`web_app.py` debe seguir existiendo como entrada mientras Render esté configurado para usarlo.

No cambiar comando de arranque sin revisar configuración de Render.

## PostgreSQL

`DATABASE_URL` activa PostgreSQL.

Sin `DATABASE_URL`, la app usa SQLite local.

## Variables importantes

- `DATABASE_URL`: conexión PostgreSQL.
- `SECRET_KEY`: secreto Flask.
- `APP_ENV`: ambiente.
- `SQLITE_PATH` o `DB_PATH`: ruta SQLite alternativa.
- `PORT`: puerto de ejecución.

## Riesgos de imports

Al modularizar:

- Imports rotos pueden impedir que Render arranque.
- Inicialización circular puede romper `app`.
- Mover `app` sin compatibilidad puede romper Gunicorn.

## Regla segura

Mantener `web_app.py` importable y con `app` disponible hasta completar la transición.

