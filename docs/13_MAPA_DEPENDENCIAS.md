# Mapa de Dependencias de NekoPOS

Este documento describe cómo está construido actualmente el POS desde el punto de vista de dominios de negocio, dependencias funcionales e impacto operativo. Su propósito es guiar la modularización sin romper rutas, datos, Render, SQLite/PostgreSQL ni scripts locales.

## 1. Arquitectura General

El sistema actual está concentrado en `web_app.py`, pero conceptualmente ya contiene dominios separados. La modularización debe respetar esos dominios y separar responsabilidades de forma gradual.

```text
                         ┌─────────────────────┐
                         │   INFRAESTRUCTURA   │
                         │ DB / Render / Utils │
                         └──────────┬──────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
        ┌─────▼─────┐         ┌─────▼─────┐         ┌─────▼─────┐
        │  VENTAS   │         │OPERACIONES│         │ADMIN      │
        │ POS/Caja  │         │Cocina/Inv │         │Reportes   │
        └─────┬─────┘         └─────┬─────┘         └─────┬─────┘
              │                     │                     │
              └─────────────┬───────┴─────────────┬───────┘
                            │                     │
                      ┌─────▼─────┐         ┌─────▼─────┐
                      │ FACTURAS  │         │  CIERRE   │
                      │ APIs local│         │  Jornada  │
                      └───────────┘         └───────────┘
```

## 2. Dominios de Negocio

### 2.1 VENTAS

Incluye:

- Menú.
- Órdenes.
- Caja/cobro.
- Pagos.
- Facturación.

Responsabilidad:

- Presentar productos activos.
- Crear órdenes.
- Agregar productos, combos, promociones y bebidas.
- Enviar pedidos a cocina.
- Cobrar.
- Registrar pagos.
- Activar o reimprimir factura.

Depende de:

- `database`: conexión, SQL, transacciones.
- `utils`: fechas, formato, normalización.
- `menu`: reglas de productos, combos y promociones.
- `auth`: permisos de mesonera/master.
- `inventario`: descuento al cobrar.
- `facturas`: impresión y pendientes.

Módulos que dependen de ventas:

- Cocina.
- Facturación.
- Reportes.
- Cierre.
- Inventario.

Nivel de acoplamiento: Muy alto.

Nivel de riesgo: Rojo.

Motivo:

- `orden()` y `cobrar()` son funciones gigantes.
- `agregar()` contiene reglas de combos/promos/refrescos.
- El cobro cambia estado de orden, registra pagos y descuenta inventario.

### 2.2 OPERACIONES

Incluye:

- Cocina.
- Inventario.
- Producción.
- Compras.
- Recetas.

Responsabilidad:

- Mostrar comandas.
- Marcar órdenes listas.
- Imprimir comandas mediante script local.
- Descontar stock por venta.
- Registrar compras.
- Registrar producción.
- Mantener recetas e insumos.

Depende de:

- Órdenes.
- Menú/productos.
- Base de datos.
- Usuarios/permisos.
- Helpers de agrupación de items.

Módulos que dependen de operaciones:

- Cobro, por descuento de inventario.
- Reportes, por ventas e inventario.
- Cocina, por estado de órdenes.

Nivel de acoplamiento: Alto.

Nivel de riesgo: Rojo/Amarillo según subdominio.

### 2.3 ADMINISTRACIÓN

Incluye:

- Usuarios.
- Roles.
- Permisos.
- Reportes.
- Dashboard.
- Cierre.
- Configuración/tasa.
- Reset.

Responsabilidad:

- Controlar acceso.
- Consultar ventas.
- Exportar reportes.
- Cerrar jornada.
- Cambiar tasa.
- Administrar usuarios.
- Resetear sistema Neko Wok bajo confirmación.

Depende de:

- Base de datos.
- Órdenes.
- Pagos.
- Usuarios.
- Tasa.
- Reportes.

Módulos que dependen de administración:

- Todas las rutas protegidas dependen de permisos.
- Reportes y cierre dependen de ventas y pagos.

Nivel de acoplamiento: Alto.

Nivel de riesgo: Amarillo/Rojo.

### 2.4 INFRAESTRUCTURA

Incluye:

- Base de datos.
- SQLite local.
- PostgreSQL por `DATABASE_URL`.
- Render.
- GitHub.
- Scripts locales.
- Configuración.
- Utilidades.

Responsabilidad:

- Mantener la app ejecutable.
- Conectar a DB.
- Adaptar SQL entre SQLite/PostgreSQL.
- Mantener punto de entrada `web_app.py`.
- Exponer APIs consumidas por scripts locales.

Depende de:

- Variables de entorno.
- `requirements.txt`.
- Convenciones actuales de Render.

Módulos que dependen de infraestructura:

- Todos.

Nivel de acoplamiento: Muy alto.

Nivel de riesgo: Rojo para DB/Render, Verde para helpers puros.

## 3. Mapa Visual de Flujo de Negocio

### 3.1 Flujo operativo principal

```text
MENÚ
  │
  ▼
ÓRDENES
  │
  ├── agregar producto normal
  ├── agregar refresco con sabor
  ├── agregar combo
  └── agregar promoción
  │
  ▼
COCINA
  │
  ├── /cocina
  └── /ordenes_cocina -> script_comanda_cocina.py
  │
  ▼
COBRO
  │
  ├── pagos
  ├── descuento
  ├── cierre de orden
  └── descuento inventario
  │
  ▼
FACTURAS
  │
  ├── /facturas_pendientes -> script_factura.py
  ├── /api/tasa
  └── /desactivar_factura/<id>
  │
  ▼
REPORTES
  │
  ▼
CIERRE DE JORNADA
```

### 3.2 Dependencia de estados de orden

```text
abierta
  │
  ├── agregar/editar items
  │
  ▼
en cocina
  │
  ├── visible en /cocina
  ├── visible en /ordenes_cocina
  │
  ▼
listo
  │
  ▼
cerrada
  │
  ├── pagos registrados
  ├── inventario descontado
  ├── disponible para cierre
  └── facturable
```

### 3.3 Dependencias externas

```text
Render / GitHub
  │
  ▼
web_app.py como punto de entrada
  │
  ├── SQLite local si no hay DATABASE_URL
  ├── PostgreSQL si hay DATABASE_URL
  ├── /ordenes_cocina -> script_comanda_cocina.py
  └── /facturas_pendientes + /api/tasa -> script_factura.py
```

## 4. Dependencias por Dominio

| Dominio | Depende de | Es usado por | Acoplamiento | Riesgo |
|---|---|---|---|---|
| Menú | DB, constantes, categorías | Órdenes, reportes, inventario/recetas | Alto | Amarillo |
| Órdenes | Menú, DB, usuarios, helpers items | Cocina, cobro, facturas, reportes, cierre | Muy alto | Rojo |
| Cocina | Órdenes, items, usuarios, DB | Scripts locales, operación diaria | Alto | Rojo |
| Caja/cobro | Órdenes, pagos, tasa, inventario, DB | Reportes, cierre, facturas | Muy alto | Rojo |
| Pagos | Tasa, métodos, DB | Cobro, reportes, cierre | Alto | Rojo |
| Facturas | Órdenes, items, tasa, scripts locales | Impresión, cierre operativo | Alto | Rojo |
| Inventario | Menú, recetas, cobro, compras, producción | Stock, costos, reportes | Alto | Amarillo/Rojo |
| Reportes | Órdenes, pagos, tasa, productos | Dashboard, cierre, exportación | Medio/alto | Amarillo |
| Dashboard | Reportes | Administración | Medio | Amarillo |
| Cierre | Órdenes cerradas, pagos, reportes | Administración, histórico | Alto | Rojo |
| Usuarios/Auth | DB, session, roles | Todas las rutas protegidas | Alto | Rojo |
| Configuración | Entorno, tasa, DB | DB, pagos, Render | Alto | Rojo |
| Utils | Ninguno o constantes | Todo el sistema | Bajo | Verde |
| Templates/Static futuro | Rutas, datos renderizados | UI | Medio | Amarillo |

## 5. Funciones Críticas Compartidas

```text
get_connection()
  └── usada por ~61 funciones
      ├── rutas
      ├── reportes
      ├── inventario
      ├── usuarios
      ├── facturas
      └── cierre
```

```text
usuario_rol()
  └── usada por ~13 funciones de permisos
      ├── usuario_es_master()
      ├── usuario_puede_tomar_ordenes()
      ├── usuario_puede_ver_cocina()
      ├── usuario_puede_reportes()
      └── proteger_sistema()
```

```text
a_float()
  └── usada por ~18 funciones
      ├── pagos
      ├── reportes
      ├── inventario
      ├── producción
      └── factura
```

```text
barra_superior()
  └── usada por ~16 pantallas HTML
      ├── usuarios
      ├── menú
      ├── inventario
      ├── compras
      ├── reportes
      └── cierre
```

```text
quitar_prefijo_cantidad_visual()
agrupar_items_comanda()
agrupar_items_factura()
  └── afectan cocina, factura, impresión y visualización
```

## 6. Clasificación por Zonas

### 6.1 Zona Verde - Bajo riesgo

Incluye:

- Constantes.
- Helpers puros.
- Regex de items.
- Fechas.
- Parseo numérico.
- XML/XLSX simple.
- Cálculos puros.

Ejemplos:

- `a_float`
- `ahora_venezuela`
- `parsear_fecha_hora_venezuela`
- `normalizar_indicacion_item`
- `separar_prefijo_cantidad`
- `xml_cell`
- `xml_sheet`
- `calcular_costo_promedio_ponderado`

Por qué está aquí:

- No abre conexiones.
- No hace commit.
- No depende de `request`, `session` o `g`.
- Puede probarse con entradas/salidas.

Riesgo: Bajo.

### 6.2 Zona Amarilla - Riesgo medio

Incluye:

- Reportes.
- Dashboard.
- Exportaciones.
- Agrupadores de cocina/factura.
- Parte de inventario.
- Tasa/configuración.
- HTML no crítico.

Ejemplos:

- `construir_reporte_rango`
- `construir_resumen_cierre`
- `generar_xlsx`
- `agrupar_items_comanda`
- `agrupar_items_factura`
- `obtener_tasa_actual`

Por qué está aquí:

- Usa SQL.
- Puede afectar reportes y cierres.
- Algunos datos se consumen en varias pantallas.
- No siempre modifica datos, pero sí puede cambiar resultados operativos.

Riesgo: Medio.

### 6.3 Zona Roja - Muy alto riesgo

Incluye:

- Orden.
- Agregar productos.
- Cobro.
- Cocina.
- Facturas pendientes.
- Cierre de jornada.
- Init DB.
- Reset.
- Auth/permisos.
- Scripts locales.

Ejemplos:

- `orden`
- `agregar`
- `cobrar`
- `pantalla_cocina`
- `ordenes_cocina`
- `facturas_pendientes`
- `desactivar_factura`
- `cerrar_jornada`
- `init_db`
- `proteger_sistema`
- `_reset_neko_wok_db`
- `reset_neko`

Por qué está aquí:

- Cambia estados.
- Hace commits.
- Afecta impresión.
- Afecta inventario.
- Afecta cierre y reportes.
- Romper una ruta puede detener la operación.

Riesgo: Alto a muy alto.

## 7. Mapa de Impacto

### 7.1 Si modificamos Orden

Puede romperse:

- Vista principal de venta.
- Agregado de productos.
- Combos y promociones.
- Selección de refrescos.
- Envío a cocina.
- Cobro.
- Reimpresión de cocina.
- Facturación.
- Reportes por producto.
- Inventario si cambia cómo se guardan items.

Impacto oculto:

- Cambiar texto del producto puede romper recetas.
- Cambiar `indicacion` puede cambiar lo que cocina y factura muestran.
- Cambiar query params de JS puede romper `/agregar`.

### 7.2 Si modificamos Cobro

Puede romperse:

- Registro de pagos.
- Cálculo Bs/USD.
- Descuento.
- Estado `cerrada`.
- Descuento de inventario.
- Auditoría de emergencia.
- Reportes.
- Cierre de jornada.
- Facturación posterior.

Impacto oculto:

- Si no se marca `inventario_descontado`, puede duplicarse o perderse stock.
- Si se cambia método de pago, reportes/cierre pueden quedar inconsistentes.

### 7.3 Si modificamos Inventario

Puede romperse:

- Compras.
- Producción.
- Recetas.
- Costos promedio.
- Movimientos.
- Descuento automático al cobrar.
- Reportes operativos.

Impacto oculto:

- Recetas dependen de nombres de productos del menú.
- `descontar_inventario_por_orden` depende de `orden_items.producto`.
- Cambios en unidades pueden afectar costos.

### 7.4 Si modificamos Cocina

Puede romperse:

- Pantalla `/cocina`.
- API `/ordenes_cocina`.
- Script local de comandas.
- Reimpresión de cocina.
- Estado `listo`.

Impacto oculto:

- Agrupación de items afecta impresión.
- `reimpresion_token` se limpia desde la API.
- Cambiar JSON puede detener impresión local.

### 7.5 Si modificamos Facturas

Puede romperse:

- `/facturas_pendientes`.
- `script_factura.py`.
- `/api/tasa`.
- `/desactivar_factura/<id>`.
- Reimpresión de factura.

Impacto oculto:

- `facturar` controla cola de impresión.
- `factura_reimpresion_token` diferencia eventos.
- Cambiar formato de items afecta ticket impreso.

### 7.6 Si modificamos Init DB

Puede romperse:

- Arranque local.
- Arranque Render.
- Migraciones runtime.
- SQLite.
- PostgreSQL.
- Usuarios iniciales.
- Menú activo.
- Inventario base.

Impacto oculto:

- Importar la app ejecuta inicialización.
- Cambios de columnas pueden ser irreversibles sin respaldo.

## 8. Dependencias Ocultas

| Dependencia oculta | Descripción | Riesgo |
|---|---|---|
| Nombres de productos -> recetas | Inventario descuenta por `producto_menu`; renombrar productos puede dejar recetas sin match. | Alto |
| `indicacion` -> cocina/factura | La indicación mezcla selección controlada y observación operativa. | Alto |
| Estado de orden -> cocina/cobro/cierre | `abierta`, `en cocina`, `listo`, `cerrada` activan flujos distintos. | Alto |
| `facturar` -> script factura | La cola de impresión depende de columna en `ordenes`. | Alto |
| `reimpresion_token` -> script cocina | La API limpia tokens después de emitir JSON. | Alto |
| `DATABASE_URL` -> motor DB | Cambia comportamiento SQL en producción. | Alto |
| `request.endpoint` -> permisos | Si cambian nombres de endpoints al crear Blueprints, permisos pueden fallar. | Muy alto |
| `web_app.py` -> Render | Render depende del punto de entrada estable. | Muy alto |
| `barra_superior` -> muchas pantallas | Cambios visuales pueden afectar navegación global. | Medio |
| `a_float` -> pagos/reportes/inventario | Parseo numérico afecta cálculos monetarios y stock. | Alto |

## 9. Conclusión del Mapa

La dependencia central del sistema es `web_app.py`, pero los dominios ya están claros. El riesgo no está solo en el tamaño del archivo, sino en los cruces entre dominios:

- Orden alimenta cocina, cobro, facturas, reportes e inventario.
- Cobro cierra la venta y descuenta inventario.
- Cocina y facturas exponen contratos externos a scripts locales.
- Init DB afecta arranque, tablas, columnas y semillas.
- Auth controla todo mediante endpoints.

La modularización debe comenzar por zonas verdes, continuar por zonas amarillas y dejar rutas rojas para el final.

