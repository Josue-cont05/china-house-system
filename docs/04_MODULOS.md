# Módulos Futuros

## auth

Responsable de login, logout y sesión.

No debe manejar reportes, menú ni cobro.

## usuarios

Responsable de roles, permisos y administración de usuarios.

No debe renderizar pantallas de POS.

## menu

Responsable de categorías, productos, combos y promociones.

No debe cobrar ni modificar inventario directamente.

## ordenes

Responsable de crear, editar y consultar órdenes.

No debe imprimir ni cerrar caja.

## cocina

Responsable de comandas, estado `en cocina`, estado `listo` y reimpresión de cocina.

No debe calcular pagos.

## caja/cobro

Responsable de totales, descuentos, cobro y cierre de orden.

No debe definir menú.

## pagos

Responsable de métodos, conversiones y registros de pago.

No debe renderizar HTML de caja.

## facturas

Responsable de facturas pendientes, activación, reimpresión y desactivación.

No debe cambiar reglas de cocina.

## inventario

Responsable de stock, recetas, compras, producción y movimientos.

No debe decidir rutas ni permisos de interfaz.

## reportes

Responsable de consultas, rangos, exportaciones y resumen histórico.

No debe alterar órdenes.

## dashboard

Responsable de métricas visuales.

No debe contener SQL complejo si puede delegarlo a reportes.

## configuracion

Responsable de tasa, variables y parámetros del negocio.

No debe manejar órdenes.

## database

Responsable de conexión y compatibilidad SQLite/PostgreSQL.

No debe conocer HTML.

## utils

Responsable de funciones puras.

No debe usar `request`, `session`, `g` ni abrir conexiones.

## templates

Responsable de HTML.

No debe contener lógica de negocio compleja.

## static

Responsable de CSS, JS e imágenes.

No debe contener secretos ni reglas críticas de negocio.

