# Contratos API Críticos

Los scripts locales dependen de estas rutas. No deben cambiarse sin actualizar y probar dichos scripts.

## `/ordenes_cocina`

Consumida por:

- `scripts_locales/script_comanda_cocina.py`

Uso:

- Devuelve órdenes listas para imprimir en cocina.
- Incluye identificador de evento para evitar duplicados.

No cambiar sin revisar:

- Campos JSON.
- Ordenamiento.
- Semántica de reimpresión.

## `/facturas_pendientes`

Consumida por:

- `scripts_locales/script_factura.py`

Uso:

- Devuelve facturas marcadas como pendientes.
- Incluye items, total y evento de impresión.

No cambiar sin probar impresión.

## `/api/tasa`

Consumida por:

- `scripts_locales/script_factura.py`

Uso:

- Devuelve tasa actual en JSON.

Contrato esperado:

- `ok`
- `tasa`

## `/desactivar_factura/<id>`

Consumida por:

- `scripts_locales/script_factura.py`

Uso:

- Marca una factura como no pendiente después de impresión.

## `/activar_factura/<id>`

Uso:

- Marca una orden para facturar.

## `/reimprimir_factura/<id>`

Uso:

- Reactiva factura con token de reimpresión.

## Regla general

Los scripts locales son clientes externos. Cambiar estas rutas equivale a cambiar una API pública.

