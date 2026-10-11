"""
menu_admin_views.py (presentacion)

Pantallas del modulo Menu como centro de administracion:
- /menu                    -> Productos (buscador, filtros, tarjetas con imagen)
- /menu/modificadores      -> Modificadores (grupos + opciones, en lenguaje de negocio)
- /editar_producto/<id>    -> Datos, imagen y "Opciones del producto"

Solo HTML: las rutas (web_app.py) resuelven los datos y aplican la
logica; los nombres de endpoint no cambian, asi proteger_sistema() sigue
protegiendolas igual (solo master). Usa exclusivamente el design system
(app.presentation.web.design_system) + un layout minimo por pantalla.
Todo texto que viene de la BD pasa por html.escape.
"""

import html as html_lib

from app.domain.sales.modifiers import MAXIMO_SIN_LIMITE, describir_reglas_grupo
from app.presentation.web.order_detail_view import estilo_categoria_pos


def _e(valor):
    return html_lib.escape("" if valor is None else str(valor))


def _attr(valor):
    return html_lib.escape("" if valor is None else str(valor), quote=True)


def tabs_menu(activo):
    pestanas = (
        ("productos", "/menu", "🍽️ Productos"),
        ("modificadores", "/menu/modificadores", "🧩 Modificadores"),
    )
    items = ""
    for clave, url, texto in pestanas:
        if clave == activo:
            items += f'<a class="ds-tab activo" href="{url}" aria-current="page">{texto}</a>'
        else:
            items += f'<a class="ds-tab" href="{url}">{texto}</a>'
    return f'<nav class="ds-tabs menu-tabs" aria-label="Secciones del menú">{items}</nav>'


CSS_MENU = """
body { margin: 0; }
.menu-admin { max-width: 1180px; }
.menu-admin .ds-page-header { margin-bottom: 4px; }
.menu-guia { display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center; margin: 0 0 16px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--bg-panel); color: var(--text-secondary); font-size: 14px; }
.menu-guia b { color: var(--text-primary); }
.menu-guia ol { margin: 0; padding-left: 20px; display: flex; flex-wrap: wrap; gap: 4px 22px; }
details.menu-desplegable { margin: 0 0 16px; }
details.menu-desplegable > summary { list-style: none; cursor: pointer; display: inline-flex; }
details.menu-desplegable > summary::-webkit-details-marker { display: none; }
details.menu-desplegable[open] > summary { margin-bottom: 12px; }
.menu-form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; align-items: end; }
.menu-form-grid .ds-field { margin: 0; }
.menu-filtros { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) auto; gap: 12px; align-items: end; margin-bottom: 16px; }
.menu-filtros .ds-field { margin: 0; }
.menu-filtros input, .menu-filtros select, .menu-form-grid input, .menu-form-grid select { width: 100%; margin: 0; }
.menu-contador { color: var(--text-muted); font-size: 13px; font-weight: 700; white-space: nowrap; padding-bottom: 12px; }
.menu-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
.menu-producto { display: flex; flex-direction: column; padding: 0; overflow: hidden; }
.menu-producto.inactivo { opacity: 0.62; }
.menu-producto-media { position: relative; aspect-ratio: 16 / 10; display: flex; align-items: center; justify-content: center; background: var(--cat-tint, var(--bg-hover)); border-bottom: 2px solid var(--cat, var(--border)); overflow: hidden; }
.menu-producto-media img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.menu-placeholder { font-size: 38px; }
.menu-producto-body { display: flex; flex-direction: column; gap: 8px; padding: 12px; flex: 1; }
.menu-producto-body h3 { margin: 0; font-size: 16px; line-height: 1.25; }
.menu-producto-precio { font-size: 18px; font-weight: 900; }
.menu-badges { display: flex; flex-wrap: wrap; gap: 6px; }
.menu-acciones { display: flex; gap: 8px; margin-top: auto; }
.menu-acciones form { margin: 0; flex: 1; display: flex; }
.menu-acciones .ds-btn { flex: 1; white-space: nowrap; }

/* Modificadores */
.grupo-card { margin-bottom: 14px; scroll-margin-top: 90px; }
.grupo-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.grupo-head h2 { margin: 0; font-size: 20px; }
.grupo-resumen { margin: 4px 0 0; color: var(--text-secondary); font-size: 14px; }
.grupo-usado { margin: 4px 0 0; color: var(--text-muted); font-size: 13px; }
.grupo-acciones-head { display: flex; gap: 8px; flex-wrap: wrap; }
.grupo-acciones-head form { margin: 0; }
.opcion-lista { margin: 14px 0 12px; border: 1px solid var(--border); border-radius: var(--radius-md); overflow: hidden; }
.opcion-fila { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px 12px; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--border); background: var(--bg-card); }
.opcion-fila:last-child { border-bottom: none; }
.opcion-fila.inactiva { opacity: 0.6; }
.opcion-nombre { font-weight: 800; font-size: 15px; }
.opcion-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; align-items: center; color: var(--text-muted); font-size: 12px; }
.opcion-acciones { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.opcion-acciones form { margin: 0; }
.opcion-editar { grid-column: 1 / -1; }
.opcion-editar > summary { display: none; }
.opcion-editar[open] { padding-top: 8px; }
.grupo-pie { display: flex; gap: 8px; flex-wrap: wrap; }
.grupo-pie details { flex: 1 1 100%; }
.grupo-pie details > summary { display: inline-flex; }
.grupo-form .ds-segmented { --ds-segmentos: 2; }
.grupo-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.grupo-form input[type=text], .grupo-form input[type=number] { width: 100%; margin: 0; }
details.grupo-avanzado { margin: 4px 0 12px; border: 1px dashed var(--border); border-radius: var(--radius-md); padding: 10px 12px; }
details.grupo-avanzado > summary { cursor: pointer; font-weight: 800; color: var(--text-secondary); }
.grupo-avanzado-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 10px; }
.grupo-avanzado-nota { color: var(--text-muted); font-size: 13px; margin: 8px 0 0; }
input[readonly] { opacity: 0.6; }

/* Editar producto */
.editar-layout { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 16px; align-items: start; }
.editar-layout .ds-panel { margin-bottom: 16px; }
.editar-layout h2 { margin: 0 0 4px; font-size: 18px; }
.editar-ayuda { margin: 0 0 14px; color: var(--text-secondary); font-size: 14px; }
.editar-layout input[type=text], .editar-layout input[type=number], .editar-layout select { width: 100%; margin: 0; }
.imagen-preview { position: relative; aspect-ratio: 4 / 3; border-radius: var(--radius-md); overflow: hidden; border: 1px solid var(--border); background: var(--cat-tint, var(--bg-card)); display: flex; align-items: center; justify-content: center; margin-bottom: 12px; }
.imagen-preview img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.imagen-preview .menu-placeholder { font-size: 56px; }
.imagen-archivo { display: block; width: 100%; padding: 10px; border: 1.5px dashed var(--border-strong); border-radius: var(--radius-md); background: var(--bg-card); color: var(--text-secondary); margin: 0 0 10px; }
.imagen-info { color: var(--text-muted); font-size: 13px; margin: 8px 0 0; }
.grupos-producto { display: grid; gap: 8px; }
.grupo-check { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px; align-items: start; padding: 12px; border: 1.5px solid var(--border); border-radius: var(--radius-md); background: var(--bg-card); cursor: pointer; }
.grupo-check input { width: 22px; height: 22px; min-height: 0; margin: 2px 0 0; accent-color: var(--accent-primary); }
.grupo-check:has(input:checked) { border-color: var(--accent-primary); background: var(--accent-primary-soft); }
.grupo-check-nombre { font-weight: 800; }
.grupo-check-detalle { color: var(--text-secondary); font-size: 13px; margin-top: 2px; }

@media (max-width: 900px) {
    .editar-layout { grid-template-columns: minmax(0, 1fr); }
    .menu-filtros { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    .menu-filtros .menu-buscar { grid-column: 1 / -1; }
    .menu-contador { grid-column: 1 / -1; padding: 0; }
}
@media (max-width: 640px) {
    .menu-form-grid, .grupo-form-grid { grid-template-columns: minmax(0, 1fr); }
    .menu-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .menu-producto-body { padding: 10px; }
    .menu-acciones { flex-direction: column; }
    .opcion-fila { grid-template-columns: minmax(0, 1fr); }
    .opcion-acciones { justify-content: flex-start; }
    .grupo-avanzado-grid { grid-template-columns: minmax(0, 1fr); }
}
"""


def _pagina(titulo, cuerpo, *, estilos_base, barra_superior, js=""):
    return f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_e(titulo)} · Neko Wok POS</title>
    <style>{estilos_base()}{CSS_MENU}</style>
    </head>
    <body>
    {barra_superior()}
    {cuerpo}
    {f"<script>{js}</script>" if js else ""}
    </body>
    </html>
    """


# ----------------------------------------------------------------------
# Productos
# ----------------------------------------------------------------------
JS_PRODUCTOS = """
(function() {
    var buscar = document.getElementById("menuBuscar");
    var categoria = document.getElementById("menuCategoria");
    var estado = document.getElementById("menuEstado");
    var contador = document.getElementById("menuContador");
    var vacio = document.getElementById("menuSinResultados");
    var tarjetas = Array.prototype.slice.call(document.querySelectorAll(".menu-producto"));
    function normalizar(t) { return (t || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase().trim(); }
    tarjetas.forEach(function(t) { t._texto = normalizar(t.dataset.nombre); });
    function filtrar() {
        var q = normalizar(buscar.value), cat = categoria.value, est = estado.value, visibles = 0;
        tarjetas.forEach(function(t) {
            var ok = (!q || t._texto.indexOf(q) !== -1)
                && (!cat || t.dataset.categoria === cat)
                && (est === "todos" || t.dataset.estado === est);
            t.hidden = !ok;
            if (ok) visibles += 1;
        });
        contador.textContent = visibles + (visibles === 1 ? " producto" : " productos");
        vacio.hidden = visibles !== 0;
    }
    [buscar, categoria, estado].forEach(function(el) { el.addEventListener("input", filtrar); el.addEventListener("change", filtrar); });
    filtrar();
})();
"""


def _media_producto(producto_id, nombre, categoria, imagen_src):
    color, icono = estilo_categoria_pos(categoria or "")
    img = ""
    if imagen_src:
        img = f'<img src="{_attr(imagen_src)}" alt="" loading="lazy" decoding="async" onerror="this.remove()">'
    return (
        f'<div class="menu-producto-media" style="--cat:{color};--cat-tint:{color}22;">'
        f'<span class="menu-placeholder" aria-hidden="true">{icono}</span>{img}</div>'
    )


def render_menu_productos(*, productos, categorias, imagenes, grupos_por_producto, estilos_base, barra_superior):
    """productos: (id, nombre, precio, categoria, activo, imagen_url).
    imagenes: {producto_id: url a mostrar} (BD -> imagen_url)."""
    opciones_categoria = "".join(
        f'<option value="{_attr(c[1])}">{_e(c[1])}</option>' for c in categorias
    )
    opciones_crear = "".join(f'<option value="{c[0]}">{_e(c[1])}</option>' for c in categorias)

    tarjetas = ""
    for producto_id, nombre, precio, categoria, activo, _imagen_url in productos:
        categoria_txt = categoria or "Sin categoría"
        n_grupos = grupos_por_producto.get(producto_id, 0)
        estado_badge = (
            '<span class="ds-badge ds-badge-success">Activo</span>'
            if activo else '<span class="ds-badge ds-badge-neutral">Inactivo</span>'
        )
        grupos_badge = (
            f'<span class="ds-badge ds-badge-info">🧩 {n_grupos} {"grupo" if n_grupos == 1 else "grupos"}</span>'
            if n_grupos else ""
        )
        boton_estado = (
            f'<form method="post" action="/menu/producto/{producto_id}/activo">'
            f'<input type="hidden" name="activo" value="{0 if activo else 1}">'
            f'<button type="submit" class="ds-btn {"ds-btn-ghost" if not activo else "ds-btn-secondary"} ds-btn-sm">'
            f'{"Activar" if not activo else "Desactivar"}</button></form>'
        )
        tarjetas += f"""
        <article class="menu-producto ds-card{'' if activo else ' inactivo'}" data-nombre="{_attr(nombre)}" data-categoria="{_attr(categoria_txt)}" data-estado="{'activo' if activo else 'inactivo'}" data-producto-id="{producto_id}">
            {_media_producto(producto_id, nombre, categoria_txt, imagenes.get(producto_id))}
            <div class="menu-producto-body">
                <h3>{_e(nombre)}</h3>
                <div class="menu-producto-precio">${float(precio or 0):.2f}</div>
                <div class="menu-badges">
                    <span class="ds-badge ds-badge-neutral">{_e(categoria_txt)}</span>
                    {estado_badge}
                    {grupos_badge}
                </div>
                <div class="menu-acciones">
                    <a class="ds-btn ds-btn-primary ds-btn-sm" href="/editar_producto/{producto_id}">✏️ Editar</a>
                    {boton_estado}
                </div>
            </div>
        </article>"""

    cuerpo = f"""
    <main class="ds-page menu-admin">
        <div class="ds-page-header">
            <div>
                <h1 class="ds-page-title">🍜 Menú</h1>
                <p class="ds-page-subtitle">Productos, opciones e imágenes que ve el POS.</p>
            </div>
        </div>
        {tabs_menu("productos")}
        <details class="menu-desplegable" {'open' if not productos else ''}>
            <summary class="ds-btn ds-btn-primary">➕ Agregar producto</summary>
            <form method="post" action="/menu" class="ds-panel menu-form-grid">
                <label class="ds-field"><span class="ds-label">Nombre</span><input name="nombre" type="text" placeholder="Ej. Jugo Natural" required></label>
                <label class="ds-field"><span class="ds-label">Precio USD</span><input name="precio" type="number" step="0.01" min="0" placeholder="0.00" required></label>
                <label class="ds-field"><span class="ds-label">Categoría</span><select name="categoria">{opciones_crear}</select></label>
                <button class="ds-btn ds-btn-primary">Guardar producto</button>
            </form>
        </details>
        <div class="ds-panel menu-filtros">
            <label class="ds-field menu-buscar"><span class="ds-label">Buscar</span><input id="menuBuscar" type="search" placeholder="Buscar producto..." autocomplete="off"></label>
            <label class="ds-field"><span class="ds-label">Categoría</span><select id="menuCategoria"><option value="">Todas</option>{opciones_categoria}<option value="Sin categoría">Sin categoría</option></select></label>
            <label class="ds-field"><span class="ds-label">Estado</span><select id="menuEstado"><option value="activo">Activos</option><option value="inactivo">Inactivos</option><option value="todos">Todos</option></select></label>
            <div class="menu-contador" id="menuContador" aria-live="polite"></div>
        </div>
        <div class="menu-grid" id="menuGrid">{tarjetas}
        </div>
        <div class="ds-empty" id="menuSinResultados" hidden>No hay productos con esos filtros.</div>
    </main>
    """
    return _pagina("Menú", cuerpo, estilos_base=estilos_base, barra_superior=barra_superior, js=JS_PRODUCTOS)


# ----------------------------------------------------------------------
# Modificadores
# ----------------------------------------------------------------------
JS_MODIFICADORES = """
(function() {
    document.querySelectorAll("form.grupo-form").forEach(function(form) {
        var minimo = form.querySelector('input[name="minimo"]');
        var maximo = form.querySelector('input[name="maximo"]');
        var nota = form.querySelector(".grupo-avanzado-nota");
        function valor(nombre) {
            var marcado = form.querySelector('input[name="' + nombre + '"]:checked');
            return marcado ? marcado.value : "";
        }
        function sincronizar() {
            var obligatorio = valor("obligatorio") === "1";
            if (valor("tipo_seleccion") === "unica") {
                minimo.value = obligatorio ? 1 : 0;
                maximo.value = 1;
                minimo.readOnly = maximo.readOnly = true;
                nota.textContent = "Con “Elegir una opción”, el mínimo y el máximo se ajustan solos.";
            } else {
                maximo.readOnly = false;
                if (obligatorio) {
                    minimo.readOnly = false;
                    if ((parseInt(minimo.value, 10) || 0) < 1) minimo.value = 1;
                } else {
                    minimo.value = 0;
                    minimo.readOnly = true;
                }
                if ((parseInt(maximo.value, 10) || 0) <= 1) maximo.value = %(sin_limite)d;
                nota.textContent = obligatorio
                    ? "Máximo %(sin_limite)d = sin límite práctico."
                    : "Grupo opcional: no exige mínimo. Máximo %(sin_limite)d = sin límite práctico.";
            }
        }
        form.addEventListener("change", sincronizar);
        sincronizar();
    });
})();
""" % {"sin_limite": MAXIMO_SIN_LIMITE}


def _form_grupo(*, accion, boton, grupo=None, ident="nuevo"):
    nombre = grupo["nombre"] if grupo else ""
    multiple = bool(grupo["seleccion_multiple"]) if grupo else False
    obligatorio = bool(grupo["obligatorio"]) if grupo else True
    minimo = grupo["minimo"] if grupo else 1
    maximo = grupo["maximo"] if grupo else 1
    orden = grupo["orden"] if grupo else 0
    return f"""
    <form method="post" action="{accion}" class="grupo-form">
        <label class="ds-field"><span class="ds-label">Nombre del grupo</span>
            <input name="nombre" type="text" value="{_attr(nombre)}" placeholder="Ej. Sabor, Nivel de azúcar" required></label>
        <div class="grupo-form-grid">
            <div class="ds-field">
                <div class="ds-label" id="tipo-{ident}">Tipo de selección</div>
                <div class="ds-segmented" role="radiogroup" aria-labelledby="tipo-{ident}">
                    <label class="ds-segmented-option"><input type="radio" name="tipo_seleccion" value="unica" {'' if multiple else 'checked'}><span>Elegir una opción</span></label>
                    <label class="ds-segmented-option"><input type="radio" name="tipo_seleccion" value="multiple" {'checked' if multiple else ''}><span>Permitir varias</span></label>
                </div>
            </div>
            <div class="ds-field">
                <div class="ds-label" id="obl-{ident}">¿Obligatorio?</div>
                <div class="ds-segmented" role="radiogroup" aria-labelledby="obl-{ident}">
                    <label class="ds-segmented-option"><input type="radio" name="obligatorio" value="1" {'checked' if obligatorio else ''}><span>Sí</span></label>
                    <label class="ds-segmented-option"><input type="radio" name="obligatorio" value="0" {'' if obligatorio else 'checked'}><span>No</span></label>
                </div>
            </div>
        </div>
        <details class="grupo-avanzado">
            <summary>Opciones avanzadas</summary>
            <div class="grupo-avanzado-grid">
                <label class="ds-field"><span class="ds-label">Mínimo</span><input name="minimo" type="number" min="0" value="{minimo}"></label>
                <label class="ds-field"><span class="ds-label">Máximo</span><input name="maximo" type="number" min="1" value="{maximo}"></label>
                <label class="ds-field"><span class="ds-label">Orden</span><input name="orden" type="number" value="{orden}"></label>
            </div>
            <p class="grupo-avanzado-nota"></p>
        </details>
        <button class="ds-btn ds-btn-primary">{boton}</button>
    </form>
    """


def render_menu_modificadores(*, grupos, productos_por_grupo, estilos_base, barra_superior):
    """grupos: lista de dicts {id, nombre, activo, obligatorio, seleccion_multiple,
    minimo, maximo, orden, opciones: [(id, nombre, activa, disponible, precio, orden)]}."""
    tarjetas = ""
    for g in grupos:
        opciones_html = ""
        for opcion_id, o_nombre, o_activa, o_disponible, o_precio, o_orden in g["opciones"]:
            precio = float(o_precio or 0)
            precio_html = f'<span class="ds-badge ds-badge-info">+${precio:.2f}</span>' if precio else ""
            disponible_badge = (
                '<span class="ds-badge ds-badge-success">Disponible</span>'
                if o_disponible else '<span class="ds-badge ds-badge-danger">Agotada</span>'
            )
            activa_badge = "" if o_activa else '<span class="ds-badge ds-badge-neutral">Inactiva</span>'
            opciones_html += f"""
            <div class="opcion-fila{'' if o_activa else ' inactiva'}" id="opcion-{opcion_id}">
                <div>
                    <div class="opcion-nombre">{_e(o_nombre)}</div>
                    <div class="opcion-meta">{disponible_badge}{activa_badge}{precio_html}</div>
                </div>
                <div class="opcion-acciones">
                    <button type="button" class="ds-btn ds-btn-secondary ds-btn-sm" onclick="var d=document.getElementById('editar-opcion-{opcion_id}'); d.open=!d.open;">Editar</button>
                    <form method="post" action="/menu/modificadores/opciones/{opcion_id}/disponible">
                        <input type="hidden" name="disponible" value="{0 if o_disponible else 1}">
                        <button class="ds-btn {'ds-btn-danger' if o_disponible else 'ds-btn-ghost'} ds-btn-sm">{'Marcar agotada' if o_disponible else 'Marcar disponible'}</button>
                    </form>
                    <form method="post" action="/menu/modificadores/opciones/{opcion_id}/activa">
                        <input type="hidden" name="activa" value="{0 if o_activa else 1}">
                        <button class="ds-btn ds-btn-secondary ds-btn-sm">{'Desactivar' if o_activa else 'Activar'}</button>
                    </form>
                </div>
                <details class="opcion-editar" id="editar-opcion-{opcion_id}">
                    <summary>Editar</summary>
                    <form method="post" action="/menu/modificadores/opciones/{opcion_id}/editar" class="grupo-form-grid">
                        <label class="ds-field"><span class="ds-label">Nombre</span><input name="nombre" type="text" value="{_attr(o_nombre)}" required></label>
                        <label class="ds-field"><span class="ds-label">Precio adicional USD</span><input name="precio_adicional" type="number" step="0.01" min="0" value="{precio:.2f}"></label>
                        <label class="ds-field"><span class="ds-label">Orden</span><input name="orden" type="number" value="{o_orden}"></label>
                        <div class="ds-field" style="display:flex;align-items:end;"><button class="ds-btn ds-btn-primary">Guardar opción</button></div>
                    </form>
                </details>
            </div>"""
        if not opciones_html:
            opciones_html = '<div class="ds-empty" style="border:none;">Sin opciones todavía. Agrega la primera abajo.</div>'

        usado = productos_por_grupo.get(g["id"], [])
        usado_html = (
            f'<p class="grupo-usado">Usado en: {_e(", ".join(usado))}</p>'
            if usado else '<p class="grupo-usado">Aún no está asociado a ningún producto.</p>'
        )
        n_opciones = len(g["opciones"])
        tarjetas += f"""
        <section class="ds-panel grupo-card" id="grupo-{g['id']}">
            <div class="grupo-head">
                <div>
                    <h2>{_e(g['nombre'])}</h2>
                    <p class="grupo-resumen">{_e(describir_reglas_grupo(g['obligatorio'], g['seleccion_multiple'], g['minimo'], g['maximo']))} · {n_opciones} {'opción' if n_opciones == 1 else 'opciones'}</p>
                    {usado_html}
                </div>
                <div class="grupo-acciones-head">
                    {'<span class="ds-badge ds-badge-success">Activo</span>' if g['activo'] else '<span class="ds-badge ds-badge-neutral">Inactivo</span>'}
                    <form method="post" action="/menu/modificadores/{g['id']}/activo">
                        <input type="hidden" name="activo" value="{0 if g['activo'] else 1}">
                        <button class="ds-btn ds-btn-secondary ds-btn-sm">{'Desactivar grupo' if g['activo'] else 'Activar grupo'}</button>
                    </form>
                </div>
            </div>
            <div class="opcion-lista">{opciones_html}</div>
            <div class="grupo-pie">
                <details class="menu-desplegable">
                    <summary class="ds-btn ds-btn-ghost ds-btn-sm">➕ Agregar opción</summary>
                    <form method="post" action="/menu/modificadores/{g['id']}/opciones/crear" class="grupo-form-grid">
                        <label class="ds-field"><span class="ds-label">Nombre de la opción</span><input name="nombre" type="text" placeholder="Ej. Fresa" required></label>
                        <label class="ds-field"><span class="ds-label">Precio adicional USD (opcional)</span><input name="precio_adicional" type="number" step="0.01" min="0" value="0"></label>
                        <input type="hidden" name="orden" value="{n_opciones}">
                        <div class="ds-field"><button class="ds-btn ds-btn-primary">Agregar opción</button></div>
                    </form>
                </details>
                <details class="menu-desplegable">
                    <summary class="ds-btn ds-btn-secondary ds-btn-sm">✏️ Editar grupo</summary>
                    {_form_grupo(accion=f"/menu/modificadores/{g['id']}/editar", boton="Guardar grupo", grupo=g, ident=str(g['id']))}
                </details>
            </div>
        </section>"""

    if not tarjetas:
        tarjetas = '<div class="ds-empty">Todavía no hay grupos. Crea el primero con “Crear grupo”.</div>'

    cuerpo = f"""
    <main class="ds-page menu-admin">
        <div class="ds-page-header">
            <div>
                <h1 class="ds-page-title">🍜 Menú</h1>
                <p class="ds-page-subtitle">Opciones que se piden al agregar un producto (sabor, azúcar, tamaño…).</p>
            </div>
        </div>
        {tabs_menu("modificadores")}
        <div class="menu-guia">
            <b>Cómo funciona:</b>
            <ol>
                <li>Crea un grupo</li>
                <li>Agrega sus opciones</li>
                <li>Asócialo a un producto desde Menú → Editar producto</li>
            </ol>
        </div>
        <details class="menu-desplegable" {'open' if not grupos else ''}>
            <summary class="ds-btn ds-btn-primary">➕ Crear grupo</summary>
            <div class="ds-panel">{_form_grupo(accion="/menu/modificadores", boton="Crear grupo")}</div>
        </details>
        {tarjetas}
    </main>
    """
    return _pagina("Modificadores", cuerpo, estilos_base=estilos_base, barra_superior=barra_superior, js=JS_MODIFICADORES)


# ----------------------------------------------------------------------
# Editar producto
# ----------------------------------------------------------------------
JS_EDITAR = """
(function() {
    var input = document.getElementById("imagenArchivo");
    var preview = document.getElementById("imagenPreview");
    var boton = document.getElementById("imagenGuardar");
    if (!input) return;
    input.addEventListener("change", function() {
        var archivo = input.files && input.files[0];
        if (!archivo) { boton.disabled = true; return; }
        boton.disabled = false;
        var img = preview.querySelector("img");
        if (!img) { img = document.createElement("img"); img.alt = ""; preview.appendChild(img); }
        img.src = URL.createObjectURL(archivo);
    });
})();
"""


def render_editar_producto(
    *,
    producto_id,
    producto,
    categorias,
    categoria_nombre,
    activo,
    grupos,
    grupos_asociados,
    imagen_info,
    imagen_url,
    estilos_base,
    barra_superior,
    error="",
    mensaje="",
):
    """producto: (nombre, precio, categoria_id). grupos: lista de dicts como en
    render_menu_modificadores. imagen_info: metadatos de la imagen en BD o None."""
    nombre, precio, categoria_id = producto
    color, icono = estilo_categoria_pos(categoria_nombre or "")

    opciones_categoria = "".join(
        f'<option value="{c[0]}" {"selected" if c[0] == categoria_id else ""}>{_e(c[1])}</option>'
        for c in categorias
    )

    if imagen_info:
        src = f"/producto/{producto_id}/imagen?v={imagen_info['version']}"
        origen = (
            f"Guardada en el sistema · {imagen_info['ancho']}×{imagen_info['alto']} px · "
            f"{round((imagen_info['tamano_bytes'] or 0) / 1024)} KB"
        )
    elif imagen_url:
        src = imagen_url
        origen = "Desde una URL externa (avanzado)."
    else:
        src = ""
        origen = "Sin imagen: el POS muestra el icono de la categoría."
    img_html = f'<img src="{_attr(src)}" alt="" onerror="this.remove()">' if src else ""
    quitar_html = ""
    if imagen_info:
        quitar_html = f"""
            <form method="post" action="/menu/producto/{producto_id}/imagen/quitar" onsubmit="return confirm('¿Quitar la imagen de este producto?');">
                <button class="ds-btn ds-btn-danger ds-btn-block">🗑️ Quitar imagen</button>
            </form>"""

    grupos_html = ""
    for g in grupos:
        nombres = [o[1] for o in g["opciones"] if o[2]]
        vista = ", ".join(nombres[:4]) + (f" +{len(nombres) - 4}" if len(nombres) > 4 else "")
        detalle = describir_reglas_grupo(g["obligatorio"], g["seleccion_multiple"], g["minimo"], g["maximo"])
        inactivo = "" if g["activo"] else " · Grupo inactivo (no se pedirá)"
        grupos_html += f"""
            <label class="grupo-check">
                <input type="checkbox" name="grupo_modificador" value="{g['id']}" {'checked' if g['id'] in grupos_asociados else ''}>
                <span>
                    <span class="grupo-check-nombre">{_e(g['nombre'])}</span>
                    <span class="grupo-check-detalle">{_e(detalle)}{_e(inactivo)}{(' · ' + _e(vista)) if vista else ''}</span>
                </span>
            </label>"""
    if not grupos_html:
        grupos_html = (
            '<div class="ds-empty">No hay grupos de opciones todavía. '
            '<a href="/menu/modificadores" style="color:var(--accent-primary);">Crear el primero</a>.</div>'
        )

    alerta = ""
    if error:
        alerta = f'<div class="ds-alert ds-alert-danger" role="alert">{_e(error)}</div>'
    elif mensaje:
        alerta = f'<div class="ds-alert ds-alert-success" role="status">{_e(mensaje)}</div>'

    estado_badge = (
        '<span class="ds-badge ds-badge-success">Activo</span>'
        if activo else '<span class="ds-badge ds-badge-neutral">Inactivo</span>'
    )

    cuerpo = f"""
    <main class="ds-page menu-admin">
        <div class="ds-page-header">
            <div>
                <h1 class="ds-page-title">✏️ {_e(nombre)}</h1>
                <p class="ds-page-subtitle">{_e(categoria_nombre or 'Sin categoría')} · {estado_badge}</p>
            </div>
            <a class="ds-btn ds-btn-secondary" href="/menu">← Volver a Menú</a>
        </div>
        {tabs_menu("productos")}
        {alerta}
        <div class="editar-layout">
            <form method="post" action="/editar_producto/{producto_id}" id="formProducto">
                <section class="ds-panel">
                    <h2>Datos del producto</h2>
                    <div class="menu-form-grid">
                        <label class="ds-field"><span class="ds-label">Nombre</span><input name="nombre" type="text" value="{_attr(nombre)}" required></label>
                        <label class="ds-field"><span class="ds-label">Precio USD</span><input name="precio" type="number" step="0.01" min="0" value="{_attr(precio)}" required></label>
                        <label class="ds-field"><span class="ds-label">Categoría</span><select name="categoria_id">{opciones_categoria}</select></label>
                    </div>
                </section>
                <section class="ds-panel">
                    <h2>Opciones del producto</h2>
                    <p class="editar-ayuda">Los grupos seleccionados se pedirán al agregar este producto a una orden.</p>
                    <div class="grupos-producto">{grupos_html}</div>
                    <p class="editar-ayuda" style="margin:12px 0 0;"><a href="/menu/modificadores" style="color:var(--accent-primary);">Gestionar grupos y opciones →</a></p>
                </section>
                <section class="ds-panel">
                    <details>
                        <summary style="cursor:pointer;font-weight:800;color:var(--text-secondary);">Imagen por URL (avanzado)</summary>
                        <p class="editar-ayuda" style="margin-top:8px;">Opcional. Si subes una imagen, la imagen subida tiene prioridad.</p>
                        <input name="imagen_url" type="text" value="{_attr(imagen_url or '')}" placeholder="https://... o /static/...">
                    </details>
                </section>
                <button class="ds-btn ds-btn-primary ds-btn-lg ds-btn-block" type="submit">💾 Guardar cambios</button>
            </form>
            <aside>
                <section class="ds-panel">
                    <h2>Imagen del producto</h2>
                    <p class="editar-ayuda">Se mostrará en el POS y futuro menú QR.</p>
                    <div class="imagen-preview" id="imagenPreview" style="--cat-tint:{color}22;">
                        <span class="menu-placeholder" aria-hidden="true">{icono}</span>{img_html}
                    </div>
                    <form method="post" action="/menu/producto/{producto_id}/imagen" enctype="multipart/form-data">
                        <label class="ds-label" for="imagenArchivo">{'Reemplazar imagen' if imagen_info else 'Seleccionar imagen'}</label>
                        <input class="imagen-archivo" id="imagenArchivo" name="imagen" type="file" accept="image/jpeg,image/png,image/webp" required>
                        <button class="ds-btn ds-btn-primary ds-btn-block" id="imagenGuardar" disabled>{'⬆️ Reemplazar imagen' if imagen_info else '⬆️ Subir imagen'}</button>
                    </form>
                    {quitar_html}
                    <p class="imagen-info">{_e(origen)}<br>JPG, PNG o WebP · máx. 8 MB · se optimiza automáticamente.</p>
                </section>
            </aside>
        </div>
    </main>
    """
    return _pagina(f"Editar {nombre}", cuerpo, estilos_base=estilos_base, barra_superior=barra_superior, js=JS_EDITAR)
