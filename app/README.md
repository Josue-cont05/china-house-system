# App

## Responsabilidad

Contiene la estructura futura de NekoPOS bajo una Clean Architecture adaptada. Esta carpeta no reemplaza todavia a `web_app.py`; prepara el espacio para mover codigo por fases cuando exista un ticket especifico.

## Capas

```text
app/
  application/
  domain/
  infrastructure/
  presentation/
  shared/
```

## Relacion entre capas

```text
presentation
↓
application
↓
domain

presentation
↓
infrastructure

application
↓
infrastructure

domain
↓
NO DEPENDE DE NADIE
```

Las dependencias siempre apuntan hacia el centro del negocio. `domain` debe permanecer independiente de Flask, SQL, Render, templates y detalles tecnicos.

## Que tipo de archivos viviran aqui

- Documentacion de arquitectura de la carpeta `app`.
- Subcarpetas de capas aprobadas.
- En el futuro, modulos Python creados por tickets controlados.

## Que NO debe vivir aqui

- Codigo funcional agregado sin ticket.
- Copias de `web_app.py`.
- Archivos temporales.
- Logica mezclada sin capa definida.

## Quien puede depender de esta carpeta

El proyecto completo puede usar `app` como raiz modular futura.

## De que puede depender

Esta carpeta solo organiza capas. Las reglas reales de dependencia se definen dentro de cada capa.

## Ejemplos futuros

- `app/application/crear_orden.py`
- `app/domain/entities/orden.py`
- `app/infrastructure/database/connection.py`
- `app/presentation/web/orden_routes.py`
- `app/shared/money/formatos.py`

## Reglas de diseno

- No mover codigo aqui sin ticket.
- No cambiar rutas durante la creacion de estructura.
- No crear imports desde `web_app.py` en esta fase.
- Mantener `web_app.py` como punto de entrada hasta el final de la migracion.
