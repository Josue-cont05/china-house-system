# Épicas y Tickets

Este documento organiza el trabajo futuro de NekoPOS en épicas y tickets pequeños. Los tickets deben ejecutarse de forma incremental, preservando rutas, lógica actual, Render, SQLite/PostgreSQL y scripts locales.

## ÉPICA 001 - Fundación de NekoPOS

Objetivo: crear una base documental, técnica y organizativa para transformar el POS monolítico actual en NekoPOS de forma segura.

## Ajuste arquitectónico aprobado

La modularización se orientará hacia una Clean Architecture adaptada:

```text
app/application
app/domain
app/infrastructure
app/presentation
app/shared
```

Antes de mover código se crearán las carpetas vacías y un `README.md` dentro de cada capa para explicar reglas, responsabilidades y límites.

Este ajuste reemplaza la intención genérica de `routes/services/database/utils` como arquitectura objetivo principal. La estructura anterior se mantiene como referencia histórica y conceptual, pero la guía preferida será `docs/15_ARQUITECTURA_LIMPIA_ADAPTADA.md`.

### Ticket 001 - Base documental inicial

Crear documentación principal del proyecto:

- `PROJECT_CONTEXT.md`
- `README.md`
- `ROADMAP.md`
- `CHANGELOG.md`
- `TODO.md`
- `FILOSOFIA.md`
- Documentación técnica en `docs/`.

Resultado esperado:

- Cualquier desarrollador o IA puede entender el estado actual antes de tocar código.

### Ticket 002 - Crear memoria de decisiones arquitectónicas

Crear un documento ADR para registrar decisiones importantes.

Resultado esperado:

- `docs/99_DECISIONES_DE_ARQUITECTURA.md`.
- Primera decisión: mantener `web_app.py` como punto de entrada durante la modularización.

### Ticket 003 - Crear estructura inicial de carpetas vacías

Estado: COMPLETADO

Descripción: Se creó la estructura física inicial del proyecto sin modificar código.

Crear carpetas futuras sin mover código todavía.

Carpetas creadas según la arquitectura aprobada en ADR-002:

- `app/`
- `app/application/`
- `app/domain/`
- `app/domain/entities/`
- `app/domain/value_objects/`
- `app/domain/repositories/`
- `app/infrastructure/`
- `app/infrastructure/database/`
- `app/infrastructure/repositories/`
- `app/infrastructure/config/`
- `app/presentation/`
- `app/presentation/web/`
- `app/presentation/api/`
- `app/presentation/templates/`
- `app/presentation/static/`
- `app/shared/`
- `app/shared/datetime/`
- `app/shared/money/`
- `app/shared/text/`
- `app/shared/validation/`
- `app/shared/excel/`
- `app/shared/xml/`

Resultado esperado:

- Estructura lista para modularización gradual.
- Sin cambios de lógica.
- Cada carpeta contiene un `README.md` con responsabilidad, límites y reglas de dependencia.

### Ticket 004 - Extraer constantes a módulo dedicado

Mover constantes de negocio y configuración visual a un módulo dedicado.

Candidatas:

- Roles.
- Métodos de pago.
- Sabores.
- Categorías.
- Combos.
- Promociones.
- Productos base de menú.

Resultado esperado:

- `web_app.py` importa constantes.
- No cambian rutas ni comportamiento.

#### Ticket 004A - Extraer constantes tecnicas compartidas

Estado: COMPLETADO

Descripcion: Se extrajeron constantes tecnicas compartidas de bajo riesgo a `app/shared/constants/system.py` sin cambiar valores ni comportamiento.

Constantes extraidas:

- `METODOS_PAGO_VALIDOS`
- `ETIQUETAS_METODO_PAGO`
- `ROLES_USUARIO_VALIDOS`
- `SABORES_REFRESCO`

Constantes no extraidas en este ticket:

- `CLAVE_SUPERVISOR`
- `VENEZUELA_TZ`
- `ORDEN_CATEGORIAS_POS`
- `COLORES_CATEGORIAS_POS`
- `PRODUCTOS_MENU_NEKO`
- `COMBOS_PERSONALES`
- `COMBOS_CON_FAVORITO`
- `FAVORITOS_COMBO_1`
- `PROMOCIONES_NEKO`
- `ARROCES_PROMOCION`
- `PROMO_EXTRA_LUMPIAS_NOMBRE`
- `PROMO_EXTRA_LUMPIAS_PRECIO`

#### Ticket 004B - Extraer configuracion de restaurante

Estado: PENDIENTE

Objetivo: tratar constantes especificas de Neko Wok, menu, categorias, combos y promociones en un ticket separado.

### Ticket 005 - Extraer utilidades puras

Mover funciones sin dependencia de Flask ni DB.

Candidatas:

- Normalización de métodos de pago.
- Formateo de montos.
- Normalización de sabores.
- Separación de cantidades en items.
- Agrupación de items para cocina/factura.

Resultado esperado:

- Helpers aislados y fáciles de probar.

### Ticket 006 - Extraer capa de base de datos

Mover conexión y compatibilidad SQLite/PostgreSQL a un módulo dedicado.

Incluye:

- `get_connection()`.
- Wrappers de conexión/cursor.
- `adaptar_query()`.
- Helpers de autoincremento.
- Helpers de columnas.

Resultado esperado:

- Una capa DB reutilizable.
- Sin cambiar SQL de negocio todavía.

### Ticket 007 - Crear servicios por dominio

Crear servicios graduales para separar lógica de negocio de rutas.

Dominios iniciales:

- Menú.
- Órdenes.
- Cocina.
- Cobro.
- Facturas.
- Inventario.
- Reportes.
- Usuarios.

Resultado esperado:

- Rutas más pequeñas.
- Lógica reusable.

### Ticket 008 - Crear Blueprints manteniendo rutas

Mover rutas por grupo usando Flask Blueprints sin cambiar URLs.

Orden recomendado:

1. Auth/usuarios.
2. Menú.
3. Inventario.
4. Reportes.
5. Cocina/facturas.
6. Órdenes/cobro al final.

Resultado esperado:

- Rutas organizadas.
- Contratos externos intactos.

### Ticket 009 - Separar templates HTML

Mover HTML embebido hacia `templates/`.

Regla:

- Una pantalla por cambio.
- No mezclar cambios visuales con cambios de negocio.

Resultado esperado:

- Código Python más legible.
- Interfaz más mantenible.

### Ticket 010 - Separar static CSS/JS

Mover CSS y JavaScript embebidos hacia `static/`.

Regla:

- No modificar comportamiento funcional durante la separación.
- Validar pantallas críticas después de cada movimiento.

Resultado esperado:

- Frontend organizado.
- Menor tamaño de rutas Python.
