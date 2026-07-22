# Pruebas Manuales

Usar este checklist después de cambios relevantes.

## Flujo base

- Login.
- Crear orden.
- Agregar producto normal.
- Agregar refresco con sabor.
- Agregar Combo 1.
- Confirmar que Combo 1 obliga a escoger `Pollo Agridulce` o `Chop Suey`.
- Agregar promoción.
- Confirmar selección de arroz.
- Confirmar selección de refresco.
- Confirmar lumpia agrandada si aplica.
- Enviar a cocina.
- Revisar `/ordenes_cocina`.
- Abrir `/cocina`.
- Marcar listo.
- Cobrar.
- Confirmar pagos.
- Activar factura.
- Revisar `/facturas_pendientes`.
- Desactivar factura si se imprime.
- Revisar cierre.
- Revisar reportes.

## Inventario

Si el cambio toca inventario:

- Revisar recetas.
- Registrar compra.
- Registrar producción.
- Cobrar orden con receta.
- Confirmar movimiento de inventario.

## Base de datos

- Probar SQLite local.
- Probar PostgreSQL si el cambio toca SQL.

## Scripts locales

Si cambia cocina o factura:

- Probar `script_comanda_cocina.py`.
- Probar `script_factura.py`.
- Confirmar que no se duplican impresiones.

