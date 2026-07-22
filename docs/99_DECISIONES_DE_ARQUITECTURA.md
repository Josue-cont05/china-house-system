# Decisiones de Arquitectura

Este documento registra decisiones arquitectónicas relevantes para la evolución del POS hacia NekoPOS. Cada decisión debe conservar contexto, decisión, motivo y consecuencias.

## ADR-001 - Mantener web_app.py como punto de entrada

Fecha: 2026-07-07
Estado: Aprobada

### Contexto

Render actualmente depende de que el proyecto conserve un punto de entrada estable.

El sistema sigue siendo un monolito Flask concentrado principalmente en `web_app.py`. Ese archivo contiene la aplicación Flask, rutas, lógica de negocio, HTML embebido, acceso a base de datos y procesos de inicialización.

### Decisión

`web_app.py` seguirá existiendo como punto de entrada principal durante la modularización.

### Motivo

Evitar romper el deploy en Render mientras se separa el monolito por fases.

La modularización debe reducir riesgo operativo. Mantener un punto de entrada estable permite extraer módulos gradualmente sin obligar a cambiar de inmediato el comando de arranque, los imports de producción o el comportamiento esperado por GitHub/Render.

### Consecuencias

- La modularización será gradual.
- `web_app.py` podrá importar módulos nuevos.
- No se cambiará el comando de arranque sin revisar Render.
- Las rutas críticas deben conservar sus URLs actuales.
- Los scripts locales de impresión deben seguir funcionando durante la transición.
- La app debe mantener compatibilidad con SQLite local y PostgreSQL en producción.

## ADR-002 - Adoptar Clean Architecture adaptada

Fecha: 2026-07-07
Estado: Aprobada

### Contexto

El proyecto nació como un monolito Flask funcional, pero se busca convertirlo en un motor POS reutilizable para distintos restaurantes.

El modelo anterior de carpetas `routes/services/database/utils` ayuda a ordenar el monolito, pero no expresa con suficiente claridad la separación entre reglas puras del negocio, casos de uso, infraestructura y presentación.

### Decisión

Adoptar una arquitectura por capas inspirada en Clean Architecture:

- `application`
- `domain`
- `infrastructure`
- `presentation`
- `shared`

### Motivo

Separar reglas de negocio, casos de uso, infraestructura y presentación para evitar crear otro monolito.

Esta decisión permite que NekoPOS evolucione de un sistema específico de Neko Wok hacia un motor POS reutilizable para otros restaurantes.

### Consecuencias

- La migración será más lenta pero más segura.
- Las rutas Flask deberán delegar progresivamente en casos de uso.
- El motor no debe depender directamente de Neko Wok.
- La lógica específica del restaurante deberá moverse gradualmente a configuración.
- `domain` no debe depender de Flask, SQL, Render ni templates.
- `infrastructure` contendrá detalles técnicos como SQLite, PostgreSQL, repositorios y configuración.
- `presentation` contendrá Flask, Blueprints, templates, static y APIs HTTP.
- `shared` deberá organizar utilidades por responsabilidad, evitando un `utils.py` gigante.
