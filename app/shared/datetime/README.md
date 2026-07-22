# Shared Datetime

## Responsabilidad

Contendra componentes reutilizables para fechas, horas y zona horaria.

## Que tipo de archivos viviran aqui

- Fecha/hora de Venezuela.
- Parseo de fechas.
- Formatos de jornada.

## Que NO debe vivir aqui

- Consultas SQL.
- Reglas de cierre con efectos secundarios.
- Rutas Flask.

## Quien puede depender de esta carpeta

- `application`
- `presentation`
- `infrastructure`
- `domain` si el uso es puro.

## De que puede depender

- Librerias estandar de fecha/hora.

## Ejemplos futuros

- `venezuela.py`
- `parseo.py`

## Reglas de diseno

- Mantener funciones puras.
- No leer request ni session.
- Documentar zona horaria usada.
