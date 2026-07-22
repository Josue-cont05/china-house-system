# Guía de desarrollo del POS Neko Wok / China House

Este documento describe el estado actual del proyecto y propone una ruta segura para modularizarlo en el futuro. La intención es que sirva como guía para trabajar con Codex sin romper el sistema en GitHub, Render ni en la operación diaria del POS.

## 1. Alcance de esta guía

Este archivo es solo documentación. No cambia rutas, lógica, base de datos ni comportamiento.

Objetivos:

- Documentar la arquitectura actual.
- Documentar reglas de negocio existentes.
- Identificar rutas críticas que no deben cambiar sin plan.
- Proponer módulos futuros.
- Definir fases de separación de `web_app.py`.
- Dar criterios para decidir qué mover primero y qué mover al final.

## 2. Diferencia entre descripción y observación

Al trabajar con Codex conviene separar dos tipos de notas:

- **Descripción:** explica lo que el código hace hoy, sin juzgar si está bien o mal.
- **Observación:** señala riesgos, fragilidad, deuda técnica o algo que requiere cuidado antes de modificar.

Ejemplo:

- **Descripción:** `web_app.py` crea las tablas al iniciar la aplicación.
- **Observación:** como la creación y migración de columnas ocurre al arrancar, importar o ejecutar la app puede modificar la base de datos.

Esta diferencia ayuda a evitar cambios prematuros. Primero se entiende el sistema; después se decide qué mejorar.

## 3. Arquitectura actual

El proyecto está concentrado casi por completo en un solo archivo:

- `web_app.py`: aplicación Flask completa.
- `requirements.txt`: dependencias del servidor.
- `china_house.db`: base SQLite local.
- `scripts_locales/script_comanda_cocina.py`: script local para imprimir comandas.
- `scripts_locales/script_factura.py`: script local para imprimir facturas.
- `scripts_locales/facturas_impresas.txt`: registro local de facturas ya impresas.
- `scripts_locales/tasa_cache.txt`: cache local de la tasa usada por el script de facturas.

### Descripción

`web_app.py` contiene:

- Configuración de Flask.
- Configuración de base de datos.
- Conexión compatible con SQLite y PostgreSQL.
- Definición de constantes de menú, combos y promociones.
- Funciones utilitarias.
- Creación y actualización de tablas.
- Lógica de usuarios y permisos.
- Rutas HTTP.
- HTML, CSS y JavaScript embebidos.
- Lógica de órdenes, cocina, cobro, facturas, reportes, cierre e inventario.

### Observación

No existe todavía una separación por capas como `routes`, `services`, `repositories`, `templates` o `static`. Por eso, cualquier cambio en `web_app.py` debe hacerse con cuidado: una función puede afectar UI, base de datos y flujo operativo al mismo tiempo.

## 4. Base de datos: SQLite local y PostgreSQL en Render

### Descripción

La app soporta dos modos:

- **SQLite local:** usado por defecto con `china_house.db`.
- **PostgreSQL:** usado cuando existe la variable de entorno `DATABASE_URL`.

La configuración se carga en `cargar_configuracion()`. La conexión se obtiene con `get_connection()`.

La función `adaptar_query()` cambia placeholders `?` por `%s` cuando se usa PostgreSQL.

### Observación

La compatibilidad entre SQLite y PostgreSQL es manual. Esto exige mucho cuidado al mover funciones SQL, porque:

- Las queries usan `?` como formato base.
- En PostgreSQL se reemplazan dinámicamente por `%s`.
- Algunas operaciones especiales usan lógica condicional, como autoincremento y obtención del último ID.
- No hay sistema formal de migraciones.

Regla para futuros cambios:

- No introducir SQL nuevo sin probar mentalmente si funciona en SQLite y PostgreSQL.
- Mantener las queries parametrizadas.
- Evitar SQL específico de un motor salvo que esté encapsulado detrás de una función.

## 5. Tablas principales

### POS y ventas

- `ordenes`: cabecera de órdenes.
- `orden_items`: productos agregados a cada orden.
- `pagos`: pagos registrados.
- `productos`: productos del menú.
- `categorias`: categorías del menú.
- `tasa`: tasa de cambio.

### Usuarios y permisos

- `usuarios`: usuarios, PIN, rol y estado activo.

### Cocina y facturación

No hay tablas separadas para cocina o facturas. Se usan columnas de `ordenes`, por ejemplo:

- `estado`
- `numero_orden`
- `reimpresion_token`
- `facturar`
- `factura_reimpresion_token`

### Cierres y reportes

- `cierres`
- `cierres_caja`
- `cierre_detalle`

### Inventario y producción

- `inventario`
- `compras`
- `producciones`
- `proveedores`
- `productos_base`
- `recetas`
- `movimientos_inventario`
- `ingredientes`

### Auditoría

- `auditoria_emergencias`

## 6. Reglas de negocio actuales

### Usuarios y roles

Roles válidos:

- `master`
- `mesonera`
- `cocina`
- `socio`
- `mesonera_reportes`
- `cocina_reportes`

Reglas generales:

- `master` tiene acceso total.
- `mesonera` toma órdenes y cobra.
- `cocina` ve cocina, inventario y producción según permisos definidos.
- `socio` puede ver reportes y también tomar órdenes según la lógica actual.
- Roles de reportes tienen permisos mixtos.

La protección central está en `proteger_sistema()`, que se ejecuta antes de cada request.

### Menú

El menú actual de Neko Wok se define en constantes:

- `ORDEN_CATEGORIAS_POS`
- `COLORES_CATEGORIAS_POS`
- `PRODUCTOS_MENU_NEKO`

Funciones relacionadas:

- `cargar_productos()`: carga menú antiguo si la tabla está vacía.
- `asegurar_menu_neko_wok()`: sincroniza productos y categorías Neko Wok.
- `desactivar_menu_china_house()`: marca como inactivo el menú antiguo de China House.

Observación:

- El sistema conserva productos históricos, pero usa `activo=0` para ocultar categorías/productos antiguos.
- No se debe cambiar nombres de productos sin revisar recetas, cocina, facturación y reportes.

## 7. Reglas de combos

Los combos personales están en `COMBOS_PERSONALES`.

### Neko Combo 1

- Arroz fijo: `Arroz de pollo`.
- Bebida fija: `Coca Cola Personal`.
- Requiere seleccionar 1 favorito.
- Favoritos disponibles:
  - `Pollo Agridulce`
  - `Chop Suey de Pollo`

### Neko Combo 2

- Arroz fijo: `Arroz de pollo`.
- Bebida fija: `Coca Cola Personal`.
- No requiere favorito seleccionable.
- Incluye favoritos fijos:
  - `Pollo Agridulce`
  - `Chop Suey de Pollo`

### Neko Combo 3

- Arroz fijo: `Arroz triple`.
- Bebida fija: `Coca Cola Personal`.
- No requiere favorito seleccionable.
- Incluye favoritos fijos:
  - `Pollo Agridulce`
  - `Chop Suey de Pollo`

### Comportamiento actual

Cuando se agrega un combo:

- Se valida que los favoritos seleccionados sean válidos.
- Se guarda una `indicacion` con los detalles del combo.
- Cocina simplifica algunos nombres mediante `NOMBRES_COCINA_SIMPLIFICADOS`.
- Para cocina, en combos personales se muestra principalmente la información operativa del favorito.

Observación:

- Las reglas de combos están mezcladas entre constantes, ruta `/orden/<id>`, ruta `/agregar/<orden_id>/<producto_id>` y funciones de agrupación para cocina/factura.
- Si se modulariza, primero conviene mover constantes y helpers puros, no la ruta completa.

## 8. Reglas de promociones

Las promociones están en `PROMOCIONES_NEKO`.

### Wok para Dos

- Requiere 1 arroz.
- Requiere 1 refresco.
- Refresco: `Refresco 1 Lt`.

### Familiar

- Requiere 1 arroz.
- Requiere 1 refresco.
- Refresco: `Refresco 1.5 Lt`.

### Mega Familiar

- Requiere 2 arroces.
- Requiere 2 refrescos.
- Refresco: `Refresco 1.5 Lt`.

### Arroces disponibles

Lista `ARROCES_PROMOCION`:

- `Pollo + Cerdo`
- `Pollo + Camarón`
- `Triple`

### Extra de lumpias

Existe una promoción extra:

- Nombre: `Promo extra: Ración de Lumpias`
- Precio: `3.00`

Cuando una promoción permite `extra_lumpias=1`, se inserta un item adicional en `orden_items`.

### Comportamiento actual

Cuando se agrega una promoción:

- Se valida la cantidad exacta de arroces.
- Se valida que cada arroz esté en la lista permitida.
- Se valida la cantidad exacta de sabores de refresco.
- Se normalizan los sabores.
- Se guarda la selección en `indicacion`.
- Cocina muestra principalmente los arroces seleccionados.
- Factura puede mostrar el detalle completo agrupado.

Observación:

- Las promociones dependen de query params generados desde HTML/JS embebido.
- Cambiar nombres de campos o rutas puede romper el flujo de agregar promociones.

## 9. Flujo orden -> cocina -> cobro

### 1. Crear orden

Ruta:

- `/crear_orden`

Comportamiento:

- Crea una orden con estado `abierta`.
- Guarda tipo, referencia, cliente, fecha, hora y usuario.
- `numero_orden` queda inicialmente vacío.

### 2. Agregar productos

Rutas:

- `/orden/<orden_id>`
- `/agregar/<orden_id>/<producto_id>`

Comportamiento:

- La vista de orden muestra productos activos.
- Refrescos requieren sabor.
- Combos requieren sus reglas.
- Promociones requieren arroces, refrescos y opcionalmente extra de lumpias.
- Se insertan filas en `orden_items`.

### 3. Enviar a cocina

Ruta:

- `/enviar_cocina/<orden_id>`

Comportamiento:

- Si la orden no tiene número, se calcula con `siguiente_numero()`.
- Cambia estado a `en cocina`.
- La orden aparece en pantalla de cocina y en API de comandas.

### 4. Cocina

Rutas:

- `/cocina`
- `/ordenes_cocina`
- `/listo/<orden_id>`
- `/reimprimir_cocina/<orden_id>`

Comportamiento:

- `/cocina` muestra órdenes en estado `en cocina`.
- `/ordenes_cocina` devuelve JSON para el script local de impresión.
- `/listo/<orden_id>` cambia estado a `listo`.
- Reimpresión usa `reimpresion_token`.

### 5. Cobro

Ruta:

- `/cobrar/<orden_id>`

Comportamiento:

- Valida que la orden no esté archivada en cierre.
- No permite cobrar orden vacía.
- Calcula total USD desde `orden_items`.
- Convierte a bolívares usando `tasa`.
- Aplica descuento en bolívares.
- Permite uno o dos pagos.
- Métodos válidos:
  - `punto_venta`
  - `bs_pago_movil`
  - `pago_movil`
  - `bs_efectivo`
  - `usd`
- Borra pagos anteriores de la orden y registra los nuevos.
- Cambia estado a `cerrada`.
- Descuenta inventario mediante `descontar_inventario_por_orden()`.

### 6. Factura

Rutas:

- `/activar_factura/<orden_id>`
- `/reimprimir_factura/<orden_id>`
- `/facturas_pendientes`
- `/desactivar_factura/<orden_id>`
- `/factura/<orden_id>`

Comportamiento:

- La factura pendiente se controla con `ordenes.facturar`.
- El script local consulta `/facturas_pendientes`.
- Después de imprimir, el script llama a `/desactivar_factura/<orden_id>`.
- Reimpresión usa `factura_reimpresion_token`.

## 10. Scripts locales de impresión

### `script_comanda_cocina.py`

Consulta:

- `https://china-house-system-3be6.onrender.com/ordenes_cocina`

Funciones:

- Consulta periódica de comandas.
- Agrupa items.
- Imprime en la impresora predeterminada de Windows usando `win32print`.
- Usa sonido con `winsound`.
- Evita duplicados en memoria con `evento_impresion`.

### `script_factura.py`

Consulta:

- `/facturas_pendientes`
- `/api/tasa`
- `/desactivar_factura/<id>`

Funciones:

- Obtiene facturas pendientes.
- Obtiene tasa actual.
- Usa cache local de tasa si Render está lento o falla.
- Registra facturas impresas en `facturas_impresas.txt`.
- Imprime usando comandos ESC/POS.

Observación:

- Estas rutas son contrato externo para los scripts locales.
- No deben cambiar nombres, formato JSON ni significado de campos sin actualizar scripts y probar impresión.

## 11. Rutas críticas que no deben cambiar sin plan

Estas rutas forman parte del flujo operativo o de integración externa:

- `/login`
- `/logout`
- `/`
- `/crear_orden`
- `/orden/<int:orden_id>`
- `/agregar/<int:orden_id>/<int:producto_id>`
- `/enviar_cocina/<int:orden_id>`
- `/cobrar/<int:orden_id>`
- `/cocina`
- `/listo/<int:orden_id>`
- `/ordenes_cocina`
- `/facturas_pendientes`
- `/api/tasa`
- `/activar_factura/<int:orden_id>`
- `/reimprimir_factura/<int:orden_id>`
- `/desactivar_factura/<int:orden_id>`
- `/factura/<int:orden_id>`
- `/cierre`
- `/cerrar_jornada`
- `/reportes`
- `/dashboard`
- `/inventario`
- `/compras`
- `/produccion`
- `/recetas`
- `/usuarios`
- `/reset_neko`

Regla recomendada:

- Durante modularización, mantener las mismas rutas y endpoints.
- Si se usan Blueprints en el futuro, preservar URLs.
- Probar scripts locales antes de cambiar cualquier respuesta JSON.

## 12. Funciones que se pueden mover primero con menor riesgo

Estas funciones son buenas candidatas para mover primero porque son relativamente puras o utilitarias:

### Configuración y tiempo

- `cargar_configuracion()`
- `ahora_venezuela()`
- `parsear_fecha_hora_venezuela()`
- `a_float()`

### Normalización y formato

- `normalizar_metodo_pago()`
- `etiqueta_metodo_pago()`
- `monto_formateado_segun_metodo()`
- `convertir_pago_equivalente()`
- `normalizar_sabor_refresco()`
- `normalizar_indicacion_item()`
- `quitar_prefijo_cantidad_visual()`
- `separar_prefijo_cantidad()`
- `producto_sin_prefijo_cantidad()`
- `texto_item_con_indicacion()`

### Cocina/factura sin DB

- `nombre_producto_cocina()`
- `indicacion_operativa_cocina()`
- `agrupar_items_comanda()`
- `agrupar_items_factura()`

### Exportación

- `xml_cell()`
- `xml_sheet()`
- `generar_xlsx()`

### Constantes

- `METODOS_PAGO_VALIDOS`
- `SABORES_REFRESCO`
- `ETIQUETAS_METODO_PAGO`
- `ROLES_USUARIO_VALIDOS`
- `ORDEN_CATEGORIAS_POS`
- `COLORES_CATEGORIAS_POS`
- `COMBOS_PERSONALES`
- `PROMOCIONES_NEKO`
- `PRODUCTOS_MENU_NEKO`

Regla:

- Mover primero funciones que no abren conexión, no hacen commit y no dependen de `request`, `session` o `g`.

## 13. Funciones que deben moverse con cuidado intermedio

Estas funciones pueden moverse después, pero necesitan pruebas porque interactúan con base de datos:

- `get_connection()`
- `pk_autoincrement_sql()`
- `obtener_ultimo_id()`
- `columna_existe()`
- `asegurar_columna()`
- `obtener_tasa_actual()`
- `crear_tablas_cierre_jornada()`
- `crear_tablas_inventario()`
- `crear_datos_base_inventario()`
- `registrar_movimiento_inventario()`
- `sumar_inventario_con_costo()`
- `obtener_costo_promedio_producto()`
- `calcular_costo_promedio_ponderado()`
- `construir_resumen_cierre()`
- `construir_reporte_rango()`

Regla:

- Antes de moverlas, crear una capa clara de `db.py` o `database.py`.
- Mantener la misma API de función durante la primera fase.
- No cambiar SQL y estructura al mismo tiempo.

## 14. Funciones que deben moverse de último

Estas partes son delicadas porque mezclan flujo operativo, permisos, sesión, HTML, base de datos y efectos secundarios:

- `proteger_sistema()`
- `init_db()`
- `crear_usuarios_iniciales()`
- `asegurar_menu_neko_wok()`
- `desactivar_menu_china_house()`
- `siguiente_numero()`
- `login()`
- `index()`
- `orden()`
- `agregar()`
- `enviar_cocina()`
- `reimprimir_cocina()`
- `cobrar()`
- `pantalla_cocina()`
- `ordenes_cocina()`
- `facturas_pendientes()`
- `desactivar_factura()`
- `cerrar_jornada()`
- `_reset_neko_wok_db()`
- `reset_neko()`

Regla:

- Estas funciones deben moverse solo cuando ya existan módulos base estables.
- Primero se deben extraer helpers internos.
- Luego se pueden mover rutas completas a Blueprints conservando exactamente las mismas URLs.

## 15. Estructura modular futura recomendada

Propuesta conservadora:

```text
pos_china_house/
  app.py
  config.py
  db.py
  constants.py
  utils/
    fechas.py
    formato.py
    pagos.py
    items.py
  services/
    menu_service.py
    orden_service.py
    cocina_service.py
    cobro_service.py
    factura_service.py
    inventario_service.py
    cierre_service.py
    reporte_service.py
    usuario_service.py
  routes/
    auth_routes.py
    pos_routes.py
    menu_routes.py
    cocina_routes.py
    cobro_routes.py
    factura_routes.py
    inventario_routes.py
    reporte_routes.py
    usuario_routes.py
    admin_routes.py
  templates/
  static/
scripts_locales/
  script_comanda_cocina.py
  script_factura.py
web_app.py
```

Primera meta:

- Mantener `web_app.py` como punto de entrada compatible con Render.
- Importar desde módulos nuevos gradualmente.
- No cambiar comando de arranque hasta que todo esté probado.

Ejemplo futuro:

```python
# web_app.py
from pos_china_house.app import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
```

Pero esto debe hacerse al final, no al inicio.

## 16. Fases para dividir `web_app.py` sin romper GitHub ni Render

### Fase 0: Documentación y respaldo

- Crear esta guía.
- Revisar `git status`.
- Confirmar que Render arranca con `web_app:app` o comando equivalente.
- Hacer backup de `china_house.db` antes de pruebas locales.

### Fase 1: Extraer constantes y helpers puros

Crear:

- `constants.py`
- `utils/items.py`
- `utils/pagos.py`
- `utils/fechas.py`

Mover solo:

- Constantes.
- Funciones sin DB.
- Funciones sin Flask globals.

Validación:

- `python -m py_compile web_app.py`
- Arranque local.
- Crear orden de prueba.

### Fase 2: Extraer capa DB

Crear:

- `db.py`

Mover:

- Configuración DB.
- `get_connection()`.
- Wrappers de conexión/cursor.
- Helpers SQL genéricos.

Validación:

- SQLite local.
- Si es posible, prueba en entorno con `DATABASE_URL`.

### Fase 3: Extraer servicios sin cambiar rutas

Crear servicios por dominio:

- `menu_service.py`
- `cocina_service.py`
- `factura_service.py`
- `inventario_service.py`
- `cierre_service.py`

Las rutas siguen en `web_app.py`, pero llaman servicios.

Validación:

- Comparar comportamiento antes/después.
- No cambiar HTML ni rutas todavía.

### Fase 4: Extraer Blueprints

Crear `routes/`.

Mover rutas por grupo:

1. Auth y usuarios.
2. Menú.
3. Inventario.
4. Reportes.
5. Cocina y facturas.
6. Orden/cobro al final.

Regla:

- Cada Blueprint debe registrar las mismas URLs.
- No usar prefijos nuevos como `/api` o `/pos` para rutas existentes.

### Fase 5: Separar templates y static

Crear:

- `templates/`
- `static/`

Mover HTML/CSS/JS lentamente.

Regla:

- No mezclar separación visual con cambios de negocio.
- Una pantalla por PR/cambio.

### Fase 6: Ajustar punto de entrada

Solo al final:

- Crear factory `create_app()` si hace falta.
- Mantener compatibilidad con Render.
- Confirmar que Gunicorn puede importar `app`.

## 17. Recomendación de orden de trabajo

Orden más seguro:

1. Documentación.
2. Helpers puros y constantes.
3. Capa de base de datos.
4. Servicios de lectura/formato.
5. Servicios de reportes.
6. Servicios de inventario.
7. Servicios de cocina/factura.
8. Servicios de menú.
9. Rutas administrativas.
10. Rutas de orden y cobro.
11. Templates/static.
12. App factory y entrada de Render.

Orden a evitar:

- No empezar moviendo `/cobrar`.
- No empezar moviendo `/orden/<id>`.
- No empezar cambiando HTML, rutas y SQL a la vez.
- No cambiar nombres de productos mientras se modulariza.
- No modificar scripts locales sin probar impresión.

## 18. Checklist antes de cualquier cambio futuro

Antes de modificar código:

- Revisar `git status`.
- Confirmar qué archivo se va a tocar.
- Confirmar si el cambio afecta rutas críticas.
- Confirmar si afecta SQLite, PostgreSQL o ambos.
- Confirmar si afecta scripts locales de impresión.
- Confirmar si afecta inventario o cierre.
- Hacer una prueba mínima del flujo completo.

Prueba mínima recomendada:

1. Login.
2. Crear orden.
3. Agregar producto normal.
4. Agregar refresco con sabor.
5. Agregar combo.
6. Agregar promoción.
7. Enviar a cocina.
8. Ver `/ordenes_cocina`.
9. Marcar listo.
10. Cobrar.
11. Activar factura.
12. Ver `/facturas_pendientes`.
13. Revisar reportes/cierre.

## 19. Nota final para Codex

Cuando se trabaje con este proyecto:

- No asumir que `web_app.py` es solo rutas.
- No mover código y cambiar comportamiento en el mismo paso.
- Mantener URLs existentes.
- Mantener JSON de scripts locales.
- Mantener compatibilidad SQLite/PostgreSQL.
- Preferir cambios pequeños, verificables y reversibles.
- Documentar cada fase antes de ejecutarla.

