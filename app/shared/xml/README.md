# Shared XML

## Responsabilidad

Contendra helpers reutilizables para generar XML tecnico.

## Que tipo de archivos viviran aqui

- Escape de celdas XML.
- Generacion de fragmentos XML.
- Utilidades para exportacion.

## Que NO debe vivir aqui

- Reportes completos con SQL.
- Reglas de negocio.
- Rutas Flask.

## Quien puede depender de esta carpeta

- `shared/excel`
- `application`
- `presentation`

## De que puede depender

- Librerias estandar de XML o texto.

## Ejemplos futuros

- `cells.py`
- `sheet_xml.py`

## Reglas de diseno

- Mantener salida escapada y segura.
- No mezclar generacion XML con consultas.
- Probar caracteres especiales.
