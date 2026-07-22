# Radiografía de `web_app.py`

Documento técnico para preparar la modularización segura del monolito Flask del POS Neko Wok / China House hacia NekoPOS.

Este documento es solo análisis. No propone cambios inmediatos de código ni modifica rutas, SQL, Render, SQLite o PostgreSQL.

## 1. Información General

| Métrica | Valor detectado | Observación |
|---|---:|---|
| Líneas totales | 7.332 | Archivo único con aplicación, UI, SQL y lógica de negocio. |
| Definiciones `def` totales | 126 | 111 funciones top-level, 14 métodos de wrappers y 1 función anidada (`generar`). |
| Funciones top-level | 111 | Funciones principales del monolito. |
| Rutas Flask `@app.route` | 50 | No incluye `@app.before_request`. |
| Hooks Flask | 1 | `proteger_sistema()` con `@app.before_request`. |
| Funciones auxiliares/no-ruta | 76 | Total de definiciones no asociadas directamente a `@app.route`. |
| Consultas/operaciones SQL aproximadas | 191 | Conteo de `cursor.execute` y `cursor.executemany`. |
| Commits explícitos | 46 | Conteo de `conn.commit(`. |
| Rollbacks explícitos | 3 | Conteo de `conn.rollback(`. |
| Funciones con HTML embebido | 25 | Rutas/pantallas y helpers que devuelven HTML. |
| Ocurrencias HTML principales | 373 | Conteo aproximado de `<html`, `<body`, `<div`, `<form`. |
| Formularios embebidos | 25 | Conteo aproximado de `<form`. |
| Bloques CSS embebidos | 30 | Conteo de `<style`. |
| Bloques JavaScript embebidos | 7 | Conteo de `<script`. |

Lectura técnica: `web_app.py` es un monolito real. Mezcla infraestructura, configuración, acceso a datos, reglas de negocio, vistas HTML, JS, CSS, seguridad, inventario, caja, cocina, facturación y reportes.

## 2. Índice General

| Línea inicial | Línea final | Nombre | Tipo | Responsabilidad |
|---:|---:|---|---|---|
| 1 | 131 | Imports y constantes | Configuración / dominio | Imports, Flask, SQLite/PostgreSQL opcional, roles, pagos, sabores, combos, promociones y menú Neko. |
| 132 | 257 | Configuración y conexión | Infraestructura | Carga de configuración, detección PostgreSQL, wrappers de cursor/conexión, `get_connection()`. |
| 258 | 300 | Helpers DB | Infraestructura DB | Autoincrement, último ID, existencia de columnas. |
| 301 | 536 | Utilidades de negocio | Utils / dominio | Fechas, parseo numérico, normalización de pagos, sabores, items, cocina y factura. |
| 537 | 751 | Tasa, migraciones y tablas base | DB / setup | Tasa actual, columnas, limpieza de facturas, cierres, usuarios iniciales, tablas de inventario. |
| 752 | 929 | Sesión, roles y auditoría | Seguridad / inventario | Roles, permisos, edición de emergencia, auditoría e inventario. |
| 930 | 1214 | Inventario avanzado | Servicios de inventario | Descuento por orden, datos base, costos promedio, producción, porciones e insumos extra. |
| 1215 | 1355 | UI común y jornada | UI helpers / jornada | CSS base, barra superior, inicio de jornada, número visual de orden. |
| 1362 | 1847 | Reportes y exportación | Reportes / export | Resumen de cierre, reportes por rango, XML/XLSX. |
| 1848 | 1974 | Protección global | Seguridad Flask | `before_request`, rutas públicas y permisos por endpoint. |
| 1975 | 2305 | Inicialización y menú | Bootstrap / menú | `init_db`, carga de productos, sincronización Neko Wok, desactivación menú antiguo, número de orden. |
| 2306 | 2749 | Login y usuarios | Rutas Flask | Autenticación, roles, CRUD de usuarios. |
| 2750 | 3089 | Inicio y menú | Rutas Flask | Home POS, administración de menú/productos. |
| 3090 | 4221 | Inventario completo | Rutas Flask | Inventario, recetas, movimientos, compras, proveedores, productos base, producción. |
| 4222 | 4339 | Productos | Rutas Flask | Alta, edición y eliminación de productos del menú. |
| 4340 | 5442 | Orden y cocina | Rutas Flask | Crear orden, vista de orden, agregar items, enviar cocina, reimprimir, editar, eliminar, emergencia. |
| 5443 | 5806 | Cobro y tasa | Rutas Flask | Cobro, pagos, descuento, inventario, cambio de tasa. |
| 5807 | 6626 | Exportación, reportes y cierre | Rutas Flask | Exportar, reportes, dashboard, cierre y cierre de jornada. |
| 6627 | 7108 | Cocina, factura y APIs locales | Rutas Flask / APIs | Pantalla cocina, JSON comandas, factura HTML, tasa API, facturas pendientes. |
| 7109 | 7332 | Reset y arranque | Admin / bootstrap | Reset Neko, reinicialización controlada, app context y `app.run`. |

## 3. Inventario Completo de Funciones

### 3.1 Métodos internos de wrappers

Estos métodos pertenecen a `CursorWrapper` y `ConnectionWrapper`. Son infraestructura y deben moverse con la capa `database` cuando se extraiga.

| Método | Línea | Tipo | Descripción | Riesgo | Propuesta futura |
|---|---:|---|---|---|---|
| `CursorWrapper.__init__` | 193 | Infraestructura DB | Guarda cursor real. | Bajo | `database`. |
| `CursorWrapper.execute` | 196 | Infraestructura DB | Adapta query y ejecuta SQL. | Alto | `database`; crítico para SQLite/PostgreSQL. |
| `CursorWrapper.executemany` | 204 | Infraestructura DB | Adapta query y ejecuta lote. | Alto | `database`. |
| `CursorWrapper.fetchone` | 209 | Infraestructura DB | Proxy a cursor. | Bajo | `database`. |
| `CursorWrapper.fetchall` | 212 | Infraestructura DB | Proxy a cursor. | Bajo | `database`. |
| `CursorWrapper.close` | 215 | Infraestructura DB | Cierra cursor. | Bajo | `database`. |
| `CursorWrapper.lastrowid` | 219 | Infraestructura DB | Expone último ID si existe. | Medio | `database`. |
| `CursorWrapper.__getattr__` | 222 | Infraestructura DB | Proxy genérico. | Medio | `database`. |
| `ConnectionWrapper.__init__` | 227 | Infraestructura DB | Guarda conexión real. | Bajo | `database`. |
| `ConnectionWrapper.cursor` | 230 | Infraestructura DB | Devuelve `CursorWrapper`. | Alto | `database`. |
| `ConnectionWrapper.commit` | 233 | Infraestructura DB | Proxy commit. | Medio | `database`. |
| `ConnectionWrapper.rollback` | 236 | Infraestructura DB | Proxy rollback. | Medio | `database`. |
| `ConnectionWrapper.close` | 239 | Infraestructura DB | Cierra conexión. | Bajo | `database`. |
| `ConnectionWrapper.__getattr__` | 242 | Infraestructura DB | Proxy genérico. | Medio | `database`. |

### 3.2 Funciones top-level

| Función | Líneas | Tipo | Usa | Retorna | Riesgo | Mover a | Dependencias principales / llamada por |
|---|---:|---|---|---|---|---|---|
| `cargar_configuracion` | 132-159 | Configuración | Entorno, DB engine | Dict | Bajo | `config` | Llamada al cargar `CONFIG`. |
| `es_postgres` | 160-163 | DB | `CONFIG` | Bool | Bajo | `database` | Usada por adaptadores y reset. |
| `normalizar_database_url` | 164-185 | DB/config | URL parsing | String | Bajo | `database` | Usada por `get_connection`. |
| `adaptar_query` | 186-245 | DB | `es_postgres` | SQL adaptado | Medio | `database` | Usada por `CursorWrapper`. |
| `get_connection` | 246-257 | DB | SQLite/PostgreSQL | Conexión | Alto | `database` | Reutilizada por 61 funciones; pilar de acceso a datos. |
| `pk_autoincrement_sql` | 258-263 | DB | `es_postgres` | SQL | Medio | `database` | Usada al crear tablas. |
| `obtener_ultimo_id` | 264-280 | DB | SQL, PostgreSQL/SQLite | ID | Medio | `database` | Usada por `crear_orden`, `cerrar_jornada`. |
| `columna_existe` | 281-300 | DB | SQL, PRAGMA/info schema | Bool | Medio | `database` | Usada por `asegurar_columna`. |
| `ahora_venezuela` | 301-304 | Utilidad fecha | Timezone | Datetime | Bajo | `utils/fechas` | Reutilizada por auditoría, compras, producción, órdenes, cierre. |
| `parsear_fecha_hora_venezuela` | 305-309 | Utilidad fecha | Timezone | Datetime | Bajo | `utils/fechas` | Usada en cocina. |
| `a_float` | 310-321 | Utilidad | Parseo numérico | Float | Bajo | `utils/formato` | Reutilizada por 18 funciones. |
| `normalizar_metodo_pago` | 322-328 | Pagos | Texto | String | Bajo | `utils/pagos` | Usada por pagos, reportes y cobro. |
| `es_producto_refresco` | 329-332 | Menú | Texto producto | Bool | Bajo | `services/menu` | Usada por orden/agregar. |
| `es_combo_con_favorito` | 333-336 | Menú | Constantes combo | Bool | Bajo | `services/menu` | No se detectan llamadas directas. |
| `normalizar_sabor_refresco` | 337-349 | Menú | Sabores | String | Bajo | `utils/items` | Usada por `agregar`. |
| `normalizar_indicacion_item` | 350-355 | Items | Texto | String | Bajo | `utils/items` | Cocina, factura, agregar, edición indicación. |
| `quitar_prefijo_cantidad_visual` | 356-365 | Items | Regex | String | Bajo | `utils/items` | Cocina, factura, JSON, pantalla. |
| `separar_prefijo_cantidad` | 366-376 | Items | Regex | Cantidad/producto | Bajo | `utils/items` | Agrupación y descuento inventario. |
| `producto_sin_prefijo_cantidad` | 377-381 | Items | `separar_prefijo_cantidad` | String | Bajo | `utils/items` | Cocina/factura. |
| `texto_item_con_indicacion` | 382-399 | Items/factura | Normalización | Texto | Bajo | `utils/items` | Usada por `agrupar_items_factura`. |
| `nombre_producto_cocina` | 400-404 | Cocina | Nombres simplificados | Texto | Bajo | `services/cocina` | Usada por `agrupar_items_comanda`. |
| `indicacion_operativa_cocina` | 405-441 | Cocina | Combos/promos | Texto | Medio | `services/cocina` | Regla de cocina para combos/promos. |
| `agrupar_items_comanda` | 442-475 | Cocina | Items, indicaciones | Lista | Medio | `services/cocina` | Usada por pantalla/API cocina. |
| `agrupar_items_factura` | 476-510 | Factura | Items/precios | Lista | Medio | `services/facturas` | Usada por factura y pendientes. |
| `etiqueta_metodo_pago` | 511-514 | Pagos | Métodos | Texto | Bajo | `utils/pagos` | Reportes/cierre. |
| `monto_formateado_segun_metodo` | 515-522 | Pagos | Método/monto | Texto | Bajo | `utils/pagos` | Cierre. |
| `convertir_pago_equivalente` | 523-536 | Pagos | Método, monto, tasa | Montos Bs/USD | Medio | `services/pagos` | Cobro y reportes. |
| `obtener_tasa_actual` | 537-542 | DB/pagos | SQL | Float | Medio | `services/configuracion` | Orden, cobro, reportes, API tasa. |
| `asegurar_columna` | 543-553 | DB/migración | SQL/commit | Ninguno | Alto | `database/migrations` | Agrega columnas en runtime. |
| `asegurar_columna_facturar` | 554-563 | DB/migración | SQL/commit | Ninguno | Alto | `database/migrations` | Inicializa `ordenes.facturar`. |
| `limpiar_facturas_archivadas` | 564-571 | Facturas/DB | SQL/commit | Ninguno | Medio | `services/facturas` | Limpia facturas cerradas al init. |
| `crear_tablas_cierre_jornada` | 572-617 | DB/cierre | CREATE/ALTER/commit | Ninguno | Alto | `database/schema` | Crea tablas de cierre y altera `ordenes`. |
| `crear_usuarios_iniciales` | 618-654 | Usuarios/setup | SQL/commit | Ninguno | Alto | `services/usuarios` | Desactiva/reactiva usuarios base. |
| `crear_tablas_inventario` | 655-751 | DB/inventario | CREATE/commit | Ninguno | Alto | `database/schema` | Crea tablas de inventario. |
| `usuario_activo` | 752-755 | Seguridad | Session | Texto | Bajo | `services/auth` | Barra, auditoría, cocina. |
| `usuario_rol` | 756-804 | Seguridad | Session, `g`, SQL | Rol | Alto | `services/auth` | Base de todos los permisos. |
| `usuario_es_master` | 805-808 | Seguridad | `usuario_rol` | Bool | Bajo | `services/auth` | Usada en permisos/rutas. |
| `usuario_es_mesonera` | 809-812 | Seguridad | `usuario_rol` | Bool | Bajo | `services/auth` | No crítica. |
| `usuario_es_cocina` | 813-816 | Seguridad | `usuario_rol` | Bool | Bajo | `services/auth` | No crítica. |
| `usuario_es_socio` | 817-820 | Seguridad | `usuario_rol` | Bool | Bajo | `services/auth` | No crítica. |
| `usuario_puede_tomar_ordenes` | 821-824 | Seguridad | `usuario_rol` | Bool | Medio | `services/auth` | `proteger_sistema`. |
| `usuario_puede_ver_inventario` | 825-828 | Seguridad | `usuario_rol` | Bool | Medio | `services/auth` | Permisos e UI cocina. |
| `usuario_puede_editar_inventario` | 829-832 | Seguridad | `usuario_rol` | Bool | Bajo | `services/auth` | No se detectan llamadas. |
| `usuario_puede_produccion` | 833-836 | Seguridad | `usuario_rol` | Bool | Medio | `services/auth` | Permisos e UI cocina. |
| `usuario_puede_ver_cocina` | 837-840 | Seguridad | `usuario_rol` | Bool | Medio | `services/auth` | `proteger_sistema`. |
| `usuario_puede_reportes` | 841-844 | Seguridad | `usuario_rol` | Bool | Medio | `services/auth` | `proteger_sistema`, reportes, dashboard. |
| `usuario_puede_admin_total` | 845-848 | Seguridad | `usuario_rol` | Bool | Bajo | `services/auth` | No se detectan llamadas. |
| `usuario_es_admin_cierre` | 849-852 | Seguridad | `usuario_es_master` | Bool | Alto | `services/auth` | 15 llamadas; administra acciones delicadas. |
| `usuario_puede_reimprimir_cocina` | 853-856 | Seguridad/cocina | `usuario_es_master` | Bool | Medio | `services/auth` | Orden/reimpresión cocina. |
| `obtener_emergencias_activas` | 857-861 | Emergencia | Session | Lista | Bajo | `services/ordenes` | Control edición emergencia. |
| `emergencia_activa` | 862-865 | Emergencia | Session/permisos | Bool | Alto | `services/ordenes` | Afecta edición de órdenes cerradas. |
| `activar_emergencia_sesion` | 866-874 | Emergencia | Session | Ninguno | Medio | `services/ordenes` | Activación emergencia. |
| `desactivar_emergencia_sesion` | 875-881 | Emergencia | Session | Ninguno | Medio | `services/ordenes` | Cobro posterior. |
| `registrar_auditoria_emergencia` | 882-893 | Auditoría | SQL, session | Ninguno | Alto | `services/auditoria` | Registra acciones de emergencia. |
| `registrar_movimiento_inventario` | 894-929 | Inventario | SQL, session | Ninguno | Alto | `services/inventario` | Movimiento de stock. |
| `descontar_inventario_por_orden` | 930-1043 | Inventario | SQL | Ninguno | Alto | `services/inventario` | Se llama al cobrar; mueve stock. |
| `crear_datos_base_inventario` | 1044-1075 | Inventario/setup | SQL/commit | Ninguno | Medio | `services/inventario` | Inserta productos base. |
| `obtener_costo_promedio_producto` | 1076-1116 | Inventario | SQL | Float | Medio | `services/inventario` | Costo promedio. |
| `calcular_costo_promedio_ponderado` | 1117-1129 | Inventario | Float | Float | Bajo | `utils/inventario` | Cálculo puro. |
| `sumar_inventario_con_costo` | 1130-1178 | Inventario | SQL | Ninguno | Alto | `services/inventario` | Compras/producción. |
| `parsear_porciones_detalle` | 1179-1197 | Producción | Texto | Lista | Bajo | `utils/inventario` | Producción. |
| `parsear_insumos_extra` | 1198-1214 | Producción | Texto | Lista | Bajo | `utils/inventario` | Producción. |
| `estilos_base` | 1215-1319 | UI/CSS | CSS string | Texto | Medio | `static` / `templates` | CSS global embebido. |
| `barra_superior` | 1320-1335 | UI | HTML/CSS/session | HTML | Medio | `templates/partials` | Usada por muchas pantallas. |
| `obtener_inicio_jornada_actual` | 1336-1355 | Jornada | SQL/fecha | Texto fecha | Medio | `services/cierre` | `siguiente_numero`. |
| `texto_numero_orden` | 1356-1361 | UI/formato | Número | Texto | Bajo | `utils/formato` | 8 llamadas. |
| `construir_resumen_cierre` | 1362-1530 | Cierre/reportes | SQL | Dict | Alto | `services/cierre` | Cierre y cerrar jornada. |
| `resumen_cierre_pendiente` | 1531-1538 | Cierre | DB | Dict | Medio | `services/cierre` | `cerrar_jornada`. |
| `fechas_reporte_desde_request` | 1539-1559 | Reportes | Request | Fechas | Medio | `routes/reportes` o `services/reportes` | Reportes/export/dashboard. |
| `construir_reporte_rango` | 1560-1774 | Reportes | SQL | Dict | Alto | `services/reportes` | Reportes/dashboard/export. |
| `xml_cell` | 1775-1781 | Export | XML | Texto | Bajo | `utils/export` | `xml_sheet`. |
| `xml_sheet` | 1782-1794 | Export | XML | Texto | Bajo | `utils/export` | `generar_xlsx`. |
| `generar_xlsx` | 1795-1847 | Export | Zip/XML | Bytes | Medio | `services/export` | `exportar_reporte`. |
| `proteger_sistema` | 1848-1974 | Seguridad Flask | Request/session/roles | Redirect/texto/None | Alto | No mover todavía | `before_request`; crítico para permisos. |
| `init_db` | 1975-2145 | DB/bootstrap | CREATE/ALTER/commit | Ninguno | Alto | No mover todavía | Crea y migra tablas al iniciar. |
| `cargar_productos` | 2146-2200 | Menú/setup | SQL/commit | Ninguno | Medio | `services/menu` | Carga menú antiguo si vacío. |
| `asegurar_menu_neko_wok` | 2201-2256 | Menú/setup | SQL/commit | Ninguno | Alto | `services/menu` | Sincroniza menú Neko. |
| `desactivar_menu_china_house` | 2257-2284 | Menú/setup | SQL/commit | Ninguno | Medio | `services/menu` | Inactiva menú antiguo. |
| `siguiente_numero` | 2285-2305 | Orden/jornada | SQL | Número | Alto | `services/ordenes` | Numeración de órdenes. |
| `login` | 2306-2464 | Ruta Flask | Request/session/SQL/HTML | HTML/redirect | Alto | `routes/auth` | Login completo. |
| `logout` | 2465-2469 | Ruta Flask | Session | Redirect | Bajo | `routes/auth` | Cierra sesión. |
| `opciones_roles_usuario` | 2470-2477 | Usuarios/UI | Roles | HTML options | Bajo | `services/usuarios` o template helper | Usuarios/editar usuario. |
| `rol_desde_formulario` | 2478-2485 | Usuarios | Request | Rol | Bajo | `services/usuarios` | Crear/editar usuario. |
| `usuarios` | 2486-2611 | Ruta Flask | SQL/HTML | HTML/texto | Alto | `routes/usuarios` | Pantalla usuarios. |
| `crear_usuario` | 2612-2638 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/usuarios` | Crea usuario. |
| `editar_usuario` | 2639-2729 | Ruta Flask | Request/SQL/HTML/commit | HTML/redirect/texto | Alto | `routes/usuarios` | Edita usuario. |
| `activar_usuario` | 2730-2749 | Ruta Flask | SQL/commit | Redirect/texto | Alto | `routes/usuarios` | Activa/desactiva usuario. |
| `index` | 2750-2986 | Ruta Flask | SQL/HTML | HTML | Alto | `routes/pos` | Home operativo del POS. |
| `menu` | 2987-3089 | Ruta Flask | Request/SQL/HTML/commit | HTML | Alto | `routes/menu` | Administración menú/categorías. |
| `inventario` | 3090-3177 | Ruta Flask | SQL/HTML | HTML | Alto | `routes/inventario` | Vista inventario. |
| `recetas` | 3178-3344 | Ruta Flask | Request/SQL/commit/HTML/JS | HTML/redirect/texto | Alto | `routes/inventario` | CRUD recetas. |
| `eliminar_receta` | 3345-3357 | Ruta Flask | SQL/commit | Redirect/texto | Alto | `routes/inventario` | Elimina receta. |
| `movimientos_inventario` | 3358-3432 | Ruta Flask | SQL/HTML | HTML/texto | Alto | `routes/inventario` | Historial movimientos. |
| `compras` | 3433-3739 | Ruta Flask | Request/session/SQL/commit/HTML/JS | HTML/redirect | Alto | `routes/inventario` | Compras temporales y registro. |
| `proveedores` | 3740-3840 | Ruta Flask | Request/SQL/commit/HTML | HTML/redirect | Alto | `routes/inventario` | CRUD proveedores. |
| `productos_base` | 3841-3945 | Ruta Flask | Request/SQL/commit/HTML | HTML/redirect | Alto | `routes/inventario` | CRUD productos base. |
| `produccion` | 3946-4221 | Ruta Flask | Request/session/SQL/commit/HTML | HTML/redirect | Alto | `routes/inventario` | Producción, merma, costos. |
| `agregar_producto` | 4222-4248 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/menu` | Alta producto menú. |
| `eliminar_producto` | 4249-4258 | Ruta Flask | SQL/commit | Redirect | Alto | `routes/menu` | Elimina producto. |
| `editar_producto` | 4259-4339 | Ruta Flask | Request/SQL/commit/HTML | HTML/redirect/texto | Alto | `routes/menu` | Edita producto. |
| `nueva_orden` | 4340-4344 | Ruta Flask | Ninguno | Redirect | Bajo | `routes/ordenes` | Alias a `/`. |
| `crear_orden` | 4345-4370 | Ruta Flask | Request/session/SQL/commit | Redirect | Alto | `routes/ordenes` | Crea cabecera orden. |
| `orden` | 4371-4960 | Ruta Flask | SQL/HTML/CSS/JS | HTML/texto | Alto | No mover todavía | Pantalla más grande y crítica. |
| `agregar` | 4961-5071 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/ordenes` después de servicios | Agrega item, combos, promos. |
| `enviar_cocina` | 5072-5107 | Ruta Flask | SQL/commit | Redirect/texto | Alto | `routes/cocina` | Cambia estado y número. |
| `reimprimir_cocina` | 5108-5149 | Ruta Flask | SQL/commit | Redirect/texto | Alto | `routes/cocina` | Token reimpresión. |
| `eliminar_item` | 5150-5199 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/ordenes` | Elimina item con clave. |
| `actualizar_indicacion_item` | 5200-5258 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/ordenes` | Edita indicación. |
| `editar_orden` | 5259-5353 | Ruta Flask | Request/SQL/HTML/commit | HTML/redirect/texto | Alto | `routes/ordenes` | Edita datos cabecera. |
| `eliminar_orden` | 5354-5395 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/ordenes` | Borra orden/items/pagos. |
| `activar_edicion_emergencia` | 5396-5442 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/ordenes` | Permite editar cerrada. |
| `cobrar` | 5443-5770 | Ruta Flask | Request/SQL/commit/rollback/HTML/JS | HTML/redirect/texto | Alto | No mover todavía | Cobro, pagos, inventario. |
| `cambiar_tasa` | 5771-5806 | Ruta Flask | Request/SQL/commit/HTML | HTML | Alto | `routes/configuracion` | Cambia tasa. |
| `exportar` | 5807-5911 | Ruta Flask | SQL | Texto/stream | Alto | `routes/reportes` | Export antiguo. |
| `generar` | 5903 | Función anidada | Streaming | Texto | Medio | Mantener con `exportar` | Generador interno de exportación. |
| `revertir_orden_cierre` | 5912-5961 | Ruta Flask | Request/SQL/commit | Redirect/texto | Alto | `routes/cierre` | Revierte orden cerrada. |
| `reportes` | 5962-6119 | Ruta Flask | Request/HTML/CSS/JS | HTML/texto | Alto | `routes/reportes` | Pantalla reportes. |
| `exportar_reporte` | 6120-6221 | Ruta Flask | Request/XLSX | Response/texto | Medio | `routes/reportes` | Export XLSX. |
| `dashboard` | 6222-6364 | Ruta Flask | Request/HTML/CSS | HTML/texto | Alto | `routes/dashboard` | Dashboard gerencial. |
| `cierre` | 6365-6508 | Ruta Flask | HTML/CSS/SQL por helper | HTML/texto | Alto | `routes/cierre` | Vista cierre. |
| `cerrar_jornada` | 6509-6626 | Ruta Flask | Session/SQL/commit/HTML | HTML/texto | Alto | No mover temprano | Cierre real de jornada. |
| `pantalla_cocina` | 6627-6776 | Ruta Flask | SQL/HTML/CSS/JS | HTML | Alto | `routes/cocina` después de servicio | Pantalla cocina. |
| `marcar_listo` | 6777-6789 | Ruta Flask | SQL/commit | Redirect | Alto | `routes/cocina` | Cambia estado a listo. |
| `ordenes_cocina` | 6790-6865 | Ruta Flask/API | SQL/JSON/commit | JSON | Alto | No cambiar contrato | API script cocina. |
| `factura` | 6866-6940 | Ruta Flask | SQL/HTML/CSS | HTML/texto | Alto | `routes/facturas` | Factura HTML. |
| `cerrar_dia` | 6941-6945 | Ruta Flask | Ninguno | Redirect | Bajo | `routes/cierre` | Alias a cierre jornada. |
| `api_tasa` | 6946-6959 | Ruta Flask/API | DB/JSON | JSON | Medio | `routes/api` | API script factura. |
| `facturas_pendientes` | 6960-7029 | Ruta Flask/API | SQL/JSON | JSON | Alto | No cambiar contrato | API script factura. |
| `activar_factura` | 7030-7042 | Ruta Flask | SQL/commit | Redirect | Alto | `routes/facturas` | Marca facturar. |
| `reimprimir_factura` | 7043-7079 | Ruta Flask | SQL/commit | Redirect/texto | Alto | `routes/facturas` | Token reimpresión. |
| `desactivar_factura` | 7080-7108 | Ruta Flask/API | SQL/commit/rollback/JSON | JSON | Alto | No cambiar contrato | API script factura. |
| `_reset_neko_wok_db` | 7109-7192 | DB/admin | SQL/commit/rollback | Ninguno | Alto | No mover todavía | Reset destructivo controlado. |
| `reset_neko` | 7193-7332 | Ruta Flask | Request/HTML/CSS/reset | HTML/texto | Alto | No mover temprano | Pantalla reset admin. |

## 4. Dependencias

### 4.1 Árbol funcional de alto nivel

```text
web_app.py
├─ Configuración
│  ├─ cargar_configuracion
│  ├─ es_postgres
│  ├─ normalizar_database_url
│  └─ adaptar_query
├─ Database
│  ├─ CursorWrapper / ConnectionWrapper
│  ├─ get_connection
│  ├─ pk_autoincrement_sql
│  ├─ obtener_ultimo_id
│  ├─ columna_existe
│  ├─ asegurar_columna
│  └─ init_db
├─ Dominio compartido
│  ├─ fechas: ahora_venezuela, parsear_fecha_hora_venezuela
│  ├─ formato: a_float, texto_numero_orden
│  ├─ pagos: normalizar_metodo_pago, convertir_pago_equivalente
│  ├─ items: normalizar_indicacion_item, separar_prefijo_cantidad
│  └─ menú: combos, promociones, sabores
├─ Seguridad
│  ├─ usuario_rol
│  ├─ usuario_es_master
│  ├─ usuario_puede_*
│  └─ proteger_sistema
├─ Servicios implícitos
│  ├─ ordenes: crear_orden, orden, agregar, editar_orden
│  ├─ cocina: enviar_cocina, pantalla_cocina, ordenes_cocina
│  ├─ caja: cobrar, cambiar_tasa
│  ├─ facturas: factura, facturas_pendientes, activar/desactivar
│  ├─ inventario: compras, produccion, recetas, descontar_inventario_por_orden
│  ├─ reportes: construir_reporte_rango, dashboard, exportar_reporte
│  └─ cierre: construir_resumen_cierre, cerrar_jornada
└─ UI embebida
   ├─ estilos_base
   ├─ barra_superior
   ├─ HTML por ruta
   ├─ CSS por ruta
   └─ JavaScript por ruta
```

### 4.2 Funciones reutilizadas muchas veces

| Función | Llamadores aproximados | Comentario |
|---|---:|---|
| `get_connection` | 61 | Mayor dependencia transversal; debe extraerse temprano pero con mucho cuidado. |
| `a_float` | 18 | Helper puro; excelente candidato temprano. |
| `barra_superior` | 16 | UI compartida; mover cuando existan templates. |
| `usuario_es_admin_cierre` | 15 | Permiso delicado; no mover antes de auth service. |
| `estilos_base` | 14 | CSS global; futuro `static`. |
| `usuario_rol` | 13 | Núcleo de seguridad; riesgo alto. |
| `ahora_venezuela` | 12 | Helper puro de fecha; buen candidato temprano. |
| `usuario_es_master` | 12 | Seguridad; mover con auth completo. |
| `texto_numero_orden` | 8 | Helper puro. |
| `quitar_prefijo_cantidad_visual` | 7 | Helper items; candidato temprano. |
| `obtener_tasa_actual` | 7 | DB/configuración; mover después de capa DB. |

### 4.3 Duplicaciones y acoplamientos detectados

- HTML se repite por rutas; cada pantalla construye su propio documento.
- CSS se repite en bloques `<style>` además de `estilos_base()`.
- Validaciones de permisos aparecen en `proteger_sistema()` y también dentro de rutas.
- Patrón `conn = get_connection(); cursor = conn.cursor(); ...; conn.commit(); conn.close()` se repite muchas veces.
- Contratos de cocina/factura están mezclados con rutas y reglas de presentación.
- Las reglas de combos/promociones se distribuyen entre constantes, HTML/JS de `orden()` y validación en `agregar()`.

## 5. Mapa de Rutas Flask

| URL | Método | Función | Línea | Dependencias principales | Devuelve | Tablas usadas | Riesgo |
|---|---|---|---:|---|---|---|---|
| `/login` | GET, POST | `login` | 2306 | `get_connection`, `estilos_base` | HTML/redirect | `usuarios` | Alto |
| `/logout` | GET | `logout` | 2465 | Session | Redirect | - | Bajo |
| `/usuarios` | GET | `usuarios` | 2486 | Auth, UI, SQL | HTML/texto | `usuarios` | Alto |
| `/crear_usuario` | POST | `crear_usuario` | 2612 | Auth, SQL | Redirect/texto | `usuarios` | Alto |
| `/editar_usuario/<int:usuario_id>` | GET, POST | `editar_usuario` | 2639 | Auth, UI, SQL | HTML/redirect | `usuarios` | Alto |
| `/activar_usuario/<int:usuario_id>` | POST | `activar_usuario` | 2730 | Auth, SQL | Redirect/texto | `usuarios` | Alto |
| `/` | GET | `index` | 2750 | Auth, SQL, UI | HTML | `ordenes`, `usuarios` | Alto |
| `/menu` | GET, POST | `menu` | 2987 | SQL, UI | HTML | `categorias`, `productos` | Alto |
| `/inventario` | GET | `inventario` | 3090 | Auth, SQL, UI | HTML | `inventario` | Alto |
| `/recetas` | GET, POST | `recetas` | 3178 | Auth, SQL, JS, UI | HTML/redirect | `inventario`, `productos`, `recetas` | Alto |
| `/eliminar_receta/<int:receta_id>` | GET | `eliminar_receta` | 3345 | Auth, SQL | Redirect/texto | `recetas` | Alto |
| `/movimientos_inventario` | GET | `movimientos_inventario` | 3358 | Auth, SQL, UI | HTML/texto | `movimientos_inventario` | Alto |
| `/compras` | GET, POST | `compras` | 3433 | Session, SQL, inventario | HTML/redirect | `compras`, `productos_base`, `proveedores` | Alto |
| `/proveedores` | GET, POST | `proveedores` | 3740 | SQL, UI | HTML/redirect | `proveedores` | Alto |
| `/productos_base` | GET, POST | `productos_base` | 3841 | SQL, UI | HTML/redirect | `productos_base` | Alto |
| `/produccion` | GET, POST | `produccion` | 3946 | SQL, inventario, costos | HTML/redirect | `inventario`, `producciones`, `productos_base` | Alto |
| `/agregar_producto` | POST | `agregar_producto` | 4222 | SQL | Redirect/texto | `productos` | Alto |
| `/eliminar_producto/<int:id>` | GET | `eliminar_producto` | 4249 | SQL | Redirect | `productos` | Alto |
| `/editar_producto/<int:id>` | GET, POST | `editar_producto` | 4259 | SQL, UI | HTML/redirect | `categorias`, `productos` | Alto |
| `/nueva_orden` | GET | `nueva_orden` | 4340 | - | Redirect | - | Bajo |
| `/crear_orden` | POST | `crear_orden` | 4345 | Session, SQL, fecha | Redirect | `ordenes` | Alto |
| `/orden/<int:orden_id>` | GET | `orden` | 4371 | SQL, combos, promos, JS, UI | HTML/texto | `categorias`, `orden_items`, `ordenes`, `productos`, `usuarios` | Alto |
| `/agregar/<int:orden_id>/<int:producto_id>` | GET | `agregar` | 4961 | Request, combos/promos, SQL | Redirect/texto | `orden_items`, `ordenes`, `productos` | Alto |
| `/enviar_cocina/<int:orden_id>` | GET | `enviar_cocina` | 5072 | Número orden, SQL | Redirect/texto | `ordenes` | Alto |
| `/reimprimir_cocina/<int:orden_id>` | GET | `reimprimir_cocina` | 5108 | Auth, token, SQL | Redirect/texto | `ordenes` | Alto |
| `/eliminar_item/<int:item_id>/<int:orden_id>` | POST | `eliminar_item` | 5150 | Supervisor, emergencia, SQL | Redirect/texto | `orden_items`, `ordenes` | Alto |
| `/actualizar_indicacion_item/<int:item_id>/<int:orden_id>` | POST | `actualizar_indicacion_item` | 5200 | Emergencia, SQL | Redirect/texto | `orden_items`, `ordenes` | Alto |
| `/editar_orden/<int:orden_id>` | GET, POST | `editar_orden` | 5259 | Emergencia, SQL, UI | HTML/redirect | `ordenes`, `usuarios` | Alto |
| `/eliminar_orden/<int:orden_id>` | GET, POST | `eliminar_orden` | 5354 | Supervisor, SQL | Redirect/texto | `orden_items`, `ordenes`, `pagos` | Alto |
| `/activar_edicion_emergencia/<int:orden_id>` | POST | `activar_edicion_emergencia` | 5396 | Auth, auditoría, SQL | Redirect/texto | `ordenes` | Alto |
| `/cobrar/<int:orden_id>` | GET, POST | `cobrar` | 5443 | Pagos, tasa, inventario, SQL | HTML/redirect | `orden_items`, `ordenes`, `pagos`, `usuarios` | Alto |
| `/cambiar_tasa` | GET, POST | `cambiar_tasa` | 5771 | SQL, UI | HTML | `tasa` | Alto |
| `/exportar` | GET | `exportar` | 5807 | SQL, stream | Texto/stream | `orden_items`, `ordenes`, `pagos`, `usuarios` | Alto |
| `/revertir_orden_cierre/<int:orden_id>` | POST | `revertir_orden_cierre` | 5912 | Auth, SQL | Redirect/texto | `ordenes` | Alto |
| `/reportes` | GET | `reportes` | 5962 | Reportes, UI, JS | HTML/texto | Vía `construir_reporte_rango` | Alto |
| `/exportar_reporte` | GET | `exportar_reporte` | 6120 | Reportes, XLSX | Response/texto | Vía `construir_reporte_rango` | Medio |
| `/dashboard` | GET | `dashboard` | 6222 | Reportes, UI | HTML/texto | Vía `construir_reporte_rango` | Alto |
| `/cierre` | GET | `cierre` | 6365 | Cierre, UI | HTML/texto | Vía `construir_resumen_cierre` | Alto |
| `/cerrar_jornada` | GET | `cerrar_jornada` | 6509 | Cierre, SQL | HTML/texto | `cierre_detalle`, `cierres_caja`, `ordenes` | Alto |
| `/cocina` | GET | `pantalla_cocina` | 6627 | Cocina, SQL, UI, JS | HTML | `orden_items`, `ordenes`, `usuarios` | Alto |
| `/listo/<int:orden_id>` | GET | `marcar_listo` | 6777 | SQL | Redirect | `ordenes` | Alto |
| `/ordenes_cocina` | GET | `ordenes_cocina` | 6790 | Cocina, SQL, JSON | JSON | `orden_items`, `ordenes`, `usuarios` | Alto |
| `/factura/<int:orden_id>` | GET | `factura` | 6866 | Factura, SQL, UI | HTML/texto | `orden_items`, `ordenes`, `usuarios` | Alto |
| `/cerrar_dia` | GET | `cerrar_dia` | 6941 | - | Redirect | - | Bajo |
| `/api/tasa` | GET | `api_tasa` | 6946 | Tasa, JSON | JSON | `tasa` vía helper | Medio |
| `/facturas_pendientes` | GET | `facturas_pendientes` | 6960 | Facturas, SQL, JSON | JSON | `orden_items`, `ordenes`, `usuarios` | Alto |
| `/activar_factura/<int:orden_id>` | GET | `activar_factura` | 7030 | SQL | Redirect | `ordenes` | Alto |
| `/reimprimir_factura/<int:orden_id>` | GET | `reimprimir_factura` | 7043 | Token, SQL | Redirect/texto | `ordenes` | Alto |
| `/desactivar_factura/<int:orden_id>` | GET | `desactivar_factura` | 7080 | SQL, JSON, rollback | JSON | `ordenes` | Alto |
| `/reset_neko` | GET, POST | `reset_neko` | 7193 | Admin, reset, HTML | HTML/texto | Vía `_reset_neko_wok_db` | Alto |

## 6. Base de Datos

### 6.1 Funciones que crean tablas

- `crear_tablas_cierre_jornada`
- `crear_tablas_inventario`
- `init_db`

### 6.2 Funciones que alteran tablas

- `asegurar_columna`
- `asegurar_columna_facturar`
- `crear_tablas_cierre_jornada`
- `init_db`

### 6.3 Funciones que escriben datos

- `asegurar_columna_facturar`
- `limpiar_facturas_archivadas`
- `crear_usuarios_iniciales`
- `registrar_auditoria_emergencia`
- `registrar_movimiento_inventario`
- `descontar_inventario_por_orden`
- `crear_datos_base_inventario`
- `sumar_inventario_con_costo`
- `init_db`
- `cargar_productos`
- `asegurar_menu_neko_wok`
- `desactivar_menu_china_house`
- `menu`
- `crear_usuario`
- `editar_usuario`
- `activar_usuario`
- `recetas`
- `eliminar_receta`
- `compras`
- `proveedores`
- `productos_base`
- `produccion`
- `agregar_producto`
- `eliminar_producto`
- `editar_producto`
- `crear_orden`
- `agregar`
- `enviar_cocina`
- `reimprimir_cocina`
- `eliminar_item`
- `actualizar_indicacion_item`
- `editar_orden`
- `eliminar_orden`
- `activar_edicion_emergencia`
- `cobrar`
- `cambiar_tasa`
- `revertir_orden_cierre`
- `cerrar_jornada`
- `marcar_listo`
- `ordenes_cocina` (limpia tokens de reimpresión)
- `activar_factura`
- `reimprimir_factura`
- `desactivar_factura`
- `_reset_neko_wok_db`

### 6.4 Funciones principalmente de lectura

- `login`
- `usuarios`
- `index`
- `inventario`
- `movimientos_inventario`
- `orden`
- `exportar`
- `reportes`
- `exportar_reporte`
- `dashboard`
- `cierre`
- `pantalla_cocina`
- `factura`
- `api_tasa`
- `facturas_pendientes`
- `construir_resumen_cierre`
- `construir_reporte_rango`
- `obtener_tasa_actual`
- `obtener_costo_promedio_producto`
- `siguiente_numero`

### 6.5 Funciones con commit

El archivo contiene 46 commits explícitos. Las funciones con commit son las zonas de mayor cuidado: setup/migraciones, usuarios, menú, inventario, órdenes, cobro, cierre, cocina, facturas y reset.

### 6.6 Funciones con rollback

- `cobrar`
- `desactivar_factura`
- `_reset_neko_wok_db`

### 6.7 Riesgos DB

- Las migraciones ocurren en runtime.
- `init_db()` se ejecuta al importar/arrancar la app.
- La compatibilidad SQLite/PostgreSQL depende de wrappers manuales.
- Hay SQL dinámico con placeholders generados para listas.
- No existe capa repository ni migraciones versionadas.

## 7. HTML

### 7.1 Pantallas principales con HTML embebido

| Función | Líneas | Pantalla | Formularios | Rutas consumidas |
|---|---:|---|---|---|
| `login` | 2306-2464 | Login por usuario/PIN | Login | `/login` |
| `usuarios` | 2486-2611 | Administración usuarios | Crear usuario, acciones | `/crear_usuario`, `/editar_usuario`, `/activar_usuario` |
| `editar_usuario` | 2639-2729 | Editar usuario | Editar usuario | `/editar_usuario/<id>` |
| `index` | 2750-2986 | Inicio POS / órdenes activas | Crear orden | `/crear_orden`, `/orden/<id>` |
| `menu` | 2987-3089 | Administración menú | Categorías/productos | `/menu`, `/agregar_producto` |
| `inventario` | 3090-3177 | Inventario | Navegación/acciones | Inventario y módulos relacionados |
| `recetas` | 3178-3344 | Recetas | Crear receta | `/recetas`, `/eliminar_receta` |
| `movimientos_inventario` | 3358-3432 | Movimientos inventario | Filtros | `/movimientos_inventario` |
| `compras` | 3433-3739 | Compras | Compra temporal/guardar | `/compras` |
| `proveedores` | 3740-3840 | Proveedores | Crear proveedor | `/proveedores` |
| `productos_base` | 3841-3945 | Productos base | Crear producto base | `/productos_base` |
| `produccion` | 3946-4221 | Producción | Producción/insumos | `/produccion` |
| `editar_producto` | 4259-4339 | Editar producto menú | Editar producto | `/editar_producto/<id>` |
| `orden` | 4371-4960 | Pantalla de venta/orden | Eliminar item/orden, modales JS | `/agregar`, `/enviar_cocina`, `/cobrar`, etc. |
| `editar_orden` | 5259-5353 | Editar cabecera orden | Editar orden | `/editar_orden/<id>` |
| `cobrar` | 5443-5770 | Cobro | Pagos, descuento | `/cobrar/<id>` |
| `cambiar_tasa` | 5771-5806 | Tasa | Cambiar tasa | `/cambiar_tasa` |
| `reportes` | 5962-6119 | Reportes por rango | Filtros | `/reportes`, `/exportar_reporte` |
| `dashboard` | 6222-6364 | Dashboard | Filtros | `/dashboard` |
| `cierre` | 6365-6508 | Resumen cierre | Cerrar/revertir | `/cerrar_jornada`, `/revertir_orden_cierre` |
| `cerrar_jornada` | 6509-6626 | Confirmación cierre | Navegación | `/cierre` |
| `pantalla_cocina` | 6627-6776 | Cocina | Botones listo | `/listo/<id>` |
| `factura` | 6866-6940 | Factura HTML | Ninguno principal | `/factura/<id>` |
| `reset_neko` | 7193-7332 | Reset admin | Confirmación reset | `/reset_neko` |

### 7.2 Observaciones HTML

- La vista `orden()` es la más grande y crítica: contiene layout, productos, panel de orden, acciones, modales y JS de configuración.
- `cobrar()` contiene UI y lógica de pagos en la misma función.
- `compras()` y `produccion()` mezclan formularios, sesiones temporales, SQL e inventario.
- `pantalla_cocina()` mezcla layout operativo, temporizadores visuales, agrupación de items y acciones.

## 8. JavaScript

Se detectan 7 bloques `<script>`.

| Zona | Función | Qué hace | Endpoints relacionados |
|---|---|---|---|
| Recetas | `recetas` | Mejora interacción del formulario/selección. | `/recetas` |
| Compras | `compras` | Gestión visual de compra temporal y validaciones. | `/compras` |
| Orden | `orden` | Modales/configuración de refrescos, combos, promociones, confirmaciones. | `/agregar/<orden>/<producto>`, `/cobrar`, `/enviar_cocina` |
| Cobro | `cobrar` | Selección visual de métodos de pago y campos asociados. | `/cobrar/<id>` |
| Reportes | `reportes` | Interacción de filtros/exportación. | `/reportes`, `/exportar_reporte` |
| Cocina | `pantalla_cocina` | Sonido/check de nuevas órdenes y refresh. | `/cocina`, `/listo/<id>` |
| Reset/otros modales | Varias pantallas | Confirmaciones operativas. | Rutas admin |

Riesgo JS: el JS de `orden()` está fuertemente acoplado a query params de `/agregar`, por lo que no debe separarse antes de estabilizar servicios de menú/combos/promos.

## 9. CSS

Se detectan 30 bloques `<style>`.

### Clasificación

| Tipo CSS | Ubicación | Riesgo | Futuro |
|---|---|---|---|
| CSS base global | `estilos_base()` | Medio | `static/css/base.css`. |
| Barra superior | `barra_superior()` y pantallas | Medio | Template parcial + CSS global. |
| Pantallas admin | Usuarios, menú, inventario | Medio | CSS por módulo. |
| Pantalla orden | `orden()` | Alto | Separar al final junto con template. |
| Cobro | `cobrar()` | Alto | Separar después de estabilizar pagos. |
| Cocina | `pantalla_cocina()` | Alto | Separar después de proteger API cocina. |
| Reportes/dashboard/cierre | Reportes/cierre | Medio | CSS de reporting. |
| Reset | `reset_neko()` | Alto | Mantener aislado; acción destructiva. |

## 10. Riesgos

### 10.1 Funciones gigantes

| Función | Líneas | Riesgo |
|---|---:|---|
| `orden` | 590 | Muy alto |
| `cobrar` | 328 | Muy alto |
| `compras` | 307 | Alto |
| `produccion` | 276 | Alto |
| `index` | 237 | Alto |
| `construir_reporte_rango` | 215 | Alto |
| `init_db` | 171 | Alto |
| `construir_resumen_cierre` | 169 | Alto |
| `recetas` | 167 | Alto |
| `login` | 159 | Alto |
| `reportes` | 158 | Alto |
| `pantalla_cocina` | 150 | Alto |
| `cierre` | 144 | Alto |
| `dashboard` | 143 | Alto |
| `reset_neko` | 140 | Alto |
| `proteger_sistema` | 127 | Alto |
| `usuarios` | 126 | Alto |
| `cerrar_jornada` | 118 | Alto |
| `descontar_inventario_por_orden` | 114 | Alto |
| `agregar` | 111 | Alto |

### 10.2 Funciones con demasiadas responsabilidades

- `orden`: UI, productos, combos, promociones, permisos, estados, modales, JS.
- `cobrar`: validación, UI, pagos, descuentos, reemplazo de pagos, estado, inventario y auditoría.
- `compras`: UI, sesión temporal, proveedores, inventario, costos.
- `produccion`: UI, producción, merma, porciones, insumos, costos.
- `init_db`: creación, migración, seeds y llamadas a setup.
- `proteger_sistema`: tabla manual de permisos por endpoint.

### 10.3 Acoplamientos fuertes

- `web_app.py` como único módulo.
- Rutas HTML acopladas a SQL directo.
- Scripts locales acoplados a JSON de rutas específicas.
- `DATABASE_URL` controla motor DB en runtime.
- Combo/promoción acoplados a HTML, JS y validación en `/agregar`.
- Inventario se descuenta desde `cobrar`.

### 10.4 Código muerto o poco usado

Funciones sin llamadas directas detectadas:

- `es_combo_con_favorito`
- `usuario_es_mesonera`
- `usuario_es_cocina`
- `usuario_es_socio`
- `usuario_puede_editar_inventario`
- `usuario_puede_admin_total`
- `obtener_costo_promedio_producto`

No se deben borrar sin auditoría manual: algunas pueden estar reservadas para uso futuro o llamadas indirectas.

### 10.5 Rutas extremadamente críticas

- `/orden/<id>`
- `/agregar/<orden_id>/<producto_id>`
- `/cobrar/<orden_id>`
- `/ordenes_cocina`
- `/facturas_pendientes`
- `/desactivar_factura/<id>`
- `/cerrar_jornada`
- `/reset_neko`

## 11. Oportunidades de Modularización

### Mover primero

Motivo: bajo acoplamiento, sin SQL o con lógica pura.

- Constantes: roles, métodos de pago, sabores, combos, promociones, menú.
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

### Mover después

Motivo: requieren capa DB o servicios ya definidos.

- `get_connection`
- `adaptar_query`
- Wrappers DB
- `obtener_tasa_actual`
- `registrar_movimiento_inventario`
- `agrupar_items_comanda`
- `agrupar_items_factura`
- `convertir_pago_equivalente`
- `construir_resumen_cierre`
- `construir_reporte_rango`
- `sumar_inventario_con_costo`
- `descontar_inventario_por_orden`

### Mover al final

Motivo: rutas grandes, críticas o muy acopladas.

- `orden`
- `agregar`
- `cobrar`
- `pantalla_cocina`
- `ordenes_cocina`
- `facturas_pendientes`
- `cerrar_jornada`
- `proteger_sistema`
- `init_db`
- `reset_neko`
- `_reset_neko_wok_db`

### Nunca mover directamente

Motivo: deben descomponerse primero.

- `orden`: extraer servicios de menú/combos/promos, template y JS antes.
- `cobrar`: extraer pagos, totales, validaciones, inventario y template antes.
- `init_db`: separar schema/migrations/seeds primero.
- `proteger_sistema`: convertir permisos en matriz/configuración antes.

## 12. Propuesta de Extracción

### Paso 1 - `constants.py`

Mover:

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

Riesgo: bajo si solo se importa.

### Paso 2 - `utils/fechas.py` y `utils/formato.py`

Mover:

- `ahora_venezuela`
- `parsear_fecha_hora_venezuela`
- `a_float`
- `texto_numero_orden`

Riesgo: bajo.

### Paso 3 - `utils/items.py`

Mover:

- `normalizar_sabor_refresco`
- `normalizar_indicacion_item`
- `quitar_prefijo_cantidad_visual`
- `separar_prefijo_cantidad`
- `producto_sin_prefijo_cantidad`
- `texto_item_con_indicacion`

Riesgo: bajo-medio por cocina/factura.

### Paso 4 - `utils/pagos.py`

Mover:

- `normalizar_metodo_pago`
- `etiqueta_metodo_pago`
- `monto_formateado_segun_metodo`
- `convertir_pago_equivalente`

Riesgo: medio por cobro/reportes.

### Paso 5 - `database/connection.py`

Mover:

- `normalizar_database_url`
- `es_postgres`
- `adaptar_query`
- `CursorWrapper`
- `ConnectionWrapper`
- `get_connection`
- `pk_autoincrement_sql`
- `obtener_ultimo_id`
- `columna_existe`

Riesgo: alto. Requiere prueba SQLite y PostgreSQL.

### Paso 6 - `database/schema.py`

Mover:

- `asegurar_columna`
- `asegurar_columna_facturar`
- `crear_tablas_cierre_jornada`
- `crear_tablas_inventario`
- Parte estructural de `init_db`

Riesgo: alto. No mezclar con cambios funcionales.

### Paso 7 - `services/menu_service.py`

Mover:

- `es_producto_refresco`
- `es_combo_con_favorito`
- `cargar_productos`
- `asegurar_menu_neko_wok`
- `desactivar_menu_china_house`

Riesgo: medio-alto por productos históricos.

### Paso 8 - `services/cocina_service.py` y `services/factura_service.py`

Mover:

- `nombre_producto_cocina`
- `indicacion_operativa_cocina`
- `agrupar_items_comanda`
- `agrupar_items_factura`

Riesgo: medio. Probar scripts locales.

### Paso 9 - `services/auth_service.py`

Mover:

- `usuario_rol`
- `usuario_es_*`
- `usuario_puede_*`
- `usuario_activo`

Riesgo: alto. Probar permisos.

### Paso 10 - `services/inventario_service.py`

Mover:

- `registrar_movimiento_inventario`
- `descontar_inventario_por_orden`
- `crear_datos_base_inventario`
- `obtener_costo_promedio_producto`
- `sumar_inventario_con_costo`

Riesgo: alto. Probar cobro e inventario.

### Paso 11 - `services/reportes_service.py` y `services/cierre_service.py`

Mover:

- `construir_resumen_cierre`
- `resumen_cierre_pendiente`
- `construir_reporte_rango`
- `generar_xlsx`

Riesgo: medio-alto.

### Paso 12 - Blueprints sin cambiar URLs

Orden:

1. `auth_routes`
2. `usuarios_routes`
3. `menu_routes`
4. `inventario_routes`
5. `reportes_routes`
6. `cocina_routes`
7. `factura_routes`
8. `ordenes_routes`
9. `cobro_routes`
10. `admin_routes`

Riesgo: alto. Preservar endpoints y nombres si `proteger_sistema` sigue usando `request.endpoint`.

### Paso 13 - Templates

Mover HTML una pantalla a la vez.

Orden:

1. Login.
2. Usuarios.
3. Menú.
4. Reportes.
5. Inventario.
6. Cocina.
7. Cobro.
8. Orden.
9. Reset.

### Paso 14 - Static

Mover CSS/JS desde strings y bloques `<style>/<script>`.

Riesgo: medio-alto en `orden`, `cobrar`, `cocina`.

### Paso 15 - Reducir `web_app.py`

Meta final:

- `web_app.py` mantiene `app`.
- Importa módulos.
- Registra Blueprints.
- Conserva compatibilidad Render.

## 13. Estimación

| Concepto | Estimación |
|---|---|
| Tickets necesarios | 25 a 40 tickets pequeños. |
| Tiempo aproximado | 3 a 6 semanas de trabajo cuidadoso, según pruebas disponibles. |
| Complejidad | Alta. |
| Riesgo general | Alto, reducible con fases pequeñas. |
| Mayor riesgo técnico | Cobro, orden, cocina/facturas JSON, cierre, init DB. |
| Mayor riesgo operativo | Romper Render o scripts locales de impresión. |

Distribución sugerida:

- 5 tickets para constantes/utils.
- 5 tickets para database/schema.
- 8 a 12 tickets para servicios.
- 6 a 10 tickets para rutas/Blueprints.
- 6 a 10 tickets para templates/static.

## 14. Conclusión

El proyecto está funcionando como un monolito operativo completo. Su valor principal es que concentra en un solo archivo todo el flujo real del restaurante: venta, cocina, cobro, facturación, cierre, inventario y reportes.

La calidad arquitectónica actual es adecuada para una primera versión funcional, pero limitada para escalar. El archivo tiene alto acoplamiento, funciones gigantes, SQL repetido, HTML/CSS/JS embebido y permisos centralizados por endpoint. Esto hace que cualquier cambio importante deba tratarse como una operación delicada.

La modularización es viable, pero debe hacerse por fases. El camino correcto no es mover rutas primero; es extraer constantes, helpers puros, capa DB y servicios pequeños antes de tocar las rutas críticas. `web_app.py` debe seguir siendo punto de entrada durante todo el proceso, tal como indica la decisión ADR-001.

Recomendaciones principales:

- No iniciar por `/orden`, `/cobrar`, `/ordenes_cocina` ni `/facturas_pendientes`.
- Crear primero estructura vacía y módulos de constantes/utils.
- Mantener pruebas manuales del flujo completo.
- Probar SQLite local y PostgreSQL/Render cuando se toque DB.
- Tratar los scripts locales como consumidores externos de API.
- Mantener cambios pequeños, reversibles y revisables.

