# POS Neko Wok / China House

Sistema POS Flask para operación de restaurante: toma de órdenes, cocina, cobro, facturación, cierre, reportes e inventario.

## Estado actual

El proyecto es monolítico. La aplicación principal vive en `web_app.py`, que sigue siendo el punto de entrada actual para ejecución local y Render.

## Estructura actual

- `web_app.py`: aplicación Flask completa.
- `requirements.txt`: dependencias.
- `china_house.db`: SQLite local.
- `scripts_locales/`: scripts Windows para impresión local.
- `DESARROLLO_POS.md`: guía inicial de modularización.
- `docs/`: documentación técnica y de producto.

## Ejecución local

Instalar dependencias:

```bash
pip install -r requirements.txt
```

Ejecutar:

```bash
python web_app.py
```

Por defecto usa SQLite local con `china_house.db`.

## Producción

En Render, si existe `DATABASE_URL`, la app usa PostgreSQL. No cambiar `web_app.py` como entrada sin revisar configuración de Render.

## Archivos importantes

- `PROJECT_CONTEXT.md`: lectura obligatoria antes de cambios.
- `docs/05_GUIA_CODEX.md`: reglas para trabajar con Codex.
- `docs/07_API_CONTRATOS.md`: rutas usadas por scripts locales.
- `docs/08_PRUEBAS.md`: checklist manual.

## Advertencias

- No cambiar rutas críticas sin autorización.
- No cambiar JSON de impresión sin probar scripts locales.
- No mezclar modularización con nuevas funciones.
- No modificar SQL sin preservar SQLite y PostgreSQL.

