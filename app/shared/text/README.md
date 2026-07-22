# Shared Text

## Responsabilidad

Contendra normalizacion y formateo de texto reutilizable.

## Que tipo de archivos viviran aqui

- Limpieza de strings.
- Normalizacion de acentos si aplica.
- Separacion de prefijos visuales.
- Formateadores de etiquetas simples.

## Que NO debe vivir aqui

- Reglas de promociones.
- Reglas de combos.
- SQL.
- HTML grande.

## Quien puede depender de esta carpeta

- `presentation`
- `application`
- `domain` si la funcion es pura.

## De que puede depender

- Librerias estandar.

## Ejemplos futuros

- `normalizacion.py`
- `items.py`

## Reglas de diseno

- No esconder reglas de negocio dentro de nombres genericos.
- Mantener funciones deterministicas.
