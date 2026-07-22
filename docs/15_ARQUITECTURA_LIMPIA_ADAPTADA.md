# Arquitectura Limpia Adaptada para NekoPOS

Este documento define la visión arquitectónica preferida para la modularización del POS. No busca aplicar Clean Architecture de forma rígida o académica; busca una versión práctica, segura y gradual para un POS Flask real que ya está en producción.

La regla base sigue siendo: `web_app.py` permanece como punto de entrada mientras se migra el sistema por fases.

## 1. Visión General

La estructura objetivo será:

```text
app/
  application/
  domain/
  infrastructure/
  presentation/
  shared/
```

La intención es separar reglas puras del negocio, casos de uso, detalles técnicos, Flask/rutas/pantallas y utilidades comunes.

## 2. Capas Propuestas

### 2.1 `domain`

Responsabilidad:

- Contener entidades, reglas puras del negocio y conceptos centrales del POS.
- Representar el motor de negocio sin depender de Flask, SQL, Render ni templates.

Ejemplos de objetos futuros:

- `Orden`
- `Producto`
- `Combo`
- `Promocion`
- `Pago`
- `Usuario`
- `Inventario`
- `Receta`
- `CierreJornada`

Debe contener validaciones puras, reglas de combos, reglas de promociones, estados válidos de una orden, cálculos puros de totales y reglas de pagos o inventario que no dependan de persistencia.

No debe:

- Importar Flask.
- Importar `request`, `session` o `g`.
- Importar SQLite/PostgreSQL.
- Ejecutar SQL.
- Conocer Render.
- Conocer templates.
- Conocer rutas HTTP.

### 2.2 `application`

Responsabilidad:

- Contener casos de uso del negocio.
- Coordinar entidades, repositorios, reglas y servicios de dominio.
- Ser el puente entre `presentation` e `infrastructure`.

Ejemplos de casos de uso:

- `crear_orden`
- `agregar_producto_a_orden`
- `enviar_orden_a_cocina`
- `cobrar_orden`
- `activar_factura`
- `cerrar_jornada`
- `registrar_compra`
- `registrar_produccion`
- `generar_reporte`

Cada caso de uso coordina entidades, repositorios y reglas. No debe renderizar HTML, leer directamente `request.form`, conocer templates ni depender de rutas Flask.

### 2.3 `infrastructure`

Responsabilidad:

- Contener implementación técnica.
- Encapsular base de datos, adaptadores, configuración, migraciones y dependencias externas.

Incluye:

- SQLite.
- PostgreSQL.
- `DATABASE_URL`.
- `get_connection`.
- `adaptar_query`.
- Wrappers de cursor/conexión.
- Repositorios SQL.
- Migraciones runtime actuales.
- Configuración Render.
- Adaptadores para scripts externos si aplica.

No debe renderizar HTML ni contener reglas complejas de negocio.

### 2.4 `presentation`

Responsabilidad:

- Contener Flask, rutas, Blueprints, templates, static, APIs HTTP y pantallas.
- Recibir requests.
- Traducir inputs HTTP a comandos/casos de uso.
- Devolver HTML, JSON o redirects.

Esta capa no debe contener reglas de negocio complejas. Las rutas deben delegar progresivamente en casos de uso.

### 2.5 `shared`

Responsabilidad:

- Contener utilidades reutilizables, pequeñas y bien organizadas.
- Evitar un `utils.py` gigante.

Áreas sugeridas:

- `fechas`
- `dinero`
- `texto`
- `validaciones`
- `formateadores`
- `excel`
- `xml`

No debe abrir conexiones, leer `request`, leer `session`, depender de `g` ni contener reglas complejas de flujo.

## 3. Principios obligatorios

- La lógica de negocio no debe depender de Flask.
- La lógica de negocio no debe depender de SQLite/PostgreSQL directamente.
- Las rutas no deben contener reglas complejas.
- Las rutas deben delegar en casos de uso.
- Los repositorios ocultan el SQL.
- El motor del POS no debe depender de Neko Wok como restaurante específico.
- Neko Wok debe ser una configuración/implementación del motor.
- Ningún archivo nuevo debería superar 500 líneas sin justificación.
- Nunca crear otro monolito.
- No mezclar refactor con funcionalidad nueva.
- No modificar contratos externos sin plan.
- No cambiar URLs críticas durante la migración.
- Mantener `web_app.py` como punto de entrada hasta el final de la migración.

## 4. Comparación con la estructura anterior

La propuesta anterior usaba:

```text
routes/
services/
database/
utils/
templates/
static/
```

Esa estructura ayuda a ordenar un Flask monolítico, pero puede quedarse corta para convertir el proyecto en un motor POS reutilizable.

La estructura preferida será:

```text
application/
domain/
infrastructure/
presentation/
shared/
```

| Estructura anterior | Riesgo | Estructura nueva | Ventaja |
|---|---|---|---|
| `services` genérico | Puede convertirse en otro monolito de servicios. | `application` + `domain` | Separa casos de uso de reglas puras. |
| `database` | Correcto, pero limitado al nombre técnico. | `infrastructure` | Permite incluir DB, Render, configuración y adaptadores. |
| `routes` | Correcto para Flask. | `presentation` | Agrupa rutas, templates, static y APIs. |
| `utils` | Puede crecer sin orden. | `shared` | Obliga a separar por responsabilidad. |
| Sin capa `domain` explícita | Reglas quedan mezcladas. | `domain` | Protege el motor del POS. |

No se busca seguir Clean Architecture de forma rígida, sino crear una versión práctica para un POS real ya en producción.

## 5. Mapa de migración actualizado

### FASE 0 - Documentación y análisis

Completar base documental, radiografía, mapa de dependencias, plan de migración y decisiones ADR.

### FASE 1 - Crear estructura vacía de Clean Architecture

Crear:

```text
app/
  application/
  domain/
  infrastructure/
  presentation/
  shared/
```

Regla: no crear imports, no mover funciones y no cambiar `web_app.py`.

### FASE 2 - Crear README.md dentro de cada capa

Crear:

- `app/application/README.md`
- `app/domain/README.md`
- `app/infrastructure/README.md`
- `app/presentation/README.md`
- `app/shared/README.md`

Cada README debe explicar qué puede vivir en la capa, qué no puede vivir allí, ejemplos del POS y reglas de dependencia.

### FASE 3 - Extraer `shared` por responsabilidad

Mover helpers puros por tema:

- `shared/fechas`
- `shared/texto`
- `shared/formato`
- `shared/dinero`
- `shared/excel`
- `shared/xml`
- `shared/validaciones`

### FASE 4 - Extraer `domain` con entidades y reglas puras

Crear entidades y reglas independientes de Flask/SQL:

- `Orden`
- `Producto`
- `Combo`
- `Promocion`
- `Pago`
- `Usuario`
- `Inventario`
- `CierreJornada`

### FASE 5 - Extraer `infrastructure/database`

Mover infraestructura DB sin tocar rutas:

- `get_connection`
- `adaptar_query`
- `normalizar_database_url`
- `CursorWrapper`
- `ConnectionWrapper`
- `pk_autoincrement_sql`
- `obtener_ultimo_id`
- `columna_existe`

### FASE 6 - Crear repositorios

Crear repositorios que oculten SQL:

- `OrdenRepository`
- `ProductoRepository`
- `UsuarioRepository`
- `PagoRepository`
- `InventarioRepository`
- `FacturaRepository`
- `ReporteRepository`
- `CierreRepository`

### FASE 7 - Crear `application/use_cases`

Crear casos de uso como:

- `crear_orden`
- `agregar_producto_a_orden`
- `enviar_orden_a_cocina`
- `cobrar_orden`
- `activar_factura`
- `cerrar_jornada`
- `registrar_compra`
- `registrar_produccion`
- `generar_reporte`

### FASE 8 - Mover lógica desde rutas hacia casos de uso

Reducir rutas sin cambiar URLs. Orden sugerido: usuarios, menú, reportes, inventario parcial, cocina/facturas con cuidado, orden y cobro al final.

### FASE 9 - Crear `presentation/blueprints` manteniendo URLs

Mover rutas a Blueprints preservando exactamente las URLs y revisando `request.endpoint`.

### FASE 10 - Separar templates/static

Mover HTML, CSS y JS pantalla por pantalla. Orden y cobro van al final.

### FASE 11 - Reducir `web_app.py` como punto de entrada

Dejar `web_app.py` como entrada liviana compatible con Render, conservando `app` y arranque local.

## 6. Zonas de migración

### Zona Verde

- `shared/fechas`
- `shared/texto`
- `shared/formato`
- `shared/excel`
- `shared/xml`
- Constantes puras.

### Zona Amarilla

- Dinero/pagos.
- Reportes.
- Inventario parcial.
- Agrupadores cocina/factura.

### Zona Roja

- `orden`
- `agregar`
- `cobrar`
- `cocina`
- `facturas_pendientes`
- `desactivar_factura`
- `init_db`
- `proteger_sistema`
- `reset`

## 7. Reglas para futuros tickets

Cada ticket debe indicar:

- Capa afectada.
- Dominio afectado.
- Zona de riesgo.
- Archivos que se tocarán.
- Funciones que se moverán.
- Rutas afectadas.
- Contratos externos afectados.
- Pruebas obligatorias.
- Plan de rollback.

Formato recomendado:

```text
Ticket:
Capa afectada:
Dominio afectado:
Zona de riesgo:
Archivos a tocar:
Funciones a mover:
Rutas afectadas:
Contratos externos afectados:
Pruebas obligatorias:
Rollback:
```

## 8. Reglas de dependencia

Dependencias permitidas:

```text
presentation -> application -> domain
application -> infrastructure
infrastructure -> domain
shared -> nadie
domain -> nadie externo
```

Reglas:

- `domain` no importa `application`.
- `domain` no importa `infrastructure`.
- `domain` no importa `presentation`.
- `application` no renderiza HTML.
- `presentation` no ejecuta SQL directamente cuando exista caso de uso/repositorio.
- `shared` no debe convertirse en un archivo genérico gigante.

## 9. Criterio de éxito

La migración será exitosa si:

- `web_app.py` sigue siendo entrada estable hasta el final.
- Las URLs no cambian.
- Los scripts locales siguen funcionando.
- SQLite local sigue funcionando.
- PostgreSQL en Render sigue funcionando.
- La lógica del POS puede entenderse sin leer Flask.
- Neko Wok queda como configuración, no como dependencia rígida del motor.

