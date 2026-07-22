# Shared Money

## Responsabilidad

Contendra componentes reutilizables para montos, conversiones simples y formato monetario.

## Que tipo de archivos viviran aqui

- Formateo USD/Bs.
- Normalizacion de montos.
- Conversiones matematicas simples.

## Que NO debe vivir aqui

- Reglas completas de cobro.
- Registro de pagos.
- SQL.
- Estado de orden.

## Quien puede depender de esta carpeta

- `application`
- `presentation`
- `domain` si se usa como valor puro.

## De que puede depender

- Librerias estandar.

## Ejemplos futuros

- `formatos.py`
- `conversion.py`

## Reglas de diseno

- No decidir metodos de pago permitidos si eso pertenece al dominio.
- Evitar redondeos ocultos.
- Mantener entradas y salidas claras.
