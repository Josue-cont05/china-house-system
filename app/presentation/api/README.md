# Presentation API

## Responsabilidad

Contendra endpoints HTTP que devuelven JSON o datos consumidos por clientes externos, como scripts locales de impresion.

## Que tipo de archivos viviran aqui

- APIs de cocina.
- APIs de facturas.
- API de tasa.
- Serializadores de respuesta.

## Que NO debe vivir aqui

- Cambios de contrato JSON sin plan.
- SQL directo cuando existan repositorios.
- Reglas de negocio de cocina o factura.

## Quien puede depender de esta carpeta

- Clientes externos consumen sus rutas, pero ninguna capa interna debe depender de ella.

## De que puede depender

- `application`
- `shared` para formateo.

## Ejemplos futuros

- `cocina_api.py`
- `facturas_api.py`
- `tasa_api.py`

## Reglas de diseno

- Proteger `/ordenes_cocina`.
- Proteger `/facturas_pendientes`.
- Proteger `/api/tasa`.
- Proteger `/desactivar_factura/<id>`.
