"""
order_detail_view.py (presentacion)

Render HTML/JS de la pantalla de detalle de orden (`/orden/<id>` en
web_app.py, GET). La ruta resuelve TODOS los datos (repositorios) y
llama a `render_detalle_orden(...)`; este modulo no tiene consultas ni
escrituras propias.

Deliberadamente NO usa Jinja/templates/: el codigo original usa
f-strings con `html_lib.escape()` manual en cada punto de interpolacion
(no autoescaping); se mantiene ese patron para no arriesgar una
regresion de XSS por una migracion de motor no pedida.

Rediseno UX (octubre 2026): layout catalogo + resumen sticky, barra
sticky con buscador y chips de categoria, tarjetas de producto con
imagen opcional / placeholder y cantidad integrada, resumen agrupado
por producto y bottom-sheet en movil. El CSS y el JS viven en
constantes planas (`_CSS_ORDEN`, `_JS_ORDEN`) en vez de dentro del
f-string, asi no hace falta duplicar llaves; los datos que el JS
necesita llegan por atributos `data-*` del <body>. El flujo de
agregado (URLs /agregar/... y /agregar_con_modificadores/..., query
params `cantidad`, `sabor`, `acompanante`, `bebida`, `pollo`, `arroz`,
`extra_lumpias`, `grupo_<id>`) es el MISMO que antes: solo cambia la
presentacion.

Todo lo que esta funcion necesita se recibe explicito (nada de
`import web_app` ni acceso a `session`/`request` directamente):
valores ya resueltos por la ruta, constantes de configuracion del menu
POS (viven en web_app.py, se inyectan para evitar un import circular)
y helpers de presentacion compartidos con otras pantallas
(estilos_base, barra_superior, etc.).
"""

import html as html_lib
import json
import re
import unicodedata
from collections import defaultdict

from app.domain.sales.calculations import (
    DELIVERY_MONTO_MAXIMO,
    TOLERANCIA_COBRO,
    es_producto_delivery_legacy,
)
from app.domain.sales.item_builder import MAX_CANTIDAD_ITEM, es_producto_refresco
from app.domain.sales.item_descriptions import (
    texto_descripcion_combo_orden,
    texto_descripcion_modificador_orden,
    texto_descripcion_promocion_orden,
)
from app.domain.sales.modifiers import producto_agotado_por_modificadores


# Color/icono por categoria: se usa SOLO como orientacion (chip, borde,
# placeholder), nunca como fondo completo. Se resuelve por palabra clave
# para que una categoria nueva ("Cervezas", "Postres") tome su color sin
# tocar codigo; lo que no coincide cae en el neutro. El orden importa
# ("cerveza" antes que "bebida").
_ESTILOS_CATEGORIA = (
    (("combo",), "#35D07F", "🍱"),
    (("promo",), "#FF8A4C", "🔥"),
    (("cerveza",), "#F2B94B", "🍺"),
    (("bebida", "refresco", "jugo", "batido"), "#5BC0EB", "🥤"),
    (("postre", "dulce", "helado"), "#F472B6", "🍰"),
    (("extra", "contorno", "adicional", "salsa"), "#A78BFA", "➕"),
    (("favorito",), "#2DD4BF", "⭐"),
    (("arroz", "arroces", "duo", "clan", "principal", "plato", "wok"), "#4DA3FF", "🍚"),
    (("delivery",), "#94A3B8", "🛵"),
)
_ESTILO_CATEGORIA_NEUTRO = ("#94A3B8", "🍽️")


def _normalizar(texto):
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).lower()


def estilo_categoria_pos(nombre_categoria):
    """(color_hex, icono) para una categoria del catalogo POS."""
    nombre = _normalizar(nombre_categoria)
    for palabras, color, icono in _ESTILOS_CATEGORIA:
        if any(palabra in nombre for palabra in palabras):
            return color, icono
    return _ESTILO_CATEGORIA_NEUTRO


def _rgba(color_hex, alpha):
    color = color_hex.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def _formato_usd(valor):
    return f"${float(valor or 0):.2f}"


_ESTADO_CLASE = {
    "abierta": "estado-abierta",
    "en cocina": "estado-cocina",
    "listo": "estado-listo",
    "cerrada": "estado-cerrada",
}


def _icono_tipo_orden(tipo):
    tipo_norm = _normalizar(tipo)
    if "delivery" in tipo_norm:
        return "🛵"
    if "llevar" in tipo_norm or "pickup" in tipo_norm or "retiro" in tipo_norm:
        return "🥡"
    return "🍽️"


def _grupos_modificador_json(grupos):
    return json.dumps(
        [
            {
                "id": grupo.id,
                "nombre": grupo.nombre,
                "multiple": grupo.seleccion_multiple,
                "obligatorio": grupo.obligatorio,
                "minimo": grupo.minimo,
                "maximo": grupo.maximo,
                "opciones": [
                    {"nombre": opcion.nombre, "disponible": opcion.disponible}
                    for opcion in grupo.opciones
                ],
            }
            for grupo in grupos
        ]
    )


def _render_tarjeta_producto(
    *,
    orden_id,
    p,
    categoria,
    icono_categoria,
    imagen_url,
    modificadores_por_producto,
    COMBOS_PERSONALES,
    ACOMPANANTES_COMBO,
    BEBIDAS_COMBO,
    COMBOS_CANTIDAD_ACOMPANANTES,
    PROMOCIONES_NEKO,
    PROMOCIONES_CON_POLLO,
    POLLOS_PROMOCION,
    ARROCES_PROMOCION,
):
    """Una tarjeta del catalogo. Las clases del boton (btn-simple,
    btn-refresco, btn-configurable, btn-modificadores) y sus data-*
    son el contrato con el JS de agregado: no renombrarlas."""
    producto_id, nombre = p[0], p[1]
    nombre_html = html_lib.escape(nombre)
    nombre_attr = html_lib.escape(nombre, quote=True)
    categoria_attr = html_lib.escape(categoria, quote=True)
    precio_html = _formato_usd(p[2])
    agotado = False
    badges = []

    if es_producto_refresco(nombre):
        clase_boton = "btn-refresco"
        texto_boton = "Elegir sabor"
        badges.append(("Sabor", "badge-config"))
        data_boton = f'data-url="/agregar/{orden_id}/{producto_id}" data-producto="{nombre_attr}"'
    elif nombre in COMBOS_PERSONALES:
        acompanantes_data = html_lib.escape("|".join(ACOMPANANTES_COMBO), quote=True)
        bebidas_data = html_lib.escape("|".join(BEBIDAS_COMBO), quote=True)
        cantidad_acompanantes = COMBOS_CANTIDAD_ACOMPANANTES.get(nombre, 1)
        clase_boton = "btn-configurable"
        texto_boton = "Configurar"
        badges.append(("Combo", "badge-config"))
        data_boton = (
            f'data-tipo="combo" data-url="/agregar/{orden_id}/{producto_id}" '
            f'data-producto="{nombre_attr}" data-acompanantes="{acompanantes_data}" '
            f'data-cantidad-acompanantes="{cantidad_acompanantes}" data-bebidas="{bebidas_data}"'
        )
    elif nombre in PROMOCIONES_NEKO:
        promo = PROMOCIONES_NEKO[nombre]
        pollos_data = html_lib.escape(
            "|".join(POLLOS_PROMOCION if nombre in PROMOCIONES_CON_POLLO else []), quote=True
        )
        arroces_data = html_lib.escape("|".join(ARROCES_PROMOCION), quote=True)
        clase_boton = "btn-configurable"
        texto_boton = "Configurar"
        badges.append(("Promo", "badge-config"))
        data_boton = (
            f'data-tipo="promocion" data-url="/agregar/{orden_id}/{producto_id}" '
            f'data-producto="{nombre_attr}" data-pollos="{pollos_data}" '
            f'data-arroces="{arroces_data}" data-cantidad-arroces="{promo["cantidad_arroces"]}" '
            f'data-cantidad-refrescos="{promo["cantidad_refrescos"]}" data-refresco="{promo["refresco"]}"'
        )
    elif modificadores_por_producto.get(producto_id):
        grupos = modificadores_por_producto[producto_id]
        grupos_data = html_lib.escape(_grupos_modificador_json(grupos), quote=True)
        clase_boton = "btn-modificadores"
        texto_boton = "Configurar"
        badges.append(("Opciones", "badge-config"))
        agotado = producto_agotado_por_modificadores(grupos)
        data_boton = (
            f'data-url="/agregar_con_modificadores/{orden_id}/{producto_id}" '
            f'data-producto="{nombre_attr}" data-modificadores="{grupos_data}"'
        )
    else:
        clase_boton = "btn-simple"
        texto_boton = "Añadir"
        data_boton = f'data-url="/agregar/{orden_id}/{producto_id}"'

    if agotado:
        badges = [("Agotado", "badge-agotado")]
        texto_boton = "Agotado"

    badges_html = "".join(
        f'<span class="badge {clase}">{html_lib.escape(texto)}</span>' for texto, clase in badges
    )
    imagen_html = ""
    if imagen_url:
        imagen_html = (
            f'<img src="{html_lib.escape(imagen_url, quote=True)}" alt="" loading="lazy" '
            'decoding="async" onerror="this.remove()">'
        )
    deshabilitado = " disabled" if agotado else ""
    clase_variante = "" if clase_boton == "btn-simple" else " configurar"
    clase_tarjeta = "producto-card producto-item" + (" agotado" if agotado else "")

    return f"""
                    <article class="{clase_tarjeta}" data-nombre="{nombre_attr}" data-categoria="{categoria_attr}" data-producto-id="{producto_id}">
                        <div class="card-media{' con-imagen' if imagen_url else ''}">
                            <span class="card-placeholder" aria-hidden="true">{icono_categoria}</span>
                            {imagen_html}
                            <div class="card-badges">{badges_html}</div>
                        </div>
                        <div class="card-body">
                            <h3 class="card-nombre">{nombre_html}</h3>
                            <div class="card-precio">{precio_html}</div>
                            <div class="card-acciones">
                                <div class="qty-stepper" role="group" aria-label="Cantidad de {nombre_attr}">
                                    <button type="button" class="qty-btn qty-dec" aria-label="Menos"{deshabilitado}>−</button>
                                    <input type="number" class="qty-input" min="1" max="{MAX_CANTIDAD_ITEM}" step="1" value="1" inputmode="numeric" aria-label="Cantidad"{deshabilitado}>
                                    <button type="button" class="qty-btn qty-inc" aria-label="Más"{deshabilitado}>+</button>
                                </div>
                                <button class="btn-add {clase_boton}{clase_variante}" type="button" {data_boton}{deshabilitado}>
                                    <span class="btn-add-texto">{texto_boton}</span><span class="btn-add-qty"></span>
                                </button>
                            </div>
                        </div>
                    </article>
    """


def _agrupar_items(items):
    """Agrupa filas de orden_items identicas (mismo producto, precio e
    indicacion) para mostrar "4×" en vez de 4 filas. Cada unidad sigue
    siendo su propia fila en BD; los botones del grupo actuan sobre UNA
    unidad (la ultima), igual que antes actuaban sobre su fila."""
    grupos = {}
    for item in items:
        clave = (item[0], round(float(item[1] or 0), 2), item[3] or "")
        grupos.setdefault(clave, []).append(item)
    return list(grupos.values())


def render_detalle_orden(
    *,
    orden_id,
    o,
    estado,
    productos,
    items,
    bloqueada_por_cierre,
    edicion_emergencia_activa,
    puede_modificar_orden,
    self_ordering_panel,
    delivery_usd,
    delivery_repartidor_id,
    repartidores_activos,
    repartidor_delivery_actual,
    tiene_delivery_legacy,
    total_orden_usd,
    total_orden_bs,
    pendiente_post_cobro,
    conductor_delivery_info,
    conductores_delivery_activos,
    ORDEN_CATEGORIAS_POS,
    COMBOS_PERSONALES,
    ACOMPANANTES_COMBO,
    BEBIDAS_COMBO,
    COMBOS_CANTIDAD_ACOMPANANTES,
    PROMOCIONES_NEKO,
    PROMOCIONES_CON_POLLO,
    POLLOS_PROMOCION,
    ARROCES_PROMOCION,
    DELIVERY_MONTOS_RAPIDOS,
    estilos_base,
    barra_superior,
    formato_bs_resumen,
    texto_numero_orden,
    usuario_es_admin_cierre,
    usuario_puede_reimprimir_cocina,
    _render_panel_conductor_delivery,
    modificadores_por_producto=None,
    imagenes_por_producto=None,
):
    modificadores_por_producto = modificadores_por_producto or {}
    imagenes_por_producto = imagenes_por_producto or {}
    numero_orden_html = html_lib.escape(texto_numero_orden(o[1]))

    # ------------------------------------------------------------------
    # Catalogo
    # ------------------------------------------------------------------
    cats_dict = defaultdict(list)
    for p in productos:
        cat_nombre = p[3] if p[3] else "Sin categoria"
        if es_producto_delivery_legacy(p[1], cat_nombre):
            continue
        cats_dict[cat_nombre].append(p)

    orden_cat_map = {nombre: i for i, nombre in enumerate(ORDEN_CATEGORIAS_POS)}
    cats_ordenadas = sorted(
        cats_dict.items(),
        key=lambda x: (orden_cat_map.get(x[0], 999), x[0]),
    )

    avisos_html = ""
    if bloqueada_por_cierre:
        avisos_html = """
        <div class="info-cierre">
            Esta orden ya pertenece a un cierre de jornada. Primero debes revertirla desde reportes.
        </div>
        """
    elif estado == "cerrada" and edicion_emergencia_activa:
        avisos_html = """
        <div class="info-cierre">
            Edicion de emergencia activa. Corrige la orden y vuelve a cobrar para actualizar los pagos.
        </div>
        """
    elif not puede_modificar_orden:
        avisos_html = f"""
        <div class="info-cierre info-neutra">
            Esta orden está <b>{html_lib.escape(estado)}</b>: el catálogo está bloqueado.
        </div>
        """

    chips_html = ""
    secciones_html = ""
    if puede_modificar_orden:
        ids_usados = set()
        for categoria, lista in cats_ordenadas:
            color_cat, icono_cat = estilo_categoria_pos(categoria)
            slug = re.sub(r"[^a-z0-9]+", "-", _normalizar(categoria)).strip("-") or "categoria"
            seccion_id = f"cat-{slug}"
            sufijo = 2
            while seccion_id in ids_usados:
                seccion_id = f"cat-{slug}-{sufijo}"
                sufijo += 1
            ids_usados.add(seccion_id)

            estilo_cat = (
                f"--cat:{color_cat};--cat-tint:{_rgba(color_cat, 0.14)};"
                f"--cat-borde:{_rgba(color_cat, 0.55)};"
            )
            categoria_html = html_lib.escape(categoria)
            chips_html += f"""
            <a class="cat-chip" href="#{seccion_id}" data-target="{seccion_id}" style="{estilo_cat}">
                <span class="cat-chip-icono" aria-hidden="true">{icono_cat}</span>{categoria_html}<span class="cuenta">{len(lista)}</span>
            </a>"""

            tarjetas_html = "".join(
                _render_tarjeta_producto(
                    orden_id=orden_id,
                    p=p,
                    categoria=categoria,
                    icono_categoria=icono_cat,
                    imagen_url=imagenes_por_producto.get(p[0]),
                    modificadores_por_producto=modificadores_por_producto,
                    COMBOS_PERSONALES=COMBOS_PERSONALES,
                    ACOMPANANTES_COMBO=ACOMPANANTES_COMBO,
                    BEBIDAS_COMBO=BEBIDAS_COMBO,
                    COMBOS_CANTIDAD_ACOMPANANTES=COMBOS_CANTIDAD_ACOMPANANTES,
                    PROMOCIONES_NEKO=PROMOCIONES_NEKO,
                    PROMOCIONES_CON_POLLO=PROMOCIONES_CON_POLLO,
                    POLLOS_PROMOCION=POLLOS_PROMOCION,
                    ARROCES_PROMOCION=ARROCES_PROMOCION,
                )
                for p in lista
            )
            secciones_html += f"""
            <section class="cat-seccion" id="{seccion_id}" style="{estilo_cat}" aria-labelledby="{seccion_id}-titulo">
                <header class="cat-head">
                    <span class="cat-icono" aria-hidden="true">{icono_cat}</span>
                    <h2 id="{seccion_id}-titulo">{categoria_html}</h2>
                    <span class="cat-count">{len(lista)} {'producto' if len(lista) == 1 else 'productos'}</span>
                </header>
                <div class="grid-productos">{tarjetas_html}
                </div>
            </section>"""

    cantidad_items = len(items)
    total_usd_html = _formato_usd(total_orden_usd)
    nav_html = ""
    if puede_modificar_orden:
        nav_html = f"""
        <div class="catalogo-nav" id="catalogoNav">
            <div class="nav-fila">
                <label class="buscador">
                    <span class="buscador-icono" aria-hidden="true">🔍</span>
                    <input id="buscarProducto" type="search" placeholder="Buscar producto..." autocomplete="off" aria-label="Buscar producto">
                    <button type="button" class="buscador-limpiar" id="limpiarBusqueda" aria-label="Limpiar búsqueda" hidden>✕</button>
                </label>
                <button type="button" class="btn-ver-orden" id="btnVerOrden" aria-controls="ordenResumen">
                    🧾 <span class="ver-orden-texto">Ver orden</span>
                    <span class="pill">{cantidad_items}</span>
                    <b class="ver-orden-total">{total_usd_html}</b>
                </button>
            </div>
            <nav class="cat-chips" id="catChips" aria-label="Categorías">{chips_html}
            </nav>
        </div>
        """

    # ------------------------------------------------------------------
    # Resumen de la orden
    # ------------------------------------------------------------------
    boton_editar_orden = ""
    if puede_modificar_orden:
        boton_editar_orden = f'<a href="/editar_orden/{orden_id}" class="btn-accion btn-sec btn-mini">✏️ Editar orden</a>'

    boton_eliminar_orden = ""
    if usuario_es_admin_cierre() and not bloqueada_por_cierre and estado in ("abierta", "en cocina"):
        boton_eliminar_orden = f"""
            <form method="post" action="/eliminar_orden/{orden_id}" class="form-eliminar-orden">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-accion btn-sec btn-mini peligro">🗑️ Eliminar orden</button>
            </form>
        """

    boton_emergencia = ""
    if usuario_es_admin_cierre() and estado == "cerrada" and not bloqueada_por_cierre:
        if edicion_emergencia_activa:
            boton_emergencia = '<div class="btn-accion btn-sec btn-mini peligro">🚨 Emergencia activa</div>'
        else:
            boton_emergencia = f"""
            <form method="post" action="/activar_edicion_emergencia/{orden_id}" class="form-emergencia">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-accion btn-sec btn-mini peligro">🚨 Editar emergencia</button>
            </form>
            """

    acciones_admin_html = ""
    if boton_editar_orden or boton_eliminar_orden or boton_emergencia:
        acciones_admin_html = f"""
        <div class="acciones-superiores">
            {boton_editar_orden}
            {boton_eliminar_orden}
            {boton_emergencia}
        </div>
        """

    tipo_html = html_lib.escape(o[3] or "-")
    referencia_html = html_lib.escape(o[4] or "-")
    cliente_html = html_lib.escape(o[5] or "-")
    mesonera_html = html_lib.escape(o[9] or "-")
    estado_html = html_lib.escape(estado)
    observacion_html = html_lib.escape(o[7] or "-")
    clase_estado = _ESTADO_CLASE.get(estado, "estado-cerrada")

    items_html = ""
    for grupo in _agrupar_items(items):
        unidad = grupo[-1]
        cantidad = len(grupo)
        precio_unitario = float(unidad[1] or 0)
        if not puede_modificar_orden:
            boton_eliminar = ""
            boton_indicacion = ""
        else:
            titulo_unidad = " (1 unidad)" if cantidad > 1 else ""
            boton_eliminar = f"""
            <form method="post" action="/eliminar_item/{unidad[2]}/{orden_id}" class="form-eliminar-item">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-item peligro" title="Quitar{titulo_unidad}" aria-label="Quitar {html_lib.escape(unidad[0], quote=True)}{titulo_unidad}">✕</button>
            </form>
            """
            boton_indicacion = f"""
            <form method="post" action="/actualizar_indicacion_item/{unidad[2]}/{orden_id}" class="form-indicacion-item" data-indicacion="{html_lib.escape(unidad[3] or '', quote=True)}">
                <input type="hidden" name="indicacion" value="">
                <button type="submit" class="btn-item" title="Indicación{titulo_unidad}" aria-label="Indicación{titulo_unidad}">✏️</button>
            </form>
            """

        descripcion_combo = (
            texto_descripcion_combo_orden(unidad[0], unidad[3])
            or texto_descripcion_promocion_orden(unidad[0], unidad[3])
            or texto_descripcion_modificador_orden(unidad[3])
        )
        indicacion_html = ""
        if descripcion_combo:
            descripcion_segura = "<br>".join(
                html_lib.escape(linea) for linea in descripcion_combo.splitlines()
            )
            indicacion_html = f"<div class='item-descripcion'>{descripcion_segura}</div>"
        elif unidad[3]:
            indicacion_html = f"<div class='item-indicacion'>(Indicación: {html_lib.escape(unidad[3])})</div>"

        items_html += f"""
        <div class="item-orden" data-item-producto="{html_lib.escape(unidad[0], quote=True)}" data-cantidad="{cantidad}">
            <div class="item-cant">{cantidad}×</div>
            <div class="item-detalle">
                <div class="item-nombre">{html_lib.escape(unidad[0])}</div>
                <div class="item-unit">{_formato_usd(precio_unitario)} c/u</div>
                {indicacion_html}
            </div>
            <div class="item-derecha">
                <div class="item-subtotal">{_formato_usd(precio_unitario * cantidad)}</div>
                <div class="acciones-item">
                    {boton_indicacion}
                    {boton_eliminar}
                </div>
            </div>
        </div>
        """

    if not items:
        items_html = """
        <div class="resumen-vacio">
            <div class="resumen-vacio-icono" aria-hidden="true">🛒</div>
            Aún no hay productos.<br>Elige uno del catálogo para empezar.
        </div>
        """

    # Delivery (mismo formulario y reglas que antes)
    repartidor_options = '<option value="">Sin repartidor</option>'
    for rep in repartidores_activos:
        selected = "selected" if rep[0] == delivery_repartidor_id else ""
        repartidor_options += (
            f'<option value="{rep[0]}" {selected}>{html_lib.escape(rep[1])}</option>'
        )

    if delivery_usd > TOLERANCIA_COBRO and not delivery_repartidor_id:
        delivery_estado_repartidor = "Repartidor: Pendiente de asignar"
    elif delivery_repartidor_id and repartidor_delivery_actual:
        delivery_estado_repartidor = f"Repartidor: {html_lib.escape(repartidor_delivery_actual[1] or '')}"
    else:
        delivery_estado_repartidor = "Repartidor: Sin delivery"

    botones_delivery = ""
    for monto_rapido in DELIVERY_MONTOS_RAPIDOS:
        activo = "activo" if abs(delivery_usd - monto_rapido) <= TOLERANCIA_COBRO else ""
        botones_delivery += (
            f'<button type="button" class="delivery-monto-btn {activo}" '
            f'data-delivery-monto="{monto_rapido:.2f}">${monto_rapido:.2f}</button>'
        )

    delivery_bloqueado = (not puede_modificar_orden) or tiene_delivery_legacy
    delivery_disabled = "disabled" if delivery_bloqueado else ""
    delivery_aviso = ""
    if tiene_delivery_legacy:
        delivery_aviso = (
            "<div class='delivery-alerta'>"
            "Esta orden contiene un delivery agregado con el sistema anterior. "
            "No se puede agregar delivery explícito para evitar doble cargo."
            "</div>"
        )
    elif not puede_modificar_orden:
        delivery_aviso = "<div class='delivery-alerta'>Delivery bloqueado para esta orden.</div>"

    # Delivery abierto por defecto si la orden es delivery o ya tiene monto.
    delivery_abierto = (
        "open"
        if delivery_usd > TOLERANCIA_COBRO or "delivery" in (o[3] or "").lower() or tiene_delivery_legacy
        else ""
    )
    delivery_resumen = (
        f"{_formato_usd(delivery_usd)}" if delivery_usd > TOLERANCIA_COBRO else "Sin delivery"
    )

    # Acciones
    advertencia_cobro = ""
    if estado == "abierta":
        advertencia_cobro = (
            ' onclick="return confirm(\'⚠️ Esta orden aún no ha sido enviada a cocina. '
            '¿Seguro que quieres continuar con el cobro?\')"'
        )

    acciones_primarias = ""
    if not bloqueada_por_cierre and estado != "cerrada":
        acciones_primarias += f"""
            <a href="/enviar_cocina/{orden_id}" class="btn-accion cocina">🍳 Enviar a cocina</a>
            <a href="/cobrar/{orden_id}" class="btn-accion cobrar"{advertencia_cobro}>💵 Cobrar</a>
        """
    elif edicion_emergencia_activa:
        acciones_primarias += f"""
            <a href="/cobrar/{orden_id}" class="btn-accion cobrar ancho">💵 Volver a cobrar</a>
        """
    if not bloqueada_por_cierre and pendiente_post_cobro:
        acciones_primarias += f"""
            <a href="/orden/{orden_id}/cobrar_pendiente" class="btn-accion pendiente ancho">💵 Cobrar consumo adicional (${pendiente_post_cobro['pendiente_usd']:.2f})</a>
        """

    acciones_secundarias = ""
    if not bloqueada_por_cierre and estado != "cerrada":
        acciones_secundarias += f'<a href="/activar_factura/{orden_id}" class="btn-accion btn-sec">🧾 Facturar</a>'
    if usuario_puede_reimprimir_cocina() and estado in ("en cocina", "listo", "cerrada"):
        acciones_secundarias += f'<a href="/reimprimir_cocina/{orden_id}" class="btn-accion btn-sec">🔁 Reimprimir cocina</a>'
    if not bloqueada_por_cierre and items and estado in ("abierta", "en cocina", "listo", "cerrada"):
        acciones_secundarias += f'<a href="/reimprimir_factura/{orden_id}" class="btn-accion btn-sec">🧾 Reimprimir factura</a>'
    acciones_secundarias += f"""
        <a href="/factura/{orden_id}" class="btn-accion btn-sec">🔍 Ver factura</a>
        <a href="/" class="btn-accion btn-sec volver">🏠 Volver</a>
    """

    resumen_html = f"""
    <aside class="resumen" id="ordenResumen" aria-label="Resumen de la orden" tabindex="-1">
        <div class="resumen-head">
            <div class="resumen-titulo">
                <h2>🧾 Orden {numero_orden_html}</h2>
                <span class="estado-pill {clase_estado}">{estado_html}</span>
                <button type="button" class="resumen-cerrar" id="cerrarResumen" aria-label="Cerrar resumen">✕</button>
            </div>
            <div class="resumen-chips">
                <span class="meta-chip">{_icono_tipo_orden(o[3])} {tipo_html}</span>
                <span class="meta-chip">📍 {referencia_html}</span>
            </div>
            {acciones_admin_html}
        </div>
        <div class="resumen-body">
            <dl class="info-orden">
                <dt>Cliente</dt><dd>👤 {cliente_html}</dd>
                <dt>Mesonera</dt><dd>👩 <b>{mesonera_html}</b></dd>
                <dt>Observación</dt><dd>{observacion_html}</dd>
            </dl>
            {self_ordering_panel}
            <div class="seccion-titulo"><span>🍽️ Productos</span><span>{cantidad_items} {'ítem' if cantidad_items == 1 else 'ítems'}</span></div>
            <div class="lista-items">{items_html}
            </div>
            <details class="delivery-panel" {delivery_abierto}>
                <summary><span>🛵 Delivery</span><span class="delivery-resumen">{delivery_resumen}</span></summary>
                {delivery_aviso}
                <form method="post" action="/orden/{orden_id}/delivery" id="deliveryForm">
                    <label>Monto USD</label>
                    <div class="delivery-grid">{botones_delivery}</div>
                    <input name="delivery_usd" id="delivery_usd" type="number" min="0" max="{DELIVERY_MONTO_MAXIMO:.2f}" step="0.01" value="{delivery_usd:.2f}" {delivery_disabled}>
                    <label>Repartidor</label>
                    <select name="delivery_repartidor_id" id="delivery_repartidor_id" {delivery_disabled}>
                        {repartidor_options}
                    </select>
                    <div class="delivery-help">{delivery_estado_repartidor}</div>
                    <div class="delivery-help">Puedes guardar el monto y asignar el repartidor mas tarde. Para cobrar, debe estar asignado.</div>
                    <div class="delivery-actions">
                        <button class="btn" type="submit" {delivery_disabled}>Guardar delivery</button>
                        <button class="btn" type="button" id="mostrarNuevoRepartidor" {delivery_disabled}>+ Nuevo repartidor</button>
                    </div>
                </form>
                <div class="delivery-nuevo" id="nuevoRepartidorPanel">
                    <input id="nuevoRepartidorNombre" placeholder="Nombre del repartidor">
                    <input id="nuevoRepartidorTelefono" placeholder="Teléfono">
                    <button class="btn" type="button" id="guardarNuevoRepartidor">Crear y seleccionar</button>
                    <div class="delivery-help" id="nuevoRepartidorMensaje"></div>
                    <a href="/repartidores" class="delivery-help">Administrar repartidores</a>
                </div>
            </details>
            {_render_panel_conductor_delivery(orden_id, conductor_delivery_info, conductores_delivery_activos)}
            <div class="seccion-titulo"><span>Más acciones</span></div>
            <div class="acciones-secundarias">
                {acciones_secundarias}
            </div>
        </div>
        <div class="resumen-footer">
            <div class="total total-cliente">Total Orden: {total_usd_html}</div>
            <div class="total-bs">Bs: {formato_bs_resumen(total_orden_bs)}</div>
            <div class="acciones-primarias">
                {acciones_primarias}
            </div>
        </div>
    </aside>
    """

    # ------------------------------------------------------------------
    # Pagina
    # ------------------------------------------------------------------
    clase_body = "pagina-orden" + ("" if puede_modificar_orden else " sin-catalogo")
    catalogo_vacio_html = ""
    if puede_modificar_orden and not cats_ordenadas:
        catalogo_vacio_html = '<div class="sin-resultados">No hay productos activos en el menú.</div>'

    fab_html = ""
    if puede_modificar_orden:
        fab_html = f"""
    <button type="button" class="fab-orden" id="fabOrden" aria-controls="ordenResumen">
        <span>🧾 Ver orden <span class="pill">{cantidad_items}</span></span>
        <b>{total_usd_html}</b>
    </button>
        """

    html = f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <title>Orden {numero_orden_html} · Neko Wok POS</title>
    <style>
    {estilos_base()}
    {_CSS_ORDEN}
    </style>
    </head>
    <body class="{clase_body}" data-orden-id="{orden_id}" data-max-cantidad="{MAX_CANTIDAD_ITEM}" data-items="{cantidad_items}">
    """

    html += barra_superior('<a href="/">🏠 Inicio</a>')

    html += f"""
    <div class="orden-app">
        <main class="catalogo" id="catalogo">
            {nav_html}
            {avisos_html}
            {secciones_html}
            {catalogo_vacio_html}
            <div class="sin-resultados" id="sinResultados" hidden>
                No hay productos que coincidan con «<span id="sinResultadosTexto"></span>».
            </div>
        </main>
        {resumen_html}
    </div>
    {fab_html}
    <div class="resumen-backdrop" id="resumenBackdrop"></div>
    <div class="toast-orden" id="toastOrden" role="status" aria-live="polite"></div>
    <div id="modal-refresco" class="modal-refresco" aria-hidden="true">
        <div class="modal-contenido" role="dialog" aria-modal="true" aria-labelledby="modal-refresco-titulo">
            <div class="modal-top">
                <div>
                    <h2 id="modal-refresco-titulo">🥤 Seleccionar sabor</h2>
                    <p id="modal-refresco-producto">Refresco</p>
                </div>
                <button id="cerrar-modal-refresco" class="cerrar-modal" type="button" aria-label="Cerrar">✕</button>
            </div>
            <div id="sabores-refresco-grid" class="sabores-grid"></div>
        </div>
    </div>
    <div id="modal-configuracion" class="modal-refresco" aria-hidden="true">
        <div class="modal-contenido" role="dialog" aria-modal="true" aria-labelledby="modal-configuracion-titulo">
            <div class="modal-top">
                <div>
                    <h2 id="modal-configuracion-titulo">Configurar producto</h2>
                    <p id="modal-configuracion-producto">Producto</p>
                </div>
                <button id="cerrar-modal-configuracion" class="cerrar-modal" type="button" aria-label="Cerrar">✕</button>
            </div>
            <div id="configuracion-opciones-grid" class="sabores-grid"></div>
        </div>
    </div>
    <script>
    {_JS_ORDEN}
    </script>
    </body>
    </html>
    """
    return html


# ----------------------------------------------------------------------
# Estilos propios de la pantalla. Colores y tokens vienen del design system
# global (app.presentation.web.design_system, via estilos_base()).
# ----------------------------------------------------------------------
_CSS_ORDEN = """
body.pagina-orden {
    --header-h: 0px;
    --nav-h: 0px;
    margin: 0;
}
.pagina-orden [hidden] { display: none !important; }
.pagina-orden a:focus-visible, .pagina-orden button:focus-visible,
.pagina-orden input:focus-visible, .pagina-orden select:focus-visible,
.pagina-orden summary:focus-visible {
    outline: 3px solid var(--info);
    outline-offset: 2px;
}
.pagina-orden .resumen-body input, .pagina-orden .resumen-body select { width: 100%; margin: 6px 0 10px; background: var(--bg-main); }
.pagina-orden button:active { transform: none; }

/* ---------- Layout ---------- */
.orden-app {
    display: grid;
    grid-template-columns: minmax(0, 1fr) clamp(330px, 31vw, 430px);
    gap: 20px;
    max-width: 1640px;
    margin: 0 auto;
    padding: 4px 20px 28px;
    align-items: start;
}
.catalogo { min-width: 0; }
/* Sin catalogo (orden cerrada/bloqueada): una sola columna centrada. */
body.sin-catalogo .orden-app { grid-template-columns: minmax(0, 680px); justify-content: center; }
body.sin-catalogo .resumen { position: static; max-height: none; }

/* ---------- Barra sticky: buscador + chips ---------- */
.catalogo-nav {
    position: sticky;
    top: var(--header-h);
    z-index: 15;
    background: var(--bg-main);
    padding: 12px 0 10px;
    border-bottom: 1px solid var(--border);
}
.nav-fila { display: flex; gap: 10px; align-items: center; }
.buscador { flex: 1; position: relative; display: block; min-width: 0; }
.buscador input {
    width: 100%;
    min-height: 46px;
    margin: 0;
    padding: 0 44px 0 42px;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 15px;
    color: var(--text-primary);
}
.buscador input::-webkit-search-cancel-button { -webkit-appearance: none; }
.buscador-icono { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); font-size: 15px; opacity: 0.7; pointer-events: none; }
.buscador-limpiar {
    position: absolute; right: 6px; top: 50%; transform: translateY(-50%);
    width: 34px; height: 34px; min-height: 34px; padding: 0;
    border: none; border-radius: 8px; background: var(--bg-hover); color: var(--text-secondary);
    box-shadow: none; font-size: 14px;
}
.btn-ver-orden {
    flex: 0 0 auto;
    display: inline-flex; align-items: center; gap: 8px;
    min-height: 46px; padding: 0 14px;
    background: var(--bg-card); color: var(--text-primary);
    border: 1px solid var(--border); border-radius: 12px;
    font-size: 15px; font-weight: 800; box-shadow: none; white-space: nowrap;
}
.btn-ver-orden:hover { background: var(--bg-hover); border-color: rgba(53,208,127,0.5); }
.pill {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 24px; height: 22px; padding: 0 7px;
    border-radius: 999px; background: var(--accent-primary); color: #0B0D10;
    font-size: 12px; font-weight: 900;
}
.ver-orden-total { color: var(--accent-primary); }
.cat-chips {
    display: flex; gap: 8px; overflow-x: auto;
    padding: 10px 2px 2px; margin: 0 -2px;
    scrollbar-width: thin; scrollbar-color: var(--border) transparent;
    -webkit-overflow-scrolling: touch;
}
.cat-chip {
    flex: 0 0 auto;
    display: inline-flex; align-items: center; gap: 7px;
    min-height: 40px; padding: 0 14px;
    border-radius: 999px; border: 1px solid var(--border);
    background: var(--bg-panel); color: var(--text-secondary);
    font-size: 14px; font-weight: 700; text-decoration: none; white-space: nowrap;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.cat-chip:hover { background: var(--bg-hover); color: var(--text-primary); }
.cat-chip-icono { font-size: 15px; }
.cat-chip .cuenta { font-size: 12px; color: var(--text-muted); font-weight: 800; }
.cat-chip.activo {
    color: var(--text-primary);
    background: var(--cat-tint);
    border-color: var(--cat);
    box-shadow: inset 0 -2px 0 var(--cat);
}
.cat-chip.activo .cuenta { color: var(--cat); }
.cat-chip.sin-coincidencias { opacity: 0.38; }

/* ---------- Secciones de categoria ---------- */
.cat-seccion { margin-top: 22px; scroll-margin-top: calc(var(--header-h) + var(--nav-h) + 12px); }
.cat-head {
    display: flex; align-items: center; gap: 10px;
    margin: 0 0 12px; padding: 2px 0 2px 12px;
    border-left: 4px solid var(--cat);
}
.cat-head h2 { margin: 0; font-size: 19px; font-weight: 800; color: var(--text-primary); letter-spacing: -0.2px; }
.cat-icono { font-size: 18px; }
.cat-count { margin-left: auto; color: var(--text-muted); font-size: 13px; font-weight: 700; }
.grid-productos {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(178px, 1fr));
    gap: 12px;
}

/* ---------- Tarjetas ---------- */
.producto-card {
    display: flex; flex-direction: column;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
    transition: border-color 0.15s ease, background 0.15s ease;
}
.producto-card:hover { border-color: var(--cat-borde); background: var(--bg-hover); }
.producto-card:focus-within { border-color: var(--cat); }
.card-media {
    position: relative;
    aspect-ratio: 16 / 10;
    background: var(--cat-tint);
    border-bottom: 2px solid var(--cat);
    display: flex; align-items: center; justify-content: center;
    overflow: hidden;
}
.card-placeholder { font-size: 40px; line-height: 1; opacity: 0.9; }
.card-media img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.card-badges { position: absolute; top: 8px; left: 8px; right: 8px; display: flex; gap: 4px; flex-wrap: wrap; }
.badge {
    font-size: 11px; font-weight: 800; letter-spacing: 0.4px; text-transform: uppercase;
    padding: 3px 8px; border-radius: 999px;
    background: rgba(11, 13, 16, 0.82); color: var(--text-primary);
    border: 1px solid rgba(255, 255, 255, 0.10);
}
.badge-config { color: var(--cat); }
.badge-agotado { background: var(--danger); color: #fff; border-color: transparent; }
.card-body { display: flex; flex-direction: column; gap: 6px; flex: 1; padding: 10px 12px 12px; }
.card-nombre {
    margin: 0; font-size: 15px; font-weight: 700; line-height: 1.25; color: var(--text-primary);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    min-height: 2.5em; letter-spacing: 0;
}
.card-precio { font-size: 17px; font-weight: 800; color: var(--text-primary); }
.card-acciones { margin-top: auto; display: flex; flex-direction: column; gap: 8px; padding-top: 2px; }
.qty-stepper { display: grid; grid-template-columns: 40px minmax(0, 1fr) 40px; gap: 6px; align-items: center; }
.qty-btn {
    width: 40px; height: 40px; min-height: 40px; padding: 0;
    border-radius: 10px; border: 1px solid var(--border);
    background: var(--bg-panel); color: var(--text-primary);
    font-size: 20px; font-weight: 800; line-height: 1; box-shadow: none;
}
.qty-btn:hover:not(:disabled) { border-color: var(--accent-primary); }
.qty-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.qty-input {
    width: 100%; height: 40px; min-height: 40px; margin: 0; padding: 0 4px;
    border-radius: 10px; border: 1px solid var(--border);
    background: var(--bg-panel); color: var(--text-primary);
    text-align: center; font-size: 16px; font-weight: 800;
    -moz-appearance: textfield; appearance: textfield;
}
.qty-input::-webkit-outer-spin-button, .qty-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.producto-card.qty-modificada .qty-input { border-color: var(--accent-primary); color: var(--accent-primary); }
.btn-add {
    width: 100%; min-height: 44px; margin: 0; padding: 0 10px;
    display: flex; align-items: center; justify-content: center; gap: 6px;
    border: 1px solid var(--accent-primary); border-radius: 10px;
    background: var(--accent-primary); color: #0B0D10;
    font-size: 15px; font-weight: 800; box-shadow: none;
}
.btn-add:hover:not(:disabled) { background: #4BDB8E; }
.btn-add.configurar { background: transparent; color: var(--accent-primary); }
.btn-add.configurar:hover:not(:disabled) { background: rgba(53, 208, 127, 0.12); }
.btn-add:disabled { background: var(--bg-hover); border-color: var(--border); color: var(--text-muted); cursor: not-allowed; }
.btn-add-qty:empty { display: none; }
.btn-add-qty { font-size: 13px; font-weight: 900; padding: 1px 7px; border-radius: 999px; background: rgba(11, 13, 16, 0.18); }
.btn-add.configurar .btn-add-qty { background: rgba(53, 208, 127, 0.18); }
.producto-card.agotado { opacity: 0.6; }
.producto-card.agotado .card-media { filter: grayscale(1); }
.producto-card.agotado:hover { border-color: var(--border); background: var(--bg-card); }

.sin-resultados { margin: 28px 0; padding: 28px 16px; text-align: center; color: var(--text-secondary); border: 1px dashed var(--border); border-radius: 14px; }
.info-cierre { background: #2A2417; border: 1px solid var(--accent-secondary); padding: 12px 14px; border-radius: 12px; margin: 14px 0 4px; color: #F8D083; font-weight: 600; }
.info-cierre.info-neutra { background: var(--bg-panel); border-color: var(--border); color: var(--text-secondary); }

/* ---------- Resumen ---------- */
.resumen {
    position: sticky;
    top: calc(var(--header-h) + 14px);
    margin-top: 14px;
    max-height: calc(100vh - var(--header-h) - 28px);
    display: flex; flex-direction: column;
    background: var(--bg-panel);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.38);
    overflow: hidden;
    outline: none;
}
.resumen.destacar { animation: destacar-resumen 0.9s ease-out; }
@keyframes destacar-resumen {
    0% { box-shadow: 0 0 0 0 rgba(53, 208, 127, 0.65), 0 14px 34px rgba(0, 0, 0, 0.38); }
    100% { box-shadow: 0 0 0 14px rgba(53, 208, 127, 0), 0 14px 34px rgba(0, 0, 0, 0.38); }
}
.resumen-head { padding: 14px 16px 12px; border-bottom: 1px solid var(--border); }
.resumen-titulo { display: flex; align-items: center; gap: 10px; }
.resumen-titulo h2 { margin: 0; font-size: 20px; font-weight: 900; color: var(--text-primary); flex: 1; min-width: 0; }
.estado-pill { padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.4px; white-space: nowrap; border: 1px solid; }
.estado-abierta { color: var(--info); border-color: rgba(77, 163, 255, 0.45); background: rgba(77, 163, 255, 0.12); }
.estado-cocina { color: var(--warning); border-color: rgba(242, 185, 75, 0.45); background: rgba(242, 185, 75, 0.12); }
.estado-listo { color: var(--success); border-color: rgba(53, 208, 127, 0.45); background: rgba(53, 208, 127, 0.12); }
.estado-cerrada { color: var(--text-secondary); border-color: var(--border); background: var(--bg-card); }
.resumen-cerrar { display: none; width: 40px; height: 40px; min-height: 40px; padding: 0; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-card); color: var(--text-primary); box-shadow: none; }
.resumen-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.meta-chip { padding: 5px 10px; border-radius: 8px; background: var(--bg-card); border: 1px solid var(--border); color: var(--text-primary); font-size: 13px; font-weight: 700; }
.acciones-superiores { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.acciones-superiores form { margin: 0; flex: 1 1 auto; display: flex; }
.resumen-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 12px 16px 16px; }
.info-orden { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; margin: 0; font-size: 14px; }
.info-orden dt { color: var(--text-muted); font-weight: 700; }
.info-orden dd { margin: 0; color: var(--text-primary); overflow-wrap: anywhere; }
.seccion-titulo {
    display: flex; justify-content: space-between; align-items: center;
    margin: 18px 0 6px; font-size: 12px; font-weight: 800;
    text-transform: uppercase; letter-spacing: 0.6px; color: var(--text-muted);
}
.item-orden { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border); align-items: start; }
.item-cant {
    min-width: 36px; height: 28px; padding: 0 6px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 8px; background: rgba(53, 208, 127, 0.12); color: var(--accent-primary);
    font-weight: 900; font-size: 14px;
}
.item-nombre { font-weight: 700; font-size: 15px; color: var(--text-primary); overflow-wrap: anywhere; }
.item-unit { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
.item-indicacion { color: var(--accent-secondary); font-size: 13px; margin-top: 4px; font-weight: 700; }
.item-descripcion { color: var(--text-secondary); font-size: 13px; margin-top: 4px; font-weight: 600; line-height: 1.4; white-space: pre-line; border-left: 2px solid var(--accent-primary); padding-left: 8px; }
.item-derecha { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.item-subtotal { font-weight: 800; font-size: 15px; white-space: nowrap; }
.acciones-item { display: flex; gap: 6px; }
.acciones-item form { margin: 0; }
.btn-item {
    width: 36px; height: 36px; min-height: 36px; padding: 0;
    border-radius: 9px; border: 1px solid var(--border);
    background: var(--bg-card); color: var(--text-secondary);
    font-size: 14px; box-shadow: none;
}
.btn-item:hover { border-color: var(--info); color: var(--text-primary); }
.btn-item.peligro:hover { border-color: var(--danger); color: var(--danger); }
.resumen-vacio { text-align: center; padding: 26px 8px; color: var(--text-muted); line-height: 1.5; }
.resumen-vacio-icono { font-size: 30px; margin-bottom: 6px; opacity: 0.8; }
.resumen-footer { border-top: 1px solid var(--border); padding: 12px 16px 14px; background: #12151C; }
.total { margin: 0; font-size: 26px; font-weight: 900; letter-spacing: -0.4px; color: var(--text-primary); }
.total-cliente { color: var(--accent-primary); }
.total-bs { margin: 2px 0 12px; color: var(--text-secondary); font-size: 15px; font-weight: 700; }
.acciones-primarias { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.acciones-primarias:empty { display: none; }
.btn-accion { margin: 0; padding: 10px 12px; min-height: 48px; border-radius: 12px; font-size: 15px; font-weight: 800; box-shadow: none; text-align: center; }
.btn-accion.cobrar { background: var(--accent-primary); color: #0B0D10; }
.btn-accion.cobrar:hover { background: #4BDB8E; }
.btn-accion.cocina { background: var(--accent-secondary); color: #0B0D10; }
.btn-accion.cocina:hover { background: #F6C766; }
.btn-accion.pendiente { background: #FF8A4C; color: #0B0D10; }
.btn-accion.ancho { grid-column: 1 / -1; }
.btn-sec { background: var(--bg-card); border: 1px solid var(--border); color: var(--text-primary); min-height: 44px; font-size: 14px; }
.btn-sec:hover { background: var(--bg-hover); }
.btn-sec.peligro { color: var(--danger-text); border-color: rgba(239, 68, 68, 0.45); background: rgba(239, 68, 68, 0.08); }
.btn-mini { width: 100%; min-height: 40px; padding: 6px 10px; font-size: 13px; flex: 1 1 auto; }
.acciones-superiores > a.btn-mini, .acciones-superiores > div.btn-mini { width: auto; }
.acciones-secundarias { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.acciones-secundarias .volver { box-shadow: none; }

/* Delivery / paneles compartidos dentro del resumen */
.btn { width: 100%; padding: 12px; margin: 6px 0; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: 10px; font-weight: 800; font-size: 14px; min-height: 44px; box-shadow: none; }
.btn:hover { background: var(--bg-hover); border-color: rgba(53, 208, 127, 0.45); }
.resumen-body label { display: block; color: var(--text-muted); font-size: 12px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; margin-top: 6px; }
.delivery-panel { border: 1px solid var(--border); background: var(--bg-card); border-radius: 12px; padding: 12px 14px; margin: 14px 0; }
.delivery-panel h3 { margin: 0 0 6px; font-size: 15px; color: var(--text-primary); }
details.delivery-panel > summary { list-style: none; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 10px; min-height: 28px; font-weight: 800; font-size: 15px; }
details.delivery-panel > summary::-webkit-details-marker { display: none; }
details.delivery-panel > summary::after { content: "▾"; color: var(--text-muted); margin-left: 4px; }
details.delivery-panel[open] > summary { margin-bottom: 8px; }
details.delivery-panel[open] > summary::after { content: "▴"; }
.delivery-resumen { margin-left: auto; color: var(--text-secondary); font-size: 13px; font-weight: 700; }
.delivery-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; margin: 6px 0; }
.delivery-monto-btn { min-height: 42px; padding: 0; border: 1px solid var(--border); border-radius: 9px; background: var(--bg-panel); color: var(--text-primary); font-weight: 900; box-shadow: none; }
.delivery-monto-btn.activo { background: var(--accent-primary); color: #0B0D10; border-color: var(--accent-primary); }
.delivery-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 4px; }
.delivery-help { color: var(--text-secondary); font-size: 13px; margin: 6px 0; display: block; }
.delivery-alerta { background: #3b2b12; color: #fde68a; border: 1px solid #92400e; border-radius: 8px; padding: 10px; margin: 8px 0; }
.delivery-nuevo { display: none; margin-top: 10px; border-top: 1px solid var(--border); padding-top: 10px; }
.delivery-nuevo.activo { display: block; }
.self-order-panel { border: 1px solid var(--border); background: var(--bg-card); border-radius: 12px; padding: 12px 14px; margin: 14px 0; }
.self-order-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.self-order-head h3 { margin: 0 0 4px; font-size: 15px; }
.self-order-head p { margin: 0; color: var(--text-secondary); font-size: 13px; }
.self-order-pill { border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 900; white-space: nowrap; }
.self-order-pill.activo { background: rgba(53, 208, 127, 0.16); color: var(--accent-primary); border: 1px solid rgba(53, 208, 127, 0.4); }
.self-order-pill.inactivo { background: var(--bg-hover); color: var(--text-secondary); border: 1px solid var(--border); }
.self-order-qr { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 12px; margin-top: 12px; align-items: start; }
.self-order-qr img { width: 120px; height: 120px; background: white; border-radius: 8px; padding: 6px; box-sizing: border-box; }
.self-order-info label { display: block; color: var(--text-muted); font-size: 12px; font-weight: 900; margin: 4px 0; text-transform: uppercase; }
.self-order-info input { width: 100%; box-sizing: border-box; margin-bottom: 8px; }
.self-order-info code { display: block; overflow-wrap: anywhere; background: var(--bg-main); border: 1px solid var(--border); border-radius: 8px; padding: 8px; color: var(--accent-primary); font-size: 12px; }
.self-order-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; }
.self-order-action { margin-top: 12px; }
.self-order-revocar { background: #4A1E23; color: #fecaca; }

/* ---------- Modales de configuracion (combos, promos, refrescos, modificadores) ---------- */
.modal-refresco { position: fixed; inset: 0; background: rgba(5, 7, 10, 0.7); display: none; align-items: center; justify-content: center; padding: 18px; z-index: 1000; }
.modal-refresco.activo { display: flex; }
.modal-contenido { width: min(620px, 100%); max-height: 85vh; overflow-y: auto; background: var(--bg-panel); color: var(--text-primary); border: 1px solid var(--border); border-radius: 16px; padding: 18px; box-shadow: 0 24px 50px rgba(0, 0, 0, 0.5); }
.modal-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 14px; }
.modal-top h2 { margin: 0; color: var(--accent-primary); font-size: 20px; }
.modal-top p { margin: 5px 0 0; color: var(--text-secondary); }
.cerrar-modal { width: 44px; min-height: 44px; padding: 0; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-card); color: var(--text-primary); font-weight: 800; box-shadow: none; }
.sabores-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.sabor-btn { min-height: 64px; padding: 12px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-card); color: var(--text-primary); font-size: 16px; font-weight: 800; text-align: center; display: flex; align-items: center; justify-content: center; box-shadow: none; transition: background 0.15s ease, border-color 0.15s ease; }
.sabor-btn:hover:not(:disabled) { background: var(--bg-hover); border-color: rgba(53, 208, 127, 0.5); }
.sabor-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.sabor-btn.activo { background: rgba(53, 208, 127, 0.18); border-color: var(--accent-primary); color: var(--accent-primary); }
.sabor-coca-cola { background: #B91C1C; border-color: #B91C1C; color: #fff; }
.sabor-chinotto { background: #0B0D10; }
.sabor-frescolita { background: #DC2626; border-color: #DC2626; color: #fff; }
.sabor-naranja { background: #F97316; border-color: #F97316; color: #1c1917; }
.sabor-uva { background: #6A0DAD; border-color: #6A0DAD; color: #fff; }
.sabor-btn.otro { background: #5B21B6; border-color: #5B21B6; color: #fff; }
.sabor-btn.opcion-omitir { background: transparent; border-style: dashed; color: var(--text-secondary); }
.combo-config { display: grid; grid-template-columns: 1fr; gap: 12px; }
.combo-config-seccion { margin: 0; }
.combo-config-seccion label { display: block; margin: 0 0 6px; color: var(--text-secondary); font-size: 13px; font-weight: 800; letter-spacing: 0.3px; text-transform: uppercase; }
.combo-select { width: 100%; min-height: 50px; padding: 11px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-card); color: var(--text-primary); font-size: 16px; font-weight: 800; box-sizing: border-box; }
.combo-select:focus { outline: none; border-color: var(--accent-primary); box-shadow: 0 0 0 3px rgba(53, 208, 127, 0.15); }
.extra-lumpia-opciones { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.extra-lumpia-btn { min-height: 50px; padding: 11px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--bg-card); color: var(--text-primary); font-size: 15px; font-weight: 900; box-shadow: none; }
.extra-lumpia-btn:hover { background: var(--bg-hover); }
.extra-lumpia-btn.activo { background: var(--accent-primary); color: #0B0D10; border-color: var(--accent-primary); }
.combo-aceptar { width: 100%; margin-top: 4px; background: var(--accent-primary); color: #0B0D10; border-color: var(--accent-primary); position: sticky; bottom: 0; }
.combo-aceptar:hover:not(:disabled) { background: #4BDB8E; color: #0B0D10; }
.sabores-grid .combo-aceptar { grid-column: 1 / -1; }

/* ---------- Movil: FAB + bottom sheet ---------- */
.fab-orden {
    display: none;
    position: fixed; left: 12px; right: 12px;
    bottom: calc(12px + env(safe-area-inset-bottom, 0px));
    z-index: 50;
    min-height: 56px; padding: 0 18px;
    align-items: center; justify-content: space-between; gap: 10px;
    border: none; border-radius: 14px;
    background: var(--accent-primary); color: #0B0D10;
    font-size: 16px; font-weight: 900;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5);
}
.fab-orden .pill { background: #0B0D10; color: var(--accent-primary); }
.resumen-backdrop { position: fixed; inset: 0; background: rgba(5, 7, 10, 0.6); z-index: 55; opacity: 0; pointer-events: none; transition: opacity 0.2s ease; }
.resumen-backdrop.activo { opacity: 1; pointer-events: auto; }
.toast-orden {
    position: fixed; left: 50%; bottom: 24px; z-index: 70;
    transform: translate(-50%, 20px); opacity: 0; pointer-events: none;
    max-width: calc(100vw - 32px);
    padding: 12px 16px; border-radius: 12px;
    background: #0B0D10; color: var(--text-primary);
    border: 1px solid var(--accent-primary);
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5);
    font-weight: 800; font-size: 14px;
    transition: opacity 0.2s ease, transform 0.2s ease;
}
.toast-orden.visible { opacity: 1; transform: translate(-50%, 0); }

/* Header compartido (barra_superior) mas bajo en esta pantalla: es sticky
   y cada pixel cuenta durante la toma de ordenes. Sus estilos de columna
   son inline, de ahi el !important. */
.pagina-orden .header { padding: 8px 20px; }
.pagina-orden .header > div:last-child { flex-direction: row !important; align-items: center !important; gap: 12px !important; }
.pagina-orden .titulo { font-size: 21px; }
@media (max-width: 860px) {
    .pagina-orden .header { padding: 8px 12px; gap: 6px; }
    .pagina-orden .header > div:last-child { justify-content: space-between; }
    .pagina-orden .menu-top a { flex: 0 0 auto; }
}
@media (max-width: 1180px) {
    .orden-app { grid-template-columns: minmax(0, 1fr) 340px; gap: 14px; padding: 4px 14px 24px; }
    .grid-productos { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
    .acciones-primarias .btn-accion { font-size: 14px; padding: 10px 6px; }
}
@media (max-width: 860px) {
    .orden-app { grid-template-columns: minmax(0, 1fr); padding: 0 12px 96px; gap: 0; }
    .catalogo-nav { padding-top: 10px; }
    .ver-orden-texto, .ver-orden-total { display: none; }
    .btn-ver-orden { padding: 0 12px; }
    .resumen {
        position: fixed; left: 0; right: 0; bottom: 0; top: auto;
        margin: 0; max-height: 90vh; max-height: 90dvh;
        border-radius: 18px 18px 0 0; border-bottom: none;
        z-index: 60;
        transform: translateY(105%); visibility: hidden;
        transition: transform 0.22s ease, visibility 0s linear 0.22s;
    }
    .resumen.abierto { transform: none; visibility: visible; transition: transform 0.22s ease, visibility 0s; }
    .resumen-cerrar { display: inline-flex; align-items: center; justify-content: center; }
    .resumen-footer { padding-bottom: calc(14px + env(safe-area-inset-bottom, 0px)); }
    .fab-orden { display: flex; }
    body.resumen-abierto { overflow: hidden; }
    .toast-orden { bottom: calc(84px + env(safe-area-inset-bottom, 0px)); }
    body.sin-catalogo .orden-app { padding-bottom: 24px; }
    body.sin-catalogo .resumen {
        position: static; transform: none; visibility: visible;
        max-height: none; border-radius: 16px; border-bottom: 1px solid var(--border); margin-top: 12px;
    }
    body.sin-catalogo .resumen-cerrar { display: none; }
    .sabores-grid { grid-template-columns: 1fr 1fr; }
    .extra-lumpia-opciones { grid-template-columns: 1fr; }
    .delivery-grid { grid-template-columns: repeat(4, 1fr); }
    .self-order-qr, .self-order-actions { grid-template-columns: 1fr; }
    .self-order-qr img { width: 160px; height: 160px; }
    .modal-refresco { padding: 12px; }
    .modal-contenido { width: calc(100% - 8px); padding: 14px; }
}
@media (max-width: 480px) {
    .grid-productos { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .card-body { padding: 8px 9px 10px; }
    .card-nombre { font-size: 14px; }
    .card-precio { font-size: 16px; }
    .card-placeholder { font-size: 34px; }
    .qty-stepper { grid-template-columns: 36px minmax(0, 1fr) 36px; gap: 4px; }
    .qty-btn { width: 36px; height: 36px; min-height: 36px; }
    .qty-input { height: 36px; min-height: 36px; }
    .cat-head h2 { font-size: 17px; }
}
@media (prefers-reduced-motion: reduce) {
    .resumen, .toast-orden, .resumen-backdrop, .cat-chip, .producto-card { transition: none !important; }
    .resumen.destacar { animation: none; }
}
"""


# ----------------------------------------------------------------------
# JS. _JS_ORDEN_LEGACY es el JS de agregado/configuracion/delivery/self-
# ordering previo al rediseno, con dos cambios mecanicos: el stepper de
# cantidad ahora sincroniza estado visual, y las navegaciones de agregado
# pasan por navegarAgregar() (guarda scroll para volver al mismo punto).
# ----------------------------------------------------------------------
_JS_ORDEN_PRE = """
    const ORDEN_ID = document.body.dataset.ordenId;
    const MAX_CANTIDAD = parseInt(document.body.dataset.maxCantidad, 10) || 1;
    const CLAVE_VISTA = "nekoOrdenVista:" + ORDEN_ID;
    let productoEnCurso = "";

    document.addEventListener("click", function(event) {
        const tarjeta = event.target.closest(".producto-card");
        if (tarjeta) {
            productoEnCurso = tarjeta.dataset.nombre || "";
        }
    }, true);

    function navegarAgregar(url) {
        try {
            const destino = new URL(url, window.location.origin);
            sessionStorage.setItem(CLAVE_VISTA, JSON.stringify({
                y: window.scrollY,
                t: Date.now(),
                items: parseInt(document.body.dataset.items, 10) || 0,
                nombre: productoEnCurso,
                cantidad: parseInt(destino.searchParams.get("cantidad"), 10) || 1
            }));
        } catch (error) {}
        window.location.href = url;
    }
"""


_JS_ORDEN_POST = """
    (function() {
        const raiz = document.body;
        const header = document.querySelector(".header");
        const nav = document.getElementById("catalogoNav");
        const chipsNav = document.getElementById("catChips");
        const chips = Array.from(document.querySelectorAll(".cat-chip"));
        const secciones = Array.from(document.querySelectorAll(".cat-seccion"));
        const tarjetas = Array.from(document.querySelectorAll(".producto-card"));
        const buscador = document.getElementById("buscarProducto");
        const limpiar = document.getElementById("limpiarBusqueda");
        const sinResultados = document.getElementById("sinResultados");
        const sinResultadosTexto = document.getElementById("sinResultadosTexto");
        const resumen = document.getElementById("ordenResumen");
        const backdrop = document.getElementById("resumenBackdrop");
        const cerrarResumenBtn = document.getElementById("cerrarResumen");
        const toast = document.getElementById("toastOrden");
        const movil = window.matchMedia("(max-width: 860px)");
        const sinMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)");

        function medir() {
            let alturaHeader = 0;
            if (header && getComputedStyle(header).position === "sticky") {
                alturaHeader = header.offsetHeight;
            }
            raiz.style.setProperty("--header-h", alturaHeader + "px");
            raiz.style.setProperty("--nav-h", (nav ? nav.offsetHeight : 0) + "px");
        }
        medir();
        window.addEventListener("resize", medir);

        function desplazamiento() {
            const estilos = getComputedStyle(raiz);
            return (parseInt(estilos.getPropertyValue("--header-h"), 10) || 0)
                + (parseInt(estilos.getPropertyValue("--nav-h"), 10) || 0) + 16;
        }

        /* ---- Chips de categoria: salto + categoria activa ---- */
        let bloqueoSpyHasta = 0;
        function marcarChip(id) {
            chips.forEach(function(chip) {
                const activo = chip.dataset.target === id;
                chip.classList.toggle("activo", activo);
                if (activo) {
                    chip.setAttribute("aria-current", "true");
                    if (chipsNav) {
                        const izquierda = chip.offsetLeft - (chipsNav.clientWidth - chip.offsetWidth) / 2;
                        chipsNav.scrollTo({ left: Math.max(0, izquierda), behavior: sinMovimiento.matches ? "auto" : "smooth" });
                    }
                } else {
                    chip.removeAttribute("aria-current");
                }
            });
        }

        function actualizarChipActivo() {
            if (Date.now() < bloqueoSpyHasta) {
                return;
            }
            const visibles = secciones.filter(function(seccion) { return !seccion.hidden; });
            if (!visibles.length) {
                return;
            }
            const limite = desplazamiento();
            let actual = visibles[0];
            visibles.forEach(function(seccion) {
                if (seccion.getBoundingClientRect().top <= limite) {
                    actual = seccion;
                }
            });
            if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) {
                actual = visibles[visibles.length - 1];
            }
            const chipActual = chips.find(function(chip) { return chip.classList.contains("activo"); });
            if (!chipActual || chipActual.dataset.target !== actual.id) {
                marcarChip(actual.id);
            }
        }

        let spyPendiente = false;
        window.addEventListener("scroll", function() {
            if (spyPendiente) {
                return;
            }
            spyPendiente = true;
            window.requestAnimationFrame(function() {
                spyPendiente = false;
                actualizarChipActivo();
            });
        }, { passive: true });

        chips.forEach(function(chip) {
            chip.addEventListener("click", function(event) {
                event.preventDefault();
                const seccion = document.getElementById(chip.dataset.target);
                if (!seccion) {
                    return;
                }
                if (seccion.hidden) {
                    limpiarBusqueda();
                }
                marcarChip(seccion.id);
                bloqueoSpyHasta = Date.now() + 700;
                seccion.scrollIntoView({ behavior: sinMovimiento.matches ? "auto" : "smooth", block: "start" });
            });
        });

        /* ---- Buscador (filtro local sobre las tarjetas ya renderizadas) ---- */
        function normalizar(texto) {
            return (texto || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "").toLowerCase().trim();
        }
        tarjetas.forEach(function(tarjeta) {
            tarjeta._textoBusqueda = normalizar((tarjeta.dataset.nombre || "") + " " + (tarjeta.dataset.categoria || ""));
        });

        function filtrar() {
            if (!buscador) {
                return;
            }
            const consulta = normalizar(buscador.value);
            const terminos = consulta.split(/\\s+/).filter(Boolean);
            let totalVisibles = 0;
            secciones.forEach(function(seccion) {
                let visibles = 0;
                seccion.querySelectorAll(".producto-card").forEach(function(tarjeta) {
                    const coincide = terminos.every(function(t) { return tarjeta._textoBusqueda.indexOf(t) !== -1; });
                    tarjeta.hidden = !coincide;
                    if (coincide) visibles += 1;
                });
                seccion.hidden = visibles === 0;
                totalVisibles += visibles;
                const chip = chips.find(function(c) { return c.dataset.target === seccion.id; });
                if (chip) {
                    chip.classList.toggle("sin-coincidencias", visibles === 0);
                }
            });
            if (limpiar) limpiar.hidden = !consulta;
            if (sinResultados) {
                sinResultados.hidden = !consulta || totalVisibles > 0;
                if (sinResultadosTexto) sinResultadosTexto.textContent = buscador.value.trim();
            }
            actualizarChipActivo();
        }

        function limpiarBusqueda() {
            if (!buscador) {
                return;
            }
            buscador.value = "";
            filtrar();
        }

        if (buscador) {
            buscador.addEventListener("input", function() {
                filtrar();
                const primera = secciones.find(function(s) { return !s.hidden; });
                if (buscador.value.trim() && primera && nav) {
                    const tope = nav.getBoundingClientRect().bottom;
                    if (primera.getBoundingClientRect().top < tope) {
                        primera.scrollIntoView({ block: "start" });
                    }
                }
            });
            buscador.addEventListener("keydown", function(event) {
                if (event.key === "Escape") {
                    limpiarBusqueda();
                    buscador.blur();
                } else if (event.key === "Enter") {
                    event.preventDefault();
                    const visibles = tarjetas.filter(function(t) { return !t.hidden; });
                    if (visibles.length === 1) {
                        const boton = visibles[0].querySelector(".btn-add");
                        if (boton && !boton.disabled) boton.click();
                    }
                }
            });
        }
        if (limpiar) {
            limpiar.addEventListener("click", function() {
                limpiarBusqueda();
                if (buscador) buscador.focus();
            });
        }
        document.addEventListener("keydown", function(event) {
            if (event.key !== "/" || !buscador) {
                return;
            }
            const activo = document.activeElement;
            if (activo && (activo.tagName === "INPUT" || activo.tagName === "TEXTAREA" || activo.tagName === "SELECT")) {
                return;
            }
            if (document.querySelector(".modal-refresco.activo")) {
                return;
            }
            event.preventDefault();
            buscador.focus();
        });

        /* ---- Ver orden: resaltar en desktop, bottom sheet en movil ---- */
        function usaDrawer() {
            return movil.matches && !raiz.classList.contains("sin-catalogo");
        }
        function abrirResumen() {
            if (!resumen) {
                return;
            }
            if (usaDrawer()) {
                resumen.classList.add("abierto");
                if (backdrop) backdrop.classList.add("activo");
                raiz.classList.add("resumen-abierto");
                resumen.focus({ preventScroll: true });
                return;
            }
            const caja = resumen.getBoundingClientRect();
            if (caja.top < 0 || caja.top > window.innerHeight - 80) {
                resumen.scrollIntoView({ behavior: sinMovimiento.matches ? "auto" : "smooth", block: "start" });
            }
            resumen.classList.remove("destacar");
            void resumen.offsetWidth;
            resumen.classList.add("destacar");
            resumen.focus({ preventScroll: true });
        }
        function cerrarResumen() {
            if (!resumen) {
                return;
            }
            resumen.classList.remove("abierto");
            if (backdrop) backdrop.classList.remove("activo");
            raiz.classList.remove("resumen-abierto");
        }
        ["btnVerOrden", "fabOrden"].forEach(function(id) {
            const boton = document.getElementById(id);
            if (boton) boton.addEventListener("click", abrirResumen);
        });
        if (cerrarResumenBtn) cerrarResumenBtn.addEventListener("click", cerrarResumen);
        if (backdrop) backdrop.addEventListener("click", cerrarResumen);
        movil.addEventListener && movil.addEventListener("change", function() {
            if (!movil.matches) cerrarResumen();
            medir();
        });

        document.addEventListener("keydown", function(event) {
            if (event.key !== "Escape") {
                return;
            }
            if (modalConfiguracion.classList.contains("activo")) {
                cerrarConfiguracion();
            } else if (modalRefresco.classList.contains("activo")) {
                cerrarSelectorRefresco();
            } else if (resumen && resumen.classList.contains("abierto")) {
                cerrarResumen();
            }
        });

        /* ---- Volver al mismo punto tras agregar + confirmacion ---- */
        function mostrarToast(texto) {
            if (!toast) {
                return;
            }
            toast.textContent = texto;
            toast.classList.add("visible");
            window.setTimeout(function() { toast.classList.remove("visible"); }, 2600);
        }
        try {
            const guardado = JSON.parse(sessionStorage.getItem(CLAVE_VISTA) || "null");
            sessionStorage.removeItem(CLAVE_VISTA);
            if (guardado && Date.now() - guardado.t < 60000) {
                window.scrollTo(0, guardado.y || 0);
                const itemsAhora = parseInt(raiz.dataset.items, 10) || 0;
                if (itemsAhora > guardado.items && guardado.nombre) {
                    mostrarToast("✓ Añadido: " + (guardado.cantidad || 1) + "× " + guardado.nombre);
                }
            }
        } catch (error) {}

        actualizarChipActivo();
    })();
"""


_JS_ORDEN_LEGACY = """
    function pedirClaveSupervisor() {
        const clave = prompt("Clave de supervisor");
        if (clave === null) {
            return null;
        }
        return clave.trim();
    }

    const selfOrderPanel = document.getElementById("selfOrderPanel");
    const selfOrderMensaje = document.getElementById("selfOrderMensaje");
    function setSelfOrderMensaje(texto) {
        if (selfOrderMensaje) {
            selfOrderMensaje.textContent = texto || "";
        }
    }
    async function postSelfOrder(url) {
        const response = await fetch(url, { method: "POST", headers: { "Accept": "application/json" } });
        if (!response.ok) {
            let mensaje = "No se pudo completar la operacion.";
            try {
                const data = await response.json();
                if (data.error) mensaje = data.error;
            } catch (error) {}
            throw new Error(mensaje);
        }
        return response.json();
    }
    const generarSelfOrder = document.getElementById("generarSelfOrder");
    if (generarSelfOrder && selfOrderPanel) {
        generarSelfOrder.addEventListener("click", async function() {
            generarSelfOrder.disabled = true;
            setSelfOrderMensaje("Generando QR...");
            try {
                await postSelfOrder(`/orden/${selfOrderPanel.dataset.ordenId}/self-ordering/link`);
                window.location.reload();
            } catch (error) {
                generarSelfOrder.disabled = false;
                setSelfOrderMensaje(error.message);
            }
        });
    }
    const revocarSelfOrder = document.getElementById("revocarSelfOrder");
    if (revocarSelfOrder && selfOrderPanel) {
        revocarSelfOrder.addEventListener("click", async function() {
            if (!confirm("Revocar el QR de autoservicio de esta mesa?")) return;
            revocarSelfOrder.disabled = true;
            setSelfOrderMensaje("Revocando QR...");
            try {
                await postSelfOrder(`/orden/${selfOrderPanel.dataset.ordenId}/self-ordering/link/${selfOrderPanel.dataset.linkId}/revocar`);
                window.location.reload();
            } catch (error) {
                revocarSelfOrder.disabled = false;
                setSelfOrderMensaje(error.message);
            }
        });
    }
    const copiarSelfOrder = document.getElementById("copiarSelfOrder");
    if (copiarSelfOrder) {
        copiarSelfOrder.addEventListener("click", async function() {
            const input = document.getElementById("selfOrderUrl");
            if (!input) return;
            try {
                await navigator.clipboard.writeText(input.value);
                setSelfOrderMensaje("Link copiado.");
            } catch (error) {
                input.select();
                document.execCommand("copy");
                setSelfOrderMensaje("Link copiado.");
            }
        });
    }

    const saboresRefresco = ["Coca Cola", "Chinotto", "Frescolita", "Naranja", "Uva", "Manzana", "7Up", "Pepsi", "Otro"];
    const modalRefresco = document.getElementById("modal-refresco");
    const modalRefrescoProducto = document.getElementById("modal-refresco-producto");
    const saboresRefrescoGrid = document.getElementById("sabores-refresco-grid");
    const cerrarModalRefresco = document.getElementById("cerrar-modal-refresco");
    let refrescoSeleccionadoUrl = "";
    let refrescoSeleccionadoCantidad = 1;

    function obtenerCantidadDesdeBoton(btn) {
        const contenedor = btn.closest(".producto-item");
        const input = contenedor ? contenedor.querySelector(".qty-input") : null;
        let valor = input ? parseInt(input.value, 10) : 1;
        if (!valor || valor < 1) {
            valor = 1;
        }
        if (valor > MAX_CANTIDAD) {
            valor = MAX_CANTIDAD;
        }
        return valor;
    }

    document.querySelectorAll(".producto-item").forEach(function(item) {
        const input = item.querySelector(".qty-input");
        if (!input) {
            return;
        }
        const dec = item.querySelector(".qty-dec");
        const inc = item.querySelector(".qty-inc");
        const boton = item.querySelector(".btn-add");
        const etiquetaQty = item.querySelector(".btn-add-qty");
        const agotado = item.classList.contains("agotado");

        function fijarCantidad(valor) {
            let cantidad = parseInt(valor, 10);
            if (!cantidad || cantidad < 1) {
                cantidad = 1;
            }
            if (cantidad > MAX_CANTIDAD) {
                cantidad = MAX_CANTIDAD;
            }
            input.value = cantidad;
            if (!agotado) {
                if (dec) dec.disabled = cantidad <= 1;
                if (inc) inc.disabled = cantidad >= MAX_CANTIDAD;
            }
            item.classList.toggle("qty-modificada", cantidad > 1);
            if (etiquetaQty) {
                etiquetaQty.textContent = cantidad > 1 ? "×" + cantidad : "";
            }
        }

        if (dec) {
            dec.addEventListener("click", function() {
                fijarCantidad((parseInt(input.value, 10) || 1) - 1);
            });
        }
        if (inc) {
            inc.addEventListener("click", function() {
                fijarCantidad((parseInt(input.value, 10) || 1) + 1);
            });
        }
        input.addEventListener("input", function() {
            const valor = parseInt(input.value, 10);
            if (valor > MAX_CANTIDAD) {
                fijarCantidad(MAX_CANTIDAD);
            }
        });
        input.addEventListener("change", function() { fijarCantidad(input.value); });
        input.addEventListener("blur", function() { fijarCantidad(input.value); });
        input.addEventListener("focus", function() { input.select(); });
        input.addEventListener("keydown", function(event) {
            if (event.key === "Enter") {
                event.preventDefault();
                fijarCantidad(input.value);
                if (boton && !boton.disabled) {
                    boton.click();
                }
            }
        });
        if (!agotado) {
            fijarCantidad(input.value);
        }
    });

    document.querySelectorAll(".btn-simple").forEach(function(btn) {
        btn.addEventListener("click", function() {
            const cantidad = obtenerCantidadDesdeBoton(btn);
            navegarAgregar(btn.dataset.url + "?cantidad=" + cantidad);
        });
    });
    const deliveryMonto = document.getElementById("delivery_usd");
    const deliveryRepartidor = document.getElementById("delivery_repartidor_id");
    const nuevoRepartidorPanel = document.getElementById("nuevoRepartidorPanel");
    const mostrarNuevoRepartidor = document.getElementById("mostrarNuevoRepartidor");
    const guardarNuevoRepartidor = document.getElementById("guardarNuevoRepartidor");
    const nuevoRepartidorNombre = document.getElementById("nuevoRepartidorNombre");
    const nuevoRepartidorTelefono = document.getElementById("nuevoRepartidorTelefono");
    const nuevoRepartidorMensaje = document.getElementById("nuevoRepartidorMensaje");

    document.querySelectorAll(".delivery-monto-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            if (!deliveryMonto || deliveryMonto.disabled) {
                return;
            }
            deliveryMonto.value = btn.dataset.deliveryMonto;
            document.querySelectorAll(".delivery-monto-btn").forEach(function(opcion) {
                opcion.classList.toggle("activo", opcion === btn);
            });
        });
    });

    if (mostrarNuevoRepartidor && nuevoRepartidorPanel) {
        mostrarNuevoRepartidor.addEventListener("click", function() {
            nuevoRepartidorPanel.classList.toggle("activo");
            if (nuevoRepartidorPanel.classList.contains("activo") && nuevoRepartidorNombre) {
                nuevoRepartidorNombre.focus();
            }
        });
    }

    if (guardarNuevoRepartidor) {
        guardarNuevoRepartidor.addEventListener("click", function() {
            const nombre = (nuevoRepartidorNombre.value || "").trim();
            const telefono = (nuevoRepartidorTelefono.value || "").trim();
            if (!nombre) {
                nuevoRepartidorMensaje.textContent = "El nombre es obligatorio.";
                nuevoRepartidorNombre.focus();
                return;
            }
            fetch("/api/repartidores", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({nombre: nombre, telefono: telefono})
            })
            .then(function(response) { return response.json().then(function(data) { return {status: response.status, data: data}; }); })
            .then(function(result) {
                if (!result.data.ok) {
                    nuevoRepartidorMensaje.textContent = result.data.error || "No se pudo crear el repartidor.";
                    return;
                }
                const rep = result.data.repartidor;
                const option = document.createElement("option");
                option.value = String(rep.id);
                option.textContent = rep.nombre;
                option.selected = true;
                deliveryRepartidor.appendChild(option);
                nuevoRepartidorNombre.value = "";
                nuevoRepartidorTelefono.value = "";
                nuevoRepartidorMensaje.textContent = "Repartidor creado y seleccionado.";
                nuevoRepartidorPanel.classList.remove("activo");
            })
            .catch(function() {
                nuevoRepartidorMensaje.textContent = "No se pudo crear el repartidor.";
            });
        });
    }

    function cerrarSelectorRefresco() {
        refrescoSeleccionadoUrl = "";
        modalRefresco.classList.remove("activo");
        modalRefresco.setAttribute("aria-hidden", "true");
    }

    function agregarRefrescoConSabor(sabor) {
        const saborLimpio = (sabor || "").trim();
        if (!saborLimpio || !refrescoSeleccionadoUrl) {
            return;
        }
        navegarAgregar(refrescoSeleccionadoUrl + "?sabor=" + encodeURIComponent(saborLimpio) + "&cantidad=" + refrescoSeleccionadoCantidad);
    }

    function claseSaborRefresco(sabor) {
        const clases = {
            "Coca Cola": "sabor-coca-cola",
            "Chinotto": "sabor-chinotto",
            "Frescolita": "sabor-frescolita",
            "Naranja": "sabor-naranja",
            "Uva": "sabor-uva"
        };
        return clases[sabor] || "";
    }

    function abrirSelectorRefresco(btn) {
        refrescoSeleccionadoUrl = btn.dataset.url;
        refrescoSeleccionadoCantidad = obtenerCantidadDesdeBoton(btn);
        modalRefrescoProducto.textContent = btn.dataset.producto || "Refresco";
        saboresRefrescoGrid.innerHTML = "";

        saboresRefresco.forEach(function(sabor) {
            const boton = document.createElement("button");
            boton.type = "button";
            const claseColor = claseSaborRefresco(sabor);
            boton.className = "sabor-btn" + (claseColor ? " " + claseColor : "") + (sabor === "Otro" ? " otro" : "");
            boton.textContent = sabor === "Otro" ? "✍️ Otro" : "🥤 " + sabor;
            boton.addEventListener("click", function() {
                if (sabor === "Otro") {
                    const escrito = prompt("Escribe el sabor del refresco");
                    if (escrito === null || !escrito.trim()) {
                        return;
                    }
                    agregarRefrescoConSabor(escrito);
                    return;
                }
                agregarRefrescoConSabor(sabor);
            });
            saboresRefrescoGrid.appendChild(boton);
        });

        modalRefresco.classList.add("activo");
        modalRefresco.setAttribute("aria-hidden", "false");
    }

    document.querySelectorAll(".btn-refresco").forEach(function(btn) {
        btn.addEventListener("click", function() {
            abrirSelectorRefresco(btn);
        });
    });

    cerrarModalRefresco.addEventListener("click", cerrarSelectorRefresco);
    modalRefresco.addEventListener("click", function(event) {
        if (event.target === modalRefresco) {
            cerrarSelectorRefresco();
        }
    });

    document.querySelectorAll(".form-eliminar-item").forEach(function(form) {
        form.addEventListener("submit", function(event) {
            const clave = pedirClaveSupervisor();
            if (!clave) {
                event.preventDefault();
                return;
            }
            form.querySelector('input[name="clave"]').value = clave;
        });
    });

    document.querySelectorAll(".form-indicacion-item").forEach(function(form) {
        form.addEventListener("submit", function(event) {
            event.preventDefault();
            const actual = form.dataset.indicacion || "";
            const indicacion = prompt("Indicación especial para este plato", actual);
            if (indicacion === null) {
                return;
            }
            form.querySelector('input[name="indicacion"]').value = indicacion.trim();
            form.submit();
        });
    });

    document.querySelectorAll(".form-eliminar-orden").forEach(function(form) {
        form.addEventListener("submit", function(event) {
            if (!confirm("¿Eliminar esta orden completa?")) {
                event.preventDefault();
                return;
            }
            const clave = pedirClaveSupervisor();
            if (!clave) {
                event.preventDefault();
                return;
            }
            form.querySelector('input[name="clave"]').value = clave;
        });
    });

    document.querySelectorAll(".form-emergencia").forEach(function(form) {
        form.addEventListener("submit", function(event) {
            const clave = pedirClaveSupervisor();
            if (!clave) {
                event.preventDefault();
                return;
            }
            form.querySelector('input[name="clave"]').value = clave;
        });
    });

    const modalConfiguracion = document.getElementById("modal-configuracion");
    const modalConfiguracionTitulo = document.getElementById("modal-configuracion-titulo");
    const modalConfiguracionProducto = document.getElementById("modal-configuracion-producto");
    const configuracionOpcionesGrid = document.getElementById("configuracion-opciones-grid");
    const cerrarModalConfiguracion = document.getElementById("cerrar-modal-configuracion");
    let configuracionUrl = "";
    let configuracionCantidad = 1;
    let pasosConfiguracion = [];
    let pasoConfiguracionActual = 0;
    let seleccionesConfiguracion = [];

    function cerrarConfiguracion() {
        configuracionUrl = "";
        pasosConfiguracion = [];
        pasoConfiguracionActual = 0;
        seleccionesConfiguracion = [];
        modalConfiguracion.classList.remove("activo");
        modalConfiguracion.setAttribute("aria-hidden", "true");
    }

    function terminarConfiguracion() {
        const destino = new URL(configuracionUrl, window.location.origin);
        seleccionesConfiguracion.forEach(function(seleccion) {
            const valores = Array.isArray(seleccion.valor) ? seleccion.valor : [seleccion.valor];
            valores.forEach(function(valor) {
                destino.searchParams.append(seleccion.parametro, valor);
            });
        });
        destino.searchParams.append("cantidad", String(configuracionCantidad));
        navegarAgregar(destino.pathname + destino.search);
    }

    function seleccionarOpcionConfiguracion(paso, valor) {
        seleccionesConfiguracion.push({parametro: paso.parametro, valor: valor});
        pasoConfiguracionActual += 1;
        if (pasoConfiguracionActual >= pasosConfiguracion.length) {
            terminarConfiguracion();
            return;
        }
        mostrarPasoConfiguracion();
    }

    function mostrarPasoConfiguracion() {
        const paso = pasosConfiguracion[pasoConfiguracionActual];
        modalConfiguracionTitulo.textContent = paso.titulo;
        configuracionOpcionesGrid.innerHTML = "";

        if (paso.multiple) {
            const seleccionadas = new Set();
            paso.opciones.forEach(function(opcion) {
                const boton = document.createElement("button");
                boton.type = "button";
                const agotada = opcion.disponible === false;
                boton.className = "sabor-btn" + (agotada ? " otro" : "");
                boton.textContent = agotada ? opcion.nombre + " (Agotado)" : opcion.nombre;
                boton.disabled = agotada;
                boton.addEventListener("click", function() {
                    if (seleccionadas.has(opcion.nombre)) {
                        seleccionadas.delete(opcion.nombre);
                        boton.classList.remove("activo");
                    } else {
                        if (seleccionadas.size >= paso.maximo) {
                            alert("Maximo " + paso.maximo + " opcion(es) para " + paso.titulo);
                            return;
                        }
                        seleccionadas.add(opcion.nombre);
                        boton.classList.add("activo");
                    }
                });
                configuracionOpcionesGrid.appendChild(boton);
            });
            const continuar = document.createElement("button");
            continuar.type = "button";
            continuar.className = "sabor-btn combo-aceptar";
            continuar.textContent = "Continuar";
            continuar.addEventListener("click", function() {
                if (seleccionadas.size < paso.minimo) {
                    alert("Selecciona al menos " + paso.minimo + " opcion(es) para " + paso.titulo);
                    return;
                }
                seleccionarOpcionConfiguracion(paso, Array.from(seleccionadas));
            });
            configuracionOpcionesGrid.appendChild(continuar);
            return;
        }

        paso.opciones.forEach(function(opcion) {
            const boton = document.createElement("button");
            boton.type = "button";
            const agotada = opcion.disponible === false;
            boton.className = "sabor-btn" + (agotada ? " otro" : "");
            boton.textContent = agotada ? opcion.nombre + " (Agotado)" : opcion.nombre;
            boton.disabled = agotada;
            boton.addEventListener("click", function() {
                seleccionarOpcionConfiguracion(paso, opcion.nombre);
            });
            configuracionOpcionesGrid.appendChild(boton);
        });
        if (paso.minimo === 0) {
            const omitir = document.createElement("button");
            omitir.type = "button";
            omitir.className = "sabor-btn opcion-omitir";
            omitir.textContent = "Sin " + paso.titulo.toLowerCase();
            omitir.addEventListener("click", function() {
                seleccionarOpcionConfiguracion(paso, []);
            });
            configuracionOpcionesGrid.appendChild(omitir);
        }
    }

    function tituloCombo(producto) {
        const match = (producto || "").match(/(\\d+)/);
        return match ? "COMBO #" + match[1] : (producto || "COMBO");
    }

    function crearGrupoRadio(titulo, nombre, opciones) {
        const seccion = document.createElement("div");
        seccion.className = "combo-config-seccion";
        const etiqueta = document.createElement("label");
        etiqueta.textContent = titulo;
        seccion.appendChild(etiqueta);

        const select = document.createElement("select");
        select.className = "combo-select";
        select.name = nombre;
        select.required = true;

        const opcionVacia = document.createElement("option");
        opcionVacia.value = "";
        opcionVacia.textContent = "Seleccionar...";
        select.appendChild(opcionVacia);

        opciones.forEach(function(opcion) {
            const option = document.createElement("option");
            option.value = opcion;
            option.textContent = opcion;
            select.appendChild(option);
        });
        seccion.appendChild(select);
        return seccion;
    }

    function crearGrupoExtraLumpia() {
        const seccion = document.createElement("div");
        seccion.className = "combo-config-seccion";

        const etiqueta = document.createElement("label");
        etiqueta.textContent = "Extra de Lumpia";
        seccion.appendChild(etiqueta);

        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "extra_lumpias";
        hidden.value = "0";
        seccion.appendChild(hidden);

        const opciones = document.createElement("div");
        opciones.className = "extra-lumpia-opciones";

        const botonSinExtra = document.createElement("button");
        botonSinExtra.type = "button";
        botonSinExtra.className = "extra-lumpia-btn activo";
        botonSinExtra.textContent = "Sin extra de Lumpia";
        botonSinExtra.dataset.valor = "0";

        const botonExtra = document.createElement("button");
        botonExtra.type = "button";
        botonExtra.className = "extra-lumpia-btn";
        botonExtra.textContent = "Extra de Lumpia";
        botonExtra.dataset.valor = "1";

        [botonSinExtra, botonExtra].forEach(function(boton) {
            boton.addEventListener("click", function() {
                hidden.value = boton.dataset.valor;
                botonSinExtra.classList.toggle("activo", boton.dataset.valor === "0");
                botonExtra.classList.toggle("activo", boton.dataset.valor === "1");
            });
            opciones.appendChild(boton);
        });

        seccion.appendChild(opciones);
        return seccion;
    }

    function abrirConfiguracionCombo(btn) {
        configuracionUrl = btn.dataset.url;
        configuracionCantidad = obtenerCantidadDesdeBoton(btn);
        const producto = btn.dataset.producto || "Combo";
        const acompanantes = (btn.dataset.acompanantes || "").split("|").filter(Boolean);
        const bebidas = (btn.dataset.bebidas || "").split("|").filter(Boolean);
        const cantidadAcompanantes = Number(btn.dataset.cantidadAcompanantes || 1);

        modalConfiguracionTitulo.textContent = tituloCombo(producto);
        modalConfiguracionProducto.textContent = "";
        configuracionOpcionesGrid.innerHTML = "";
        configuracionOpcionesGrid.className = "combo-config";

        if (cantidadAcompanantes === 1) {
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Acompañante", "acompanante_1", acompanantes));
        } else {
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Primer acompañante", "acompanante_1", acompanantes));
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Segundo acompañante", "acompanante_2", acompanantes));
        }
        configuracionOpcionesGrid.appendChild(crearGrupoRadio("Bebida", "bebida", bebidas));

        const aceptar = document.createElement("button");
        aceptar.type = "button";
        aceptar.className = "sabor-btn combo-aceptar";
        aceptar.textContent = "Aceptar";
        aceptar.addEventListener("click", function() {
            const destino = new URL(configuracionUrl, window.location.origin);
            for (let i = 1; i <= cantidadAcompanantes; i += 1) {
                const elegido = configuracionOpcionesGrid.querySelector('select[name="acompanante_' + i + '"]');
                if (!elegido || !elegido.value) {
                    alert("Debes seleccionar todos los acompañantes");
                    return;
                }
                destino.searchParams.append("acompanante", elegido.value);
            }
            const bebida = configuracionOpcionesGrid.querySelector('select[name="bebida"]');
            if (!bebida || !bebida.value) {
                alert("Debes seleccionar una bebida");
                return;
            }
            destino.searchParams.append("bebida", bebida.value);
            destino.searchParams.append("cantidad", String(configuracionCantidad));
            navegarAgregar(destino.pathname + destino.search);
        });
        configuracionOpcionesGrid.appendChild(aceptar);

        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }

    function abrirConfiguracion(btn) {
        configuracionUrl = btn.dataset.url;
        configuracionCantidad = obtenerCantidadDesdeBoton(btn);
        modalConfiguracionProducto.textContent = btn.dataset.producto || "Producto";
        pasosConfiguracion = [];
        seleccionesConfiguracion = [];
        pasoConfiguracionActual = 0;
        configuracionOpcionesGrid.className = "sabores-grid";

        let grupos = [];
        try {
            grupos = JSON.parse(btn.dataset.modificadores || "[]");
        } catch (error) {
            grupos = [];
        }
        grupos.forEach(function(grupo) {
            pasosConfiguracion.push({
                titulo: grupo.nombre,
                parametro: "grupo_" + grupo.id,
                opciones: grupo.opciones,
                multiple: !!grupo.multiple,
                // Un grupo opcional (o con minimo 0) se puede omitir; antes el
                // JS exigia siempre 1 aunque el backend lo aceptaba.
                minimo: (grupo.obligatorio === false || grupo.minimo === 0) ? 0 : (grupo.minimo || 1),
                maximo: grupo.maximo || 1
            });
        });

        if (!pasosConfiguracion.length) {
            navegarAgregar(configuracionUrl + "?cantidad=" + configuracionCantidad);
            return;
        }
        mostrarPasoConfiguracion();
        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }

    function abrirConfiguracionSelect(btn) {
        if (btn.dataset.tipo === "combo") {
            abrirConfiguracionCombo(btn);
            return;
        }

        configuracionUrl = btn.dataset.url;
        configuracionCantidad = obtenerCantidadDesdeBoton(btn);
        modalConfiguracionTitulo.textContent = "Configurar promocion";
        modalConfiguracionProducto.textContent = btn.dataset.producto || "Producto";
        configuracionOpcionesGrid.innerHTML = "";
        configuracionOpcionesGrid.className = "combo-config";

        const pollos = (btn.dataset.pollos || "").split("|").filter(Boolean);
        const arroces = (btn.dataset.arroces || "").split("|").filter(Boolean);
        const cantidadArroces = Number(btn.dataset.cantidadArroces || 0);
        const cantidadRefrescos = Number(btn.dataset.cantidadRefrescos || 0);
        const sabores = saboresRefresco.slice();

        if (pollos.length) {
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Tipo de pollo", "pollo", pollos));
        }
        for (let i = 1; i <= cantidadArroces; i += 1) {
            configuracionOpcionesGrid.appendChild(crearGrupoRadio(cantidadArroces === 1 ? "Arroz" : "Arroz " + i, "arroz_" + i, arroces));
        }
        for (let i = 1; i <= cantidadRefrescos; i += 1) {
            configuracionOpcionesGrid.appendChild(crearGrupoRadio(cantidadRefrescos === 1 ? "Refresco" : "Refresco " + i, "sabor_" + i, sabores));
        }
        configuracionOpcionesGrid.appendChild(crearGrupoExtraLumpia());

        const aceptar = document.createElement("button");
        aceptar.type = "button";
        aceptar.className = "sabor-btn combo-aceptar";
        aceptar.textContent = "Aceptar";
        aceptar.addEventListener("click", function() {
            const destino = new URL(configuracionUrl, window.location.origin);
            const campoPollo = configuracionOpcionesGrid.querySelector('select[name="pollo"]');
            if (campoPollo) {
                if (!campoPollo.value) {
                    alert("Debes seleccionar un tipo de pollo");
                    campoPollo.focus();
                    return;
                }
                destino.searchParams.append("pollo", campoPollo.value);
            }

            for (let i = 1; i <= cantidadArroces; i += 1) {
                const arroz = configuracionOpcionesGrid.querySelector('select[name="arroz_' + i + '"]');
                if (!arroz || !arroz.value) {
                    alert("Debes seleccionar todos los arroces");
                    if (arroz) {
                        arroz.focus();
                    }
                    return;
                }
                destino.searchParams.append("arroz", arroz.value);
            }

            for (let i = 1; i <= cantidadRefrescos; i += 1) {
                const sabor = configuracionOpcionesGrid.querySelector('select[name="sabor_' + i + '"]');
                if (!sabor || !sabor.value) {
                    alert("Debes seleccionar todos los refrescos");
                    if (sabor) {
                        sabor.focus();
                    }
                    return;
                }
                let saborFinal = sabor.value;
                if (saborFinal === "Otro") {
                    saborFinal = prompt("Escribe el sabor del refresco");
                    if (saborFinal === null || !saborFinal.trim()) {
                        return;
                    }
                    saborFinal = saborFinal.trim();
                }
                destino.searchParams.append("sabor", saborFinal);
            }

            const extraLumpias = configuracionOpcionesGrid.querySelector('input[name="extra_lumpias"]');
            destino.searchParams.append("extra_lumpias", extraLumpias ? extraLumpias.value : "0");
            destino.searchParams.append("cantidad", String(configuracionCantidad));
            navegarAgregar(destino.pathname + destino.search);
        });
        configuracionOpcionesGrid.appendChild(aceptar);

        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }

    document.querySelectorAll(".btn-configurable").forEach(function(btn) {
        btn.addEventListener("click", function() { abrirConfiguracionSelect(btn); });
    });
    document.querySelectorAll(".btn-modificadores").forEach(function(btn) {
        btn.addEventListener("click", function() { abrirConfiguracion(btn); });
    });
    cerrarModalConfiguracion.addEventListener("click", cerrarConfiguracion);
    modalConfiguracion.addEventListener("click", function(event) {
        if (event.target === modalConfiguracion) { cerrarConfiguracion(); }
    });
"""

_JS_ORDEN = _JS_ORDEN_PRE + _JS_ORDEN_LEGACY + _JS_ORDEN_POST
