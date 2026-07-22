# Shared Excel

## Responsabilidad

Contendra generacion o apoyo tecnico para archivos Excel cuando sea reutilizable.

## Que tipo de archivos viviran aqui

- Helpers XLSX.
- Serializacion tabular.
- Formatos reutilizables de exportacion.

## Que NO debe vivir aqui

- Queries de reportes.
- Reglas de cierre.
- Rutas de descarga.

## Quien puede depender de esta carpeta

- `application`
- `presentation`

## De que puede depender

- Librerias estandar o dependencias de generacion de archivos aprobadas.

## Ejemplos futuros

- `xlsx.py`
- `sheets.py`

## Reglas de diseno

- Recibir datos ya preparados.
- No consultar base de datos.
- No conocer rutas Flask.
