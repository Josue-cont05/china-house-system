# Shared

## Responsabilidad

Contendra componentes reutilizables organizados por responsabilidad. No es un lugar para un `utils.py` gigante.

Areas iniciales:

- `datetime`
- `money`
- `text`
- `validation`
- `excel`
- `xml`

## Que tipo de archivos viviran aqui

- Componentes pequenos.
- Funciones puras.
- Formateadores.
- Validadores.
- Generadores tecnicos reutilizables.

## Que NO debe vivir aqui

- Reglas complejas de negocio.
- Rutas.
- SQL.
- Flask globals.
- Acceso a base de datos.

## Quien puede depender de esta capa

- `presentation`
- `application`
- `domain`, solo cuando el helper sea puro y estable.
- `infrastructure`

## De que puede depender

- Preferiblemente de nadie dentro de `app`.
- Librerias estandar o dependencias claramente justificadas.

## Ejemplos futuros

- `money/formatos.py`
- `datetime/venezuela.py`
- `text/normalizacion.py`
- `excel/xlsx.py`

## Reglas de diseno

- Organizar por responsabilidad.
- Evitar nombres genericos.
- Mantener funciones pequenas y testeables.
