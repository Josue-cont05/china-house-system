# Shared Validation

## Responsabilidad

Contendra validaciones reutilizables y pequenas que no sean reglas centrales de negocio.

## Que tipo de archivos viviran aqui

- Validaciones de formato.
- Validaciones de campos simples.
- Helpers de entrada segura.

## Que NO debe vivir aqui

- Reglas completas de orden, cobro o cierre.
- Permisos de usuario.
- Acceso a base de datos.

## Quien puede depender de esta carpeta

- `presentation`
- `application`
- `domain` cuando la validacion sea pura y estable.

## De que puede depender

- Librerias estandar.

## Ejemplos futuros

- `campos.py`
- `numeros.py`

## Reglas de diseno

- Diferenciar validacion tecnica de regla de negocio.
- No consultar base de datos.
- Devolver errores claros.
