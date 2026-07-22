# Arquitectura

## Arquitectura actual

El sistema es una aplicación Flask monolítica. `web_app.py` contiene:

- Configuración Flask.
- Configuración de base de datos.
- Rutas.
- SQL.
- HTML/CSS/JS embebido.
- Lógica de negocio.
- Permisos.
- Inventario, caja, cocina, facturación, reportes y cierre.

## Riesgos de `web_app.py`

- Alto acoplamiento entre UI, rutas, SQL y negocio.
- Dificultad para probar partes aisladas.
- Riesgo de romper flujos críticos al mover código.
- Inicialización de base de datos en runtime.
- Contratos externos mezclados con vistas HTML.

## Arquitectura modular futura

Arquitectura preferida desde ADR-002:

```text
app/
  application/
  domain/
  infrastructure/
  presentation/
  shared/
```

Responsabilidades:

- `application`: casos de uso del negocio. Coordina entidades, repositorios y reglas para operaciones como crear orden, agregar producto, cobrar, cerrar jornada o generar reportes.
- `domain`: entidades y reglas puras del negocio. Aquí viven conceptos como Orden, Producto, Combo, Promoción, Pago, Usuario e Inventario, sin depender de Flask ni SQL.
- `infrastructure`: base de datos, repositorios, adaptadores, Render y configuración. Encapsula SQLite, PostgreSQL, `DATABASE_URL`, migraciones y detalles técnicos.
- `presentation`: Flask, rutas, Blueprints, templates, static, APIs HTTP y pantallas. Recibe requests y delega en casos de uso.
- `shared`: utilidades reutilizables organizadas por responsabilidad, como fechas, dinero, texto, validaciones, formateadores, Excel y XML.

Nota histórica:

La estructura anterior `routes/services/database/utils` queda como referencia histórica del primer plan de modularización. La arquitectura preferida desde ADR-002 es Clean Architecture adaptada: `application/domain/infrastructure/presentation/shared`.

## Mantener entrada Render

Mientras Render use `web_app.py`, este archivo debe seguir existiendo y exportando `app`.

Estrategia segura:

1. Extraer helpers.
2. Importarlos desde `web_app.py`.
3. Mantener rutas intactas.
4. Solo al final convertir `web_app.py` en entrada liviana.
