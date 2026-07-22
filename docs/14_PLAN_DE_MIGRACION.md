# Plan Maestro de Migración hacia NekoPOS

> Nota de actualización arquitectónica:
> Este plan original se mantiene como referencia histórica. La arquitectura preferida para la modularización será la definida en `docs/15_ARQUITECTURA_LIMPIA_ADAPTADA.md`, basada en una Clean Architecture adaptada con capas `application`, `domain`, `infrastructure`, `presentation` y `shared`.

Este documento define el plan de migración del POS monolítico hacia una arquitectura modular. No autoriza cambios de código por sí mismo: cada fase debe ejecutarse como ticket pequeño, con validación y rollback.

Principio rector: `web_app.py` sigue siendo punto de entrada durante toda la migración, según ADR-001.

## FASE 0 - Preparación

Objetivo:

- Asegurar que el equipo y Codex tengan contexto suficiente antes de tocar código.

Motivo:

- El sistema es crítico para operación diaria.
- Hay dependencias con Render, SQLite/PostgreSQL y scripts locales.

Riesgo:

- Bajo, porque solo involucra documentación y checklist.

Tiempo estimado:

- 0,5 a 1 día.

Dependencias:

- Documentación existente.
- Radiografía de `web_app.py`.

Funciones que entran:

- Ninguna.

Funciones que NO entran:

- Todas. No se toca código.

Validaciones:

- Leer `PROJECT_CONTEXT.md`.
- Leer `docs/05_GUIA_CODEX.md`.
- Confirmar `git status`.
- Confirmar que existe backup de `china_house.db` antes de futuras pruebas.

Rollback:

- No aplica a código.

Commit sugerido:

- `docs: completar preparacion de migracion`

Ticket:

- Ticket 001 y Ticket 002.

## FASE 1 - Crear estructura vacía

Objetivo:

- Crear carpetas objetivo sin mover código.

Motivo:

- Preparar arquitectura sin riesgo funcional.

Riesgo:

- Bajo.

Tiempo estimado:

- 0,5 día.

Dependencias:

- ADR-001.
- Plan de migración aprobado.

Funciones que entran:

- Ninguna.

Funciones que NO entran:

- Todas.

Validaciones:

- Confirmar que `web_app.py` no cambió.
- Confirmar que no hay imports nuevos.
- Confirmar que Render no requiere ajustes.

Rollback:

- Borrar carpetas vacías si se decide revertir.

Commit sugerido:

- `chore: crear estructura modular vacia`

Ticket:

- Ticket 003.

Estructura sugerida:

```text
app/
  routes/
  services/
  database/
  utils/
templates/
static/
```

## FASE 2 - Extraer constantes

Objetivo:

- Mover constantes a un módulo dedicado sin cambiar valores.

Motivo:

- Reducir tamaño de `web_app.py`.
- Centralizar reglas estáticas.

Riesgo:

- Bajo si solo se mueven constantes y se importan.

Tiempo estimado:

- 0,5 a 1 día.

Dependencias:

- Fase 1.

Funciones que entran:

- Ninguna al inicio; solo constantes.

Constantes candidatas:

- `CLAVE_SUPERVISOR`
- `VENEZUELA_TZ`
- `METODOS_PAGO_VALIDOS`
- `SABORES_REFRESCO`
- `ETIQUETAS_METODO_PAGO`
- `ROLES_USUARIO_VALIDOS`
- `ORDEN_CATEGORIAS_POS`
- `COLORES_CATEGORIAS_POS`
- `FAVORITOS_COMBO_1`
- `COMBOS_PERSONALES`
- `COMBOS_CON_FAVORITO`
- `ARROCES_PROMOCION`
- `PROMOCIONES_NEKO`
- `PROMO_EXTRA_LUMPIAS_NOMBRE`
- `PROMO_EXTRA_LUMPIAS_PRECIO`
- `PRODUCTOS_MENU_NEKO`

Qué depende de ellas:

- Menú.
- Orden.
- Agregar productos.
- Cocina.
- Factura.
- Cobro.
- Permisos.

Funciones que NO entran:

- Rutas.
- `orden`
- `agregar`
- `cobrar`
- `init_db`
- `proteger_sistema`

Validaciones:

- Compilar `web_app.py`.
- Abrir login.
- Crear orden.
- Ver menú.
- Agregar combo y promoción.

Rollback:

- Revertir import y devolver constantes al archivo original.

Commit sugerido:

- `refactor: extraer constantes del dominio`

Ticket:

- Ticket 004.

## FASE 3 - Extraer helpers puros

Objetivo:

- Mover funciones sin DB, sin Flask globals y sin efectos secundarios.

Motivo:

- Son la zona más segura para iniciar refactor real.

Riesgo:

- Bajo a medio.

Tiempo estimado:

- 1 a 2 días.

Dependencias:

- Fase 2.

Funciones que entran:

- `ahora_venezuela`
- `parsear_fecha_hora_venezuela`
- `a_float`
- `normalizar_metodo_pago`
- `normalizar_sabor_refresco`
- `normalizar_indicacion_item`
- `quitar_prefijo_cantidad_visual`
- `separar_prefijo_cantidad`
- `producto_sin_prefijo_cantidad`
- `texto_item_con_indicacion`
- `texto_numero_orden`
- `xml_cell`
- `xml_sheet`
- `calcular_costo_promedio_ponderado`
- `parsear_porciones_detalle`
- `parsear_insumos_extra`

Funciones que NO entran:

- Funciones con SQL.
- Funciones con `request`.
- Funciones con `session`.
- Funciones con `g`.
- Rutas Flask.

Pruebas:

- Crear orden.
- Agregar refresco con sabor.
- Agregar combo.
- Agregar promoción.
- Revisar `/ordenes_cocina`.
- Revisar `/facturas_pendientes`.
- Exportar reporte si se movieron XML/XLSX.

Rollback:

- Revertir imports y funciones movidas.

Commit sugerido:

- `refactor: extraer utilidades puras`

Ticket:

- Ticket 005.

## FASE 4 - Extraer infraestructura de base de datos

Objetivo:

- Separar conexión y compatibilidad SQLite/PostgreSQL.

Motivo:

- `get_connection()` es usado por más de 60 funciones.
- La compatibilidad DB debe quedar aislada antes de mover servicios.

Riesgo:

- Alto.

Tiempo estimado:

- 1 a 2 días, más pruebas.

Dependencias:

- Fase 3.
- Backup SQLite.

Funciones que entran:

- `normalizar_database_url`
- `es_postgres`
- `adaptar_query`
- `CursorWrapper`
- `ConnectionWrapper`
- `get_connection`
- `pk_autoincrement_sql`
- `obtener_ultimo_id`
- `columna_existe`

Funciones que NO entran:

- Rutas.
- `init_db` completo.
- Queries de negocio.
- `cobrar`.
- `orden`.

Por qué todavía no deben tocarse rutas:

- Si falla DB, fallan todas las rutas.
- Conviene cambiar una sola dimensión: infraestructura, no flujo.
- Las rutas actuales sirven como prueba de regresión.

Pruebas:

- Arranque local con SQLite.
- Login.
- Crear orden.
- Agregar producto.
- Cobrar.
- Consultar reportes.
- Si es posible, smoke test con `DATABASE_URL`.

Rollback:

- Revertir módulo DB e imports.

Commit sugerido:

- `refactor: extraer infraestructura de base de datos`

Ticket:

- Ticket 006.

## FASE 5 - Crear capa Services

Objetivo:

- Crear servicios por dominio sin cambiar comportamiento.

Motivo:

- Separar lógica de negocio de rutas antes de Blueprints.

Riesgo:

- Medio a alto según dominio.

Tiempo estimado:

- 5 a 10 días en tickets pequeños.

Dependencias:

- Fase 4.

Funciones que entran por grupos:

- `menu_service`: `es_producto_refresco`, `es_combo_con_favorito`, `cargar_productos`, `asegurar_menu_neko_wok`, `desactivar_menu_china_house`.
- `cocina_service`: `nombre_producto_cocina`, `indicacion_operativa_cocina`, `agrupar_items_comanda`.
- `factura_service`: `agrupar_items_factura`.
- `pagos_service`: `convertir_pago_equivalente`, helpers de método de pago si no quedaron en utils.
- `inventario_service`: `registrar_movimiento_inventario`, `descontar_inventario_por_orden`, `sumar_inventario_con_costo`.
- `reportes_service`: `construir_reporte_rango`, `generar_xlsx`.
- `cierre_service`: `construir_resumen_cierre`, `resumen_cierre_pendiente`.
- `auth_service`: `usuario_rol`, `usuario_es_*`, `usuario_puede_*`.

Funciones que NO entran:

- Rutas completas.
- `orden` completa.
- `cobrar` completa.
- `proteger_sistema` hasta estabilizar auth.
- `init_db` completo.

Pruebas:

- Flujo completo manual.
- Reportes.
- Cocina.
- Facturas.
- Inventario si se movió servicio.

Rollback:

- Revertir servicio específico sin tocar otros.

Commit sugerido:

- `refactor: extraer servicio de <dominio>`

Ticket:

- Ticket 007, dividido en subtickets.

## FASE 6 - Crear Blueprints manteniendo URLs

Objetivo:

- Separar rutas por dominio sin cambiar URLs ni contratos.

Motivo:

- Ordenar Flask después de extraer lógica.

Riesgo:

- Alto.

Tiempo estimado:

- 5 a 8 días.

Dependencias:

- Fase 5.

Funciones que entran:

- Primero rutas simples: `login`, `logout`, usuarios, menú, reportes.
- Luego inventario.
- Luego cocina/facturas.
- Al final orden/cobro/admin.

Funciones que NO entran al principio:

- `orden`
- `agregar`
- `cobrar`
- `ordenes_cocina`
- `facturas_pendientes`
- `desactivar_factura`
- `reset_neko`

Pruebas:

- Verificar cada URL exacta.
- Verificar `request.endpoint` y permisos.
- Probar scripts locales si se mueven rutas API.

Rollback:

- Revertir Blueprint específico y volver ruta a `web_app.py`.

Commit sugerido:

- `refactor: mover rutas de <dominio> a blueprint`

Ticket:

- Ticket 008.

## FASE 7 - Separar templates

Objetivo:

- Mover HTML embebido a `templates/` pantalla por pantalla.

Motivo:

- Reducir tamaño de rutas.
- Separar presentación de negocio.

Riesgo:

- Medio a alto.

Tiempo estimado:

- 5 a 10 días.

Dependencias:

- Fase 6 preferiblemente, aunque algunas pantallas simples pueden moverse antes.

Funciones que entran:

- `login`
- `usuarios`
- `menu`
- `reportes`
- `dashboard`
- `inventario`
- `cocina`
- `cobrar`
- `orden`
- `reset_neko`

Funciones que NO entran al inicio:

- `orden` y `cobrar` hasta que haya templates base probados.

Pruebas:

- Pantalla movida abre igual.
- Formularios apuntan a las mismas rutas.
- No cambian nombres de campos.
- No cambia HTML necesario para JS.

Rollback:

- Restaurar HTML embebido de la pantalla movida.

Commit sugerido:

- `refactor: mover template de <pantalla>`

Ticket:

- Ticket 009.

## FASE 8 - Separar JavaScript

Objetivo:

- Mover JS embebido a `static/js`.

Motivo:

- Aislar comportamiento frontend.
- Reducir complejidad de rutas.

Riesgo:

- Medio a alto.

Tiempo estimado:

- 3 a 6 días.

Dependencias:

- Fase 7 parcial.

Funciones/pantallas que entran:

- `recetas`
- `compras`
- `orden`
- `cobrar`
- `reportes`
- `pantalla_cocina`

Funciones que NO entran al inicio:

- JS de `orden`, por su acoplamiento a combos/promociones.
- JS de `cobrar`, hasta estabilizar pagos.

Pruebas:

- Agregar refresco.
- Agregar Combo 1.
- Agregar promoción.
- Cobrar con método de pago.
- Cocina sigue refrescando/sonando si aplica.

Rollback:

- Reinsertar JS en template anterior o revertir archivo static.

Commit sugerido:

- `refactor: separar javascript de <pantalla>`

Ticket:

- Ticket 010 extendido.

## FASE 9 - Separar CSS

Objetivo:

- Mover estilos embebidos a `static/css`.

Motivo:

- Centralizar diseño.
- Evitar duplicación.

Riesgo:

- Medio.

Tiempo estimado:

- 3 a 5 días.

Dependencias:

- Fase 7 parcial.

Funciones/pantallas que entran:

- `estilos_base`
- `barra_superior`
- Login.
- Usuarios.
- Menú.
- Reportes.
- Cocina.
- Orden.
- Cobro.

Funciones que NO entran al inicio:

- Pantalla `orden` y `cobrar` si no están estabilizadas.

Pruebas:

- Verificar layout en desktop.
- Verificar layout móvil.
- Verificar botones y modales.

Rollback:

- Revertir CSS estático o volver estilos al template.

Commit sugerido:

- `refactor: separar estilos de <pantalla>`

Ticket:

- Ticket 010 extendido.

## FASE 10 - Reducir `web_app.py`

Objetivo:

- Dejar `web_app.py` como punto de entrada liviano.

Motivo:

- Cumplir ADR-001 sin romper Render.
- Centralizar app, registro de Blueprints e inicialización controlada.

Riesgo:

- Alto.

Tiempo estimado:

- 2 a 4 días.

Dependencias:

- Fases 1 a 9 completas y probadas.

Funciones que entran:

- Registro de app.
- Registro de Blueprints.
- Inicialización final.
- Compatibilidad con `app`.

Funciones que NO entran:

- No debe contener lógica de negocio.
- No debe contener HTML.
- No debe contener SQL de dominio.

Pruebas:

- Arranque local.
- Import de `app`.
- Render/Gunicorn.
- Flujo completo manual.
- Scripts locales.

Rollback:

- Revertir a `web_app.py` anterior.

Commit sugerido:

- `refactor: reducir web_app como punto de entrada`

Ticket:

- Ticket final de migración estructural.

## Tabla Maestra

| Fase | Ticket | Riesgo | Complejidad | Estado | Duración estimada | Rollback posible |
|---:|---|---|---|---|---|---|
| 0 | Tickets 001-002 | Bajo | Baja | Documentada | 0,5-1 día | Sí |
| 1 | Ticket 003 | Bajo | Baja | Pendiente | 0,5 día | Sí |
| 2 | Ticket 004 | Bajo | Baja/media | Pendiente | 0,5-1 día | Sí |
| 3 | Ticket 005 | Bajo/medio | Media | Pendiente | 1-2 días | Sí |
| 4 | Ticket 006 | Alto | Alta | Pendiente | 1-2 días | Sí, con cuidado |
| 5 | Ticket 007 | Medio/alto | Alta | Pendiente | 5-10 días | Sí por dominio |
| 6 | Ticket 008 | Alto | Alta | Pendiente | 5-8 días | Sí por blueprint |
| 7 | Ticket 009 | Medio/alto | Alta | Pendiente | 5-10 días | Sí por pantalla |
| 8 | Ticket 010 JS | Medio/alto | Media/alta | Pendiente | 3-6 días | Sí por pantalla |
| 9 | Ticket 010 CSS | Medio | Media | Pendiente | 3-5 días | Sí por pantalla |
| 10 | Ticket final entrada | Alto | Alta | Pendiente | 2-4 días | Sí, revert completo |

## Orden Recomendado de Inicio

1. Ejecutar Fase 1: crear estructura vacía.
2. Luego Fase 2: constantes.
3. Luego Fase 3: helpers puros.
4. No tocar DB, rutas, orden ni cobro hasta que esas fases estén probadas.

## Criterios para avanzar de fase

Una fase solo debe considerarse terminada si:

- `web_app.py` sigue importando correctamente.
- Las rutas críticas mantienen URL.
- No cambian contratos JSON.
- SQLite local funciona.
- Render no requiere cambio.
- El flujo manual mínimo pasa.
