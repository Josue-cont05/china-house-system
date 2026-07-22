# Reglas de Negocio

## Descripción, indicación y observación

- **Descripción:** detalle estructurado que el sistema genera por selección del cliente, por ejemplo sabor, arroz o favorito.
- **Indicación:** dato operativo guardado en el item para cocina/factura.
- **Observación del cliente:** nota libre escrita por el usuario, por ejemplo "sin cebollín".

Regla futura:

- Las selecciones controladas deben salir como descripción.
- Las notas libres deben salir como observación.
- No mezclar ambas si se rediseña el modelo.

## Combos personales

### Neko Combo 1

- Incluye arroz fijo.
- Incluye bebida fija.
- El cliente debe escoger un favorito:
  - `Pollo Agridulce`
  - `Chop Suey de Pollo`

### Neko Combo 2

- Arroz fijo.
- Bebida fija.
- Incluye favoritos fijos.
- No requiere selección de favorito.

### Neko Combo 3

- Arroz fijo.
- Bebida fija.
- Incluye favoritos fijos.
- No requiere selección de favorito.

## Promociones

Promociones actuales:

- `Wok para Dos`
- `Familiar`
- `Mega Familiar`

Cada promoción define:

- Cantidad de arroces.
- Cantidad de refrescos.
- Tipo de refresco.

## Arroces

Opciones controladas:

- `Pollo + Cerdo`
- `Pollo + Camarón`
- `Triple`

## Refrescos

Los refrescos requieren sabor. El sabor se normaliza contra una lista de opciones válidas.

## Lumpia agrandada

Algunas promociones permiten agregar una lumpia extra como item separado:

- `Promo extra: Ración de Lumpias`

## Flujo orden -> cocina -> cobro

1. Orden se crea en estado `abierta`.
2. Se agregan items.
3. Se envía a cocina y pasa a `en cocina`.
4. Cocina puede marcar como `listo`.
5. Caja cobra y pasa a `cerrada`.
6. Cobro registra pagos y descuenta inventario.
7. Factura se activa si corresponde.

## Regla para cambios futuros

No cambiar nombres de productos, promociones o detalles sin revisar:

- Cocina.
- Factura.
- Inventario.
- Reportes.
- Scripts locales.

