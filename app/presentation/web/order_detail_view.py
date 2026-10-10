"""
order_detail_view.py (presentacion)

Render HTML/JS de la pantalla de detalle de orden (`/orden/<id>` en
web_app.py, GET). Es la ultima pieza grande de presentacion que
quedaba en el monolito: la ruta ya delegaba TODAS sus consultas a
repositorios (SqlSalesOrderRepository, SqlSalesCatalogRepository,
delivery.py, payments.py) antes de esta extraccion -- este modulo
mueve el HTML/JS (que no tenia ninguna consulta ni escritura propia,
solo lectura de datos ya resueltos) fuera de web_app.py, dejando la
ruta como: resolver datos -> `render_detalle_orden(...)`.

Deliberadamente NO se porto a Jinja/templates/: el codigo original usa
f-strings con `html_lib.escape()` manual en cada punto de interpolacion
(no autoescaping), y reescribirlo sobre un motor de templates con
semantica de escape distinta es un cambio de comportamiento real, no
una extraccion mecanica -- se preservo el codigo EXACTO (mismas
variables, mismo texto, mismo escaping) para no arriesgar una regresion
de XSS o de render por una migracion de motor no pedida.

Todo lo que esta funcion necesita se recibe explicito (nada de
`import web_app` ni acceso a `session`/`request` directamente): 19
valores ya resueltos por la ruta (queries/view-model), 11 constantes de
configuracion del menu POS (viven en web_app.py, se inyectan para
evitar un import circular) y 7 funciones/helpers de presentacion
compartidos con otras pantallas (estilos_base, barra_superior, etc. --
mismo patron de inyeccion ya usado por
app.presentation.web.cxc_routes.crear_cxc_blueprint). Los helpers que
SI son puros y viven en el dominio (es_producto_refresco,
es_producto_delivery_legacy, texto_descripcion_combo_orden,
texto_descripcion_promocion_orden, TOLERANCIA_COBRO,
DELIVERY_MONTO_MAXIMO) se importan directo, sin inyeccion.
"""

import html as html_lib
import json
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
    COLORES_CATEGORIAS_POS,
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
):
    modificadores_por_producto = modificadores_por_producto or {}
    boton_reimprimir = ""
    if usuario_puede_reimprimir_cocina() and estado in ("en cocina", "listo", "cerrada"):
        boton_reimprimir = (
            f'<a href="/reimprimir_cocina/{orden_id}" class="btn-accion" '
            'style="background:#8e44ad;">🔁 Reimprimir cocina</a>'
        )

    advertencia_cobro = ""
    if estado == "abierta":
        advertencia_cobro = (
            ' onclick="return confirm(\'⚠️ Esta orden aún no ha sido enviada a cocina. '
            '¿Seguro que quieres continuar con el cobro?\')"'
        )

    html = f"""
    <html>
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    {estilos_base()}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; background: var(--gris-fondo); color: var(--texto); }}
    .contenedor {{ display: flex; gap: 0; }}
    .productos {{ width: 60%; padding: 18px; }}
    .panel {{ width: 40%; padding: 18px; background: var(--panel); min-height: calc(100vh - 70px); box-sizing: border-box; border-left: 1px solid var(--borde); box-shadow: -4px 0 18px rgba(0,0,0,0.24); }}
    .btn {{ width: 100%; padding: 14px; margin: 6px 0; background: var(--tarjeta); color: var(--texto); border: 1px solid var(--borde); border-radius: 12px; font-weight: 800; font-size: 15px; cursor: pointer; box-shadow:var(--sombra-suave); transition:background 0.16s ease, border-color 0.16s ease, transform 0.1s ease; }}
    .btn:hover {{ background:#252A32; border-color:rgba(61,220,132,0.38); }}
    .categoria {{ font-weight: 800; margin-top: 14px; background: var(--panel-secundario) !important; color: var(--texto-secundario); padding: 8px 12px; border-radius: 999px; font-size: 13px; letter-spacing: 0.5px; border: 1px solid var(--borde); display:inline-flex; }}
    .grid-productos {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .producto-item {{ display: flex; flex-direction: column; }}
    .producto-item .btn {{ margin-bottom: 4px; }}
    .qty-stepper {{ display: flex; align-items: center; justify-content: center; gap: 6px; margin: 0 0 6px; }}
    .qty-btn {{ width: 30px; height: 30px; border-radius: 8px; border: 1px solid var(--borde); background: var(--panel-secundario); color: var(--texto); font-weight: 800; font-size: 16px; cursor: pointer; line-height: 1; }}
    .qty-btn:hover {{ border-color: rgba(61,220,132,0.38); }}
    .qty-input {{ width: 46px; height: 30px; text-align: center; border-radius: 8px; border: 1px solid var(--borde); background: var(--tarjeta); color: var(--texto); font-weight: 800; font-size: 14px; }}
    .acciones-superiores {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px; }}
    .btn-accion {{ display: block; padding: 14px 12px; margin: 5px 0; text-align: center; color: white; text-decoration: none; border-radius: 10px; font-weight: 800; font-size: 15px; }}
    .cocina {{ background: var(--naranja); color:#0F1115; border:none; }}
    .cobrar {{ background: var(--verde-neko); color:#0F1115; border:none; }}
    .editar {{ background: var(--azul); border:none; }}
    .eliminar {{ background: var(--rojo); border:none; }}
    .volver {{ background: var(--panel-secundario); border:1px solid var(--borde); }}
    .total {{ font-size: 20px; margin-top: 12px; font-weight: 800; color: var(--texto); }}
    .info-cierre {{ background:#2A2417; border:1px solid var(--naranja); padding:12px; border-radius:10px; margin-bottom:14px; color:#F8D083; font-weight:600; }}
    .modal-refresco {{ position:fixed; inset:0; background:rgba(17,24,39,0.62); display:none; align-items:center; justify-content:center; padding:18px; z-index:1000; }}
    .modal-refresco.activo {{ display:flex; }}
    .modal-contenido {{ width:min(620px, 100%); max-height:85vh; overflow-y:auto; background:var(--panel); color:var(--texto); border:1px solid var(--borde); border-radius:16px; padding:18px; box-shadow:0 24px 50px rgba(0,0,0,0.42); }}
    .modal-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:14px; }}
    .modal-top h2 {{ margin:0; color:var(--verde-neko); }}
    .modal-top p {{ margin:5px 0 0; color:var(--texto-secundario); }}
    .cerrar-modal {{ width:auto; min-height:44px; padding:8px 14px; border:none; border-radius:8px; background:#6b7280; color:white; cursor:pointer; font-weight:700; }}
    .sabores-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }}
    .sabor-btn {{ min-height:68px; padding:14px; border:none; border-radius:12px; background:var(--tarjeta); color:var(--texto); font-size:16px; font-weight:900; cursor:pointer; text-align:center; display:flex; align-items:center; justify-content:center; box-shadow:var(--sombra-suave); transition:opacity 0.16s ease, transform 0.16s ease, border-color 0.16s ease; }}
    .sabor-btn:hover {{ opacity:0.90; transform:translateY(-1px); }}
    .sabor-btn:active {{ transform:translateY(0); }}
    .sabor-coca-cola {{ background:#E50914; }}
    .sabor-chinotto {{ background:#111827; }}
    .sabor-frescolita {{ background:#FF4C4C; }}
    .sabor-naranja {{ background:#f97316; color:#1c1917; }}
    .sabor-uva {{ background:#6A0DAD; }}
    .sabor-btn.otro {{ background:#7c3aed; }}
    .item-orden {{ display:flex; justify-content:space-between; align-items:flex-start; margin:5px 0; gap:10px; border-bottom:1px solid var(--borde); padding:8px 0; }}
    .item-detalle {{ flex:1; min-width:0; }}
    .item-indicacion {{ color:var(--verde-neko); font-size:13px; margin-top:3px; font-weight:700; }}
    .item-descripcion {{ color:var(--verde-neko); font-size:14px; margin-top:4px; font-weight:800; line-height:1.35; white-space:pre-line; }}
    .acciones-item {{ display:flex; gap:6px; align-items:center; flex:0 0 auto; }}
    .btn-item {{ color:white; border:none; border-radius:8px; padding:8px 10px; cursor:pointer; width:auto; min-height:38px; box-shadow:none; font-weight:700; }}
    .combo-config {{ display:grid; grid-template-columns:1fr; gap:12px; }}
    .combo-config-seccion {{ margin:0; }}
    .combo-config-seccion label {{ display:block; margin:0 0 6px; color:var(--texto-secundario); font-size:13px; font-weight:800; letter-spacing:0.3px; text-transform:uppercase; }}
    .combo-select {{ width:100%; min-height:50px; padding:11px 12px; border:1px solid var(--borde); border-radius:10px; background:var(--panel-secundario); color:var(--texto); font-size:16px; font-weight:800; box-sizing:border-box; }}
    .combo-select:focus {{ outline:none; border-color:var(--verde-neko); box-shadow:0 0 0 3px rgba(61,220,132,0.12); }}
    .extra-lumpia-opciones {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    .extra-lumpia-btn {{ min-height:50px; padding:11px 12px; border:1px solid var(--borde); border-radius:10px; background:var(--panel-secundario); color:var(--texto); font-size:15px; font-weight:900; cursor:pointer; transition:background 0.16s ease, border-color 0.16s ease; }}
    .extra-lumpia-btn:hover {{ background:#252A32; border-color:#3C4350; }}
    .extra-lumpia-btn.activo {{ background:var(--verde-neko); color:white; border-color:var(--verde-neko); }}
    .combo-aceptar {{ width:100%; margin-top:4px; background:var(--verde-neko); color:#0F1115; position:sticky; bottom:0; }}
    .delivery-panel {{ border:1px solid var(--borde); background:var(--panel-secundario); border-radius:12px; padding:14px; margin:14px 0; }}
    .delivery-panel h3 {{ margin-top:0; }}
    .delivery-grid {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:8px; margin:8px 0; }}
    .delivery-monto-btn {{ min-height:44px; border:1px solid var(--borde); border-radius:9px; background:var(--tarjeta); color:var(--texto); font-weight:900; cursor:pointer; }}
    .delivery-monto-btn.activo {{ background:var(--verde-neko); color:#0F1115; border-color:var(--verde-neko); }}
    .delivery-form-row {{ display:grid; grid-template-columns:1fr; gap:8px; }}
    .delivery-actions {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }}
    .delivery-help {{ color:var(--texto-secundario); font-size:13px; margin:6px 0; }}
    .delivery-alerta {{ background:#3b2b12; color:#fde68a; border:1px solid #92400e; border-radius:8px; padding:10px; margin:8px 0; }}
    .delivery-nuevo {{ display:none; margin-top:10px; border-top:1px solid var(--borde); padding-top:10px; }}
    .delivery-nuevo.activo {{ display:block; }}
    .total-cliente {{ color:var(--verde-neko); }}
    .self-order-panel {{ border:1px solid var(--borde); background:var(--panel-secundario); border-radius:12px; padding:14px; margin:14px 0; }}
    .self-order-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }}
    .self-order-head h3 {{ margin:0 0 4px; }}
    .self-order-head p {{ margin:0; color:var(--texto-secundario); font-size:13px; }}
    .self-order-pill {{ border-radius:999px; padding:6px 10px; font-size:12px; font-weight:900; white-space:nowrap; }}
    .self-order-pill.activo {{ background:rgba(61,220,132,0.16); color:var(--verde-neko); border:1px solid rgba(61,220,132,0.4); }}
    .self-order-pill.inactivo {{ background:#272B33; color:var(--texto-secundario); border:1px solid var(--borde); }}
    .self-order-qr {{ display:grid; grid-template-columns:130px 1fr; gap:12px; margin-top:12px; align-items:start; }}
    .self-order-qr img {{ width:130px; height:130px; background:white; border-radius:8px; padding:6px; box-sizing:border-box; }}
    .self-order-info label {{ display:block; color:var(--texto-secundario); font-size:12px; font-weight:900; margin:4px 0; text-transform:uppercase; }}
    .self-order-info input {{ width:100%; box-sizing:border-box; margin-bottom:8px; }}
    .self-order-info code {{ display:block; overflow-wrap:anywhere; background:#111827; border:1px solid var(--borde); border-radius:8px; padding:8px; color:var(--verde-neko); font-size:12px; }}
    .self-order-actions {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }}
    .self-order-action {{ margin-top:12px; }}
    .self-order-revocar {{ background:#4A1E23; color:#fecaca; }}
    @media (max-width: 768px) {{
        .contenedor {{ flex-direction: column; }}
        .productos, .panel {{ width: 100%; min-height: auto; border-left: none; }}
        .sabores-grid {{ grid-template-columns:1fr 1fr; }}
        .extra-lumpia-opciones {{ grid-template-columns:1fr; }}
        .delivery-grid, .delivery-actions {{ grid-template-columns:1fr 1fr; }}
        .self-order-qr, .self-order-actions {{ grid-template-columns:1fr; }}
        .self-order-qr img {{ width:160px; height:160px; }}
        .modal-refresco {{ padding:12px; }}
        .modal-contenido {{ width:calc(100% - 24px); padding:14px; }}
    }}
    </style>
    </head>
    <body>
    """

    html += barra_superior('<a href="/">🏠 Inicio</a>')

    html += """
    <div class="contenedor">
    <div class="productos">
    <h2>📋 Agregar productos</h2>
    """

    if bloqueada_por_cierre:
        html += f"""
        <div class="info-cierre">
            Esta orden ya pertenece a un cierre de jornada. Primero debes revertirla desde reportes.
        </div>
        """
    elif estado == "cerrada" and edicion_emergencia_activa:
        html += """
        <div class="info-cierre">
            Edicion de emergencia activa. Corrige la orden y vuelve a cobrar para actualizar los pagos.
        </div>
        """

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

    if puede_modificar_orden:
        for categoria, lista in cats_ordenadas:
            color_cat = COLORES_CATEGORIAS_POS.get(categoria, "#374151")
            categoria_html = html_lib.escape(categoria)
            html += f"<div class='categoria' style='background:{color_cat};'>{categoria_html}</div>"
            html += "<div class='grid-productos'>"

            for p in lista:
                precio_fmt = f"${p[2]:.2f}".rstrip("0").rstrip(".")
                producto_nombre_html = html_lib.escape(p[1])
                producto_nombre_attr = html_lib.escape(p[1], quote=True)
                qty_stepper_html = f"""
                <div class="qty-stepper">
                    <button type="button" class="qty-btn qty-dec" aria-label="Menos">-</button>
                    <input type="number" class="qty-input" min="1" max="{MAX_CANTIDAD_ITEM}" step="1" value="1" inputmode="numeric">
                    <button type="button" class="qty-btn qty-inc" aria-label="Mas">+</button>
                </div>
                """
                if es_producto_refresco(p[1]):
                    html += f"""
                    <div class="producto-item">
                    {qty_stepper_html}
                    <button class="btn btn-refresco" type="button" data-url="/agregar/{orden_id}/{p[0]}" data-producto="{producto_nombre_attr}">
                        {producto_nombre_html} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span>
                    </button>
                    </div>
                    """
                elif p[1] in COMBOS_PERSONALES:
                    acompanantes_data = html_lib.escape("|".join(ACOMPANANTES_COMBO), quote=True)
                    bebidas_data = html_lib.escape("|".join(BEBIDAS_COMBO), quote=True)
                    cantidad_acompanantes = COMBOS_CANTIDAD_ACOMPANANTES.get(p[1], 1)
                    html += f"""
                    <div class="producto-item">
                    {qty_stepper_html}
                    <button class="btn btn-configurable" type="button" data-tipo="combo" data-url="/agregar/{orden_id}/{p[0]}" data-producto="{producto_nombre_attr}" data-acompanantes="{acompanantes_data}" data-cantidad-acompanantes="{cantidad_acompanantes}" data-bebidas="{bebidas_data}">
                        {producto_nombre_html} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span>
                    </button>
                    </div>
                    """
                elif p[1] in PROMOCIONES_NEKO:
                    promo = PROMOCIONES_NEKO[p[1]]
                    pollos_data = html_lib.escape("|".join(POLLOS_PROMOCION if p[1] in PROMOCIONES_CON_POLLO else []), quote=True)
                    arroces_data = html_lib.escape("|".join(ARROCES_PROMOCION), quote=True)
                    html += f"""
                    <div class="producto-item">
                    {qty_stepper_html}
                    <button class="btn btn-configurable" type="button" data-tipo="promocion" data-url="/agregar/{orden_id}/{p[0]}" data-producto="{producto_nombre_attr}" data-pollos="{pollos_data}" data-arroces="{arroces_data}" data-cantidad-arroces="{promo['cantidad_arroces']}" data-cantidad-refrescos="{promo['cantidad_refrescos']}" data-refresco="{promo['refresco']}">
                        {producto_nombre_html} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span>
                    </button>
                    </div>
                    """
                elif modificadores_por_producto.get(p[0]):
                    grupos_modificador_data = html_lib.escape(
                        json.dumps(
                            [
                                {
                                    "id": grupo.id,
                                    "nombre": grupo.nombre,
                                    "multiple": grupo.seleccion_multiple,
                                    "minimo": grupo.minimo,
                                    "maximo": grupo.maximo,
                                    "opciones": [
                                        {"nombre": opcion.nombre, "disponible": opcion.disponible}
                                        for opcion in grupo.opciones
                                    ],
                                }
                                for grupo in modificadores_por_producto[p[0]]
                            ]
                        ),
                        quote=True,
                    )
                    html += f"""
                    <div class="producto-item">
                    {qty_stepper_html}
                    <button class="btn btn-modificadores" type="button" data-url="/agregar_con_modificadores/{orden_id}/{p[0]}" data-producto="{producto_nombre_attr}" data-modificadores="{grupos_modificador_data}">
                        {producto_nombre_html} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span>
                    </button>
                    </div>
                    """
                else:
                    html += f"""
                    <div class="producto-item">
                    {qty_stepper_html}
                    <button class="btn btn-simple" type="button" data-url="/agregar/{orden_id}/{p[0]}">{producto_nombre_html} <span style="opacity:0.75;font-size:13px;">{precio_fmt}</span></button>
                    </div>
                    """

            html += "</div>"

    html += "</div>"
    boton_eliminar_orden = ""
    if usuario_es_admin_cierre() and not bloqueada_por_cierre and estado in ("abierta", "en cocina"):
        boton_eliminar_orden = f"""
            <form method="post" action="/eliminar_orden/{orden_id}" class="form-eliminar-orden" style="margin:0;">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-accion eliminar" style="width:100%; border:none; cursor:pointer;">🗑️ Eliminar orden</button>
            </form>
        """

    boton_editar_orden = ""
    if puede_modificar_orden:
        boton_editar_orden = f'<a href="/editar_orden/{orden_id}" class="btn-accion editar">✏️ Editar orden</a>'

    boton_emergencia = ""
    if usuario_es_admin_cierre() and estado == "cerrada" and not bloqueada_por_cierre:
        if edicion_emergencia_activa:
            boton_emergencia = '<div class="btn-accion" style="background:#DC2626;">🚨 Emergencia activa</div>'
        else:
            boton_emergencia = f"""
            <form method="post" action="/activar_edicion_emergencia/{orden_id}" class="form-emergencia" style="margin:0;">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-accion" style="width:100%; border:none; cursor:pointer; background:#DC2626;">🚨 Editar emergencia</button>
            </form>
            """

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

    tipo_html = html_lib.escape(o[3] or "-")
    referencia_html = html_lib.escape(o[4] or "-")
    cliente_html = html_lib.escape(o[5] or "-")
    mesonera_html = html_lib.escape(o[9] or "-")
    estado_html = html_lib.escape(estado)
    observacion_html = html_lib.escape(o[7] or "-")

    html += f"""
    <div class="panel">
        <h2>🧾 Orden {texto_numero_orden(o[1])}</h2>
        <div class="acciones-superiores">
            {boton_editar_orden}
            {boton_eliminar_orden}
            {boton_emergencia}
        </div>
        <p>Tipo: {tipo_html}</p>
        <p>Referencia: {referencia_html}</p>
        <p>👤 Cliente: {cliente_html}</p>
        <p>👩 Mesonera: <b>{mesonera_html}</b></p>
        <p>Estado: {estado_html}</p>
        <p>Observacion: {observacion_html}</p>
        {self_ordering_panel}
        <h3>🍽️ Productos</h3>
    """

    for i in items:
        if not puede_modificar_orden:
            boton_eliminar = ""
            boton_indicacion = ""
        else:
            boton_eliminar = f"""
            <form method="post" action="/eliminar_item/{i[2]}/{orden_id}" class="form-eliminar-item" style="margin:0;">
                <input type="hidden" name="clave" value="">
                <button type="submit" class="btn-item" style="background:#c0392b;">❌</button>
            </form>
            """
            boton_indicacion = f"""
            <form method="post" action="/actualizar_indicacion_item/{i[2]}/{orden_id}" class="form-indicacion-item" style="margin:0;" data-indicacion="{html_lib.escape(i[3] or '', quote=True)}">
                <input type="hidden" name="indicacion" value="">
                <button type="submit" class="btn-item" style="background:#2980b9;">✏️</button>
            </form>
            """

        descripcion_combo = (
            texto_descripcion_combo_orden(i[0], i[3])
            or texto_descripcion_promocion_orden(i[0], i[3])
            or texto_descripcion_modificador_orden(i[3])
        )
        indicacion_html = ""
        if descripcion_combo:
            descripcion_segura = "<br>".join(
                html_lib.escape(linea) for linea in descripcion_combo.splitlines()
            )
            indicacion_html = f"<div class='item-descripcion'>{descripcion_segura}</div>"
        elif i[3]:
            indicacion_html = f"<div class='item-indicacion'>(Indicación: {html_lib.escape(i[3])})</div>"

        html += f"""
        <div class="item-orden">
            <div class="item-detalle">
                <div>{html_lib.escape(i[0])} - ${i[1]}</div>
                {indicacion_html}
            </div>
            <div class="acciones-item">
                {boton_indicacion}
                {boton_eliminar}
            </div>
        </div>
        """

    html += f"""
        <div class="delivery-panel">
            <h3>Delivery</h3>
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
        </div>
        {_render_panel_conductor_delivery(orden_id, conductor_delivery_info, conductores_delivery_activos)}
        <div class="total total-cliente">Total Orden: ${total_orden_usd:.2f}</div>
        <div class="total">Bs: {formato_bs_resumen(total_orden_bs)}</div>
        {boton_reimprimir}
    """

    if not bloqueada_por_cierre and estado != "cerrada":
        html += f"""
        <a href="/enviar_cocina/{orden_id}" class="btn-accion cocina">🍳 Enviar a cocina</a>
        <a href="/activar_factura/{orden_id}" class="btn-accion" style="background:#8e44ad;">🧾 Facturar</a>
        <a href="/cobrar/{orden_id}" class="btn-accion cobrar"{advertencia_cobro}>💵 Cobrar</a>
        """
    elif edicion_emergencia_activa:
        html += f"""
        <a href="/cobrar/{orden_id}" class="btn-accion cobrar">💵 Volver a cobrar</a>
        """

    if not bloqueada_por_cierre and pendiente_post_cobro:
        html += f"""
        <a href="/orden/{orden_id}/cobrar_pendiente" class="btn-accion cobrar" style="background:#e67e22;">💵 Cobrar consumo adicional (${pendiente_post_cobro['pendiente_usd']:.2f})</a>
        """

    if not bloqueada_por_cierre and items and estado in ("abierta", "en cocina", "listo", "cerrada"):
        html += f"""
        <a href="/reimprimir_factura/{orden_id}" class="btn-accion" style="background:#d35400;">🧾 Reimprimir factura</a>
        """

    html += f"""
        <a href="/factura/{orden_id}" class="btn-accion" style="background:#16a085;">🔍 Ver factura</a>
        <a href="/" class="btn-accion volver">🏠 Volver</a>
    </div>
    </div>
    <div id="modal-refresco" class="modal-refresco" aria-hidden="true">
        <div class="modal-contenido">
            <div class="modal-top">
                <div>
                    <h2>🥤 Seleccionar sabor</h2>
                    <p id="modal-refresco-producto">Refresco</p>
                </div>
                <button id="cerrar-modal-refresco" class="cerrar-modal" type="button">✖</button>
            </div>
            <div id="sabores-refresco-grid" class="sabores-grid"></div>
        </div>
    </div>
    <div id="modal-configuracion" class="modal-refresco" aria-hidden="true">
        <div class="modal-contenido">
            <div class="modal-top">
                <div>
                    <h2 id="modal-configuracion-titulo">Configurar producto</h2>
                    <p id="modal-configuracion-producto">Producto</p>
                </div>
                <button id="cerrar-modal-configuracion" class="cerrar-modal" type="button">✖</button>
            </div>
            <div id="configuracion-opciones-grid" class="sabores-grid"></div>
        </div>
    </div>
    <script>
    function pedirClaveSupervisor() {{
        const clave = prompt("Clave de supervisor");
        if (clave === null) {{
            return null;
        }}
        return clave.trim();
    }}

    const selfOrderPanel = document.getElementById("selfOrderPanel");
    const selfOrderMensaje = document.getElementById("selfOrderMensaje");
    function setSelfOrderMensaje(texto) {{
        if (selfOrderMensaje) {{
            selfOrderMensaje.textContent = texto || "";
        }}
    }}
    async function postSelfOrder(url) {{
        const response = await fetch(url, {{ method: "POST", headers: {{ "Accept": "application/json" }} }});
        if (!response.ok) {{
            let mensaje = "No se pudo completar la operacion.";
            try {{
                const data = await response.json();
                if (data.error) mensaje = data.error;
            }} catch (error) {{}}
            throw new Error(mensaje);
        }}
        return response.json();
    }}
    const generarSelfOrder = document.getElementById("generarSelfOrder");
    if (generarSelfOrder && selfOrderPanel) {{
        generarSelfOrder.addEventListener("click", async function() {{
            generarSelfOrder.disabled = true;
            setSelfOrderMensaje("Generando QR...");
            try {{
                await postSelfOrder(`/orden/${{selfOrderPanel.dataset.ordenId}}/self-ordering/link`);
                window.location.reload();
            }} catch (error) {{
                generarSelfOrder.disabled = false;
                setSelfOrderMensaje(error.message);
            }}
        }});
    }}
    const revocarSelfOrder = document.getElementById("revocarSelfOrder");
    if (revocarSelfOrder && selfOrderPanel) {{
        revocarSelfOrder.addEventListener("click", async function() {{
            if (!confirm("Revocar el QR de autoservicio de esta mesa?")) return;
            revocarSelfOrder.disabled = true;
            setSelfOrderMensaje("Revocando QR...");
            try {{
                await postSelfOrder(`/orden/${{selfOrderPanel.dataset.ordenId}}/self-ordering/link/${{selfOrderPanel.dataset.linkId}}/revocar`);
                window.location.reload();
            }} catch (error) {{
                revocarSelfOrder.disabled = false;
                setSelfOrderMensaje(error.message);
            }}
        }});
    }}
    const copiarSelfOrder = document.getElementById("copiarSelfOrder");
    if (copiarSelfOrder) {{
        copiarSelfOrder.addEventListener("click", async function() {{
            const input = document.getElementById("selfOrderUrl");
            if (!input) return;
            try {{
                await navigator.clipboard.writeText(input.value);
                setSelfOrderMensaje("Link copiado.");
            }} catch (error) {{
                input.select();
                document.execCommand("copy");
                setSelfOrderMensaje("Link copiado.");
            }}
        }});
    }}

    const saboresRefresco = ["Coca Cola", "Chinotto", "Frescolita", "Naranja", "Uva", "Manzana", "7Up", "Pepsi", "Otro"];
    const modalRefresco = document.getElementById("modal-refresco");
    const modalRefrescoProducto = document.getElementById("modal-refresco-producto");
    const saboresRefrescoGrid = document.getElementById("sabores-refresco-grid");
    const cerrarModalRefresco = document.getElementById("cerrar-modal-refresco");
    let refrescoSeleccionadoUrl = "";
    let refrescoSeleccionadoCantidad = 1;

    function obtenerCantidadDesdeBoton(btn) {{
        const contenedor = btn.closest(".producto-item");
        const input = contenedor ? contenedor.querySelector(".qty-input") : null;
        let valor = input ? parseInt(input.value, 10) : 1;
        if (!valor || valor < 1) {{
            valor = 1;
        }}
        if (valor > {MAX_CANTIDAD_ITEM}) {{
            valor = {MAX_CANTIDAD_ITEM};
        }}
        return valor;
    }}

    document.querySelectorAll(".producto-item").forEach(function(item) {{
        const input = item.querySelector(".qty-input");
        if (!input) {{
            return;
        }}
        const dec = item.querySelector(".qty-dec");
        const inc = item.querySelector(".qty-inc");
        if (dec) {{
            dec.addEventListener("click", function() {{
                input.value = Math.max(1, (parseInt(input.value, 10) || 1) - 1);
            }});
        }}
        if (inc) {{
            inc.addEventListener("click", function() {{
                input.value = Math.min({MAX_CANTIDAD_ITEM}, (parseInt(input.value, 10) || 1) + 1);
            }});
        }}
    }});

    document.querySelectorAll(".btn-simple").forEach(function(btn) {{
        btn.addEventListener("click", function() {{
            const cantidad = obtenerCantidadDesdeBoton(btn);
            window.location.href = btn.dataset.url + "?cantidad=" + cantidad;
        }});
    }});
    const deliveryMonto = document.getElementById("delivery_usd");
    const deliveryRepartidor = document.getElementById("delivery_repartidor_id");
    const nuevoRepartidorPanel = document.getElementById("nuevoRepartidorPanel");
    const mostrarNuevoRepartidor = document.getElementById("mostrarNuevoRepartidor");
    const guardarNuevoRepartidor = document.getElementById("guardarNuevoRepartidor");
    const nuevoRepartidorNombre = document.getElementById("nuevoRepartidorNombre");
    const nuevoRepartidorTelefono = document.getElementById("nuevoRepartidorTelefono");
    const nuevoRepartidorMensaje = document.getElementById("nuevoRepartidorMensaje");

    document.querySelectorAll(".delivery-monto-btn").forEach(function(btn) {{
        btn.addEventListener("click", function() {{
            if (!deliveryMonto || deliveryMonto.disabled) {{
                return;
            }}
            deliveryMonto.value = btn.dataset.deliveryMonto;
            document.querySelectorAll(".delivery-monto-btn").forEach(function(opcion) {{
                opcion.classList.toggle("activo", opcion === btn);
            }});
        }});
    }});

    if (mostrarNuevoRepartidor && nuevoRepartidorPanel) {{
        mostrarNuevoRepartidor.addEventListener("click", function() {{
            nuevoRepartidorPanel.classList.toggle("activo");
            if (nuevoRepartidorPanel.classList.contains("activo") && nuevoRepartidorNombre) {{
                nuevoRepartidorNombre.focus();
            }}
        }});
    }}

    if (guardarNuevoRepartidor) {{
        guardarNuevoRepartidor.addEventListener("click", function() {{
            const nombre = (nuevoRepartidorNombre.value || "").trim();
            const telefono = (nuevoRepartidorTelefono.value || "").trim();
            if (!nombre) {{
                nuevoRepartidorMensaje.textContent = "El nombre es obligatorio.";
                nuevoRepartidorNombre.focus();
                return;
            }}
            fetch("/api/repartidores", {{
                method: "POST",
                headers: {{"Content-Type": "application/json"}},
                body: JSON.stringify({{nombre: nombre, telefono: telefono}})
            }})
            .then(function(response) {{ return response.json().then(function(data) {{ return {{status: response.status, data: data}}; }}); }})
            .then(function(result) {{
                if (!result.data.ok) {{
                    nuevoRepartidorMensaje.textContent = result.data.error || "No se pudo crear el repartidor.";
                    return;
                }}
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
            }})
            .catch(function() {{
                nuevoRepartidorMensaje.textContent = "No se pudo crear el repartidor.";
            }});
        }});
    }}

    function cerrarSelectorRefresco() {{
        refrescoSeleccionadoUrl = "";
        modalRefresco.classList.remove("activo");
        modalRefresco.setAttribute("aria-hidden", "true");
    }}

    function agregarRefrescoConSabor(sabor) {{
        const saborLimpio = (sabor || "").trim();
        if (!saborLimpio || !refrescoSeleccionadoUrl) {{
            return;
        }}
        window.location.href = refrescoSeleccionadoUrl + "?sabor=" + encodeURIComponent(saborLimpio) + "&cantidad=" + refrescoSeleccionadoCantidad;
    }}

    function claseSaborRefresco(sabor) {{
        const clases = {{
            "Coca Cola": "sabor-coca-cola",
            "Chinotto": "sabor-chinotto",
            "Frescolita": "sabor-frescolita",
            "Naranja": "sabor-naranja",
            "Uva": "sabor-uva"
        }};
        return clases[sabor] || "";
    }}

    function abrirSelectorRefresco(btn) {{
        refrescoSeleccionadoUrl = btn.dataset.url;
        refrescoSeleccionadoCantidad = obtenerCantidadDesdeBoton(btn);
        modalRefrescoProducto.textContent = btn.dataset.producto || "Refresco";
        saboresRefrescoGrid.innerHTML = "";

        saboresRefresco.forEach(function(sabor) {{
            const boton = document.createElement("button");
            boton.type = "button";
            const claseColor = claseSaborRefresco(sabor);
            boton.className = "sabor-btn" + (claseColor ? " " + claseColor : "") + (sabor === "Otro" ? " otro" : "");
            boton.textContent = sabor === "Otro" ? "✍️ Otro" : "🥤 " + sabor;
            boton.addEventListener("click", function() {{
                if (sabor === "Otro") {{
                    const escrito = prompt("Escribe el sabor del refresco");
                    if (escrito === null || !escrito.trim()) {{
                        return;
                    }}
                    agregarRefrescoConSabor(escrito);
                    return;
                }}
                agregarRefrescoConSabor(sabor);
            }});
            saboresRefrescoGrid.appendChild(boton);
        }});

        modalRefresco.classList.add("activo");
        modalRefresco.setAttribute("aria-hidden", "false");
    }}

    document.querySelectorAll(".btn-refresco").forEach(function(btn) {{
        btn.addEventListener("click", function() {{
            abrirSelectorRefresco(btn);
        }});
    }});

    cerrarModalRefresco.addEventListener("click", cerrarSelectorRefresco);
    modalRefresco.addEventListener("click", function(event) {{
        if (event.target === modalRefresco) {{
            cerrarSelectorRefresco();
        }}
    }});

    document.querySelectorAll(".form-eliminar-item").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            const clave = pedirClaveSupervisor();
            if (!clave) {{
                event.preventDefault();
                return;
            }}
            form.querySelector('input[name="clave"]').value = clave;
        }});
    }});

    document.querySelectorAll(".form-indicacion-item").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            event.preventDefault();
            const actual = form.dataset.indicacion || "";
            const indicacion = prompt("Indicación especial para este plato", actual);
            if (indicacion === null) {{
                return;
            }}
            form.querySelector('input[name="indicacion"]').value = indicacion.trim();
            form.submit();
        }});
    }});

    document.querySelectorAll(".form-eliminar-orden").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            if (!confirm("¿Eliminar esta orden completa?")) {{
                event.preventDefault();
                return;
            }}
            const clave = pedirClaveSupervisor();
            if (!clave) {{
                event.preventDefault();
                return;
            }}
            form.querySelector('input[name="clave"]').value = clave;
        }});
    }});

    document.querySelectorAll(".form-emergencia").forEach(function(form) {{
        form.addEventListener("submit", function(event) {{
            const clave = pedirClaveSupervisor();
            if (!clave) {{
                event.preventDefault();
                return;
            }}
            form.querySelector('input[name="clave"]').value = clave;
        }});
    }});

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

    function cerrarConfiguracion() {{
        configuracionUrl = "";
        pasosConfiguracion = [];
        pasoConfiguracionActual = 0;
        seleccionesConfiguracion = [];
        modalConfiguracion.classList.remove("activo");
        modalConfiguracion.setAttribute("aria-hidden", "true");
    }}

    function terminarConfiguracion() {{
        const destino = new URL(configuracionUrl, window.location.origin);
        seleccionesConfiguracion.forEach(function(seleccion) {{
            const valores = Array.isArray(seleccion.valor) ? seleccion.valor : [seleccion.valor];
            valores.forEach(function(valor) {{
                destino.searchParams.append(seleccion.parametro, valor);
            }});
        }});
        destino.searchParams.append("cantidad", String(configuracionCantidad));
        window.location.href = destino.pathname + destino.search;
    }}

    function seleccionarOpcionConfiguracion(paso, valor) {{
        seleccionesConfiguracion.push({{parametro: paso.parametro, valor: valor}});
        pasoConfiguracionActual += 1;
        if (pasoConfiguracionActual >= pasosConfiguracion.length) {{
            terminarConfiguracion();
            return;
        }}
        mostrarPasoConfiguracion();
    }}

    function mostrarPasoConfiguracion() {{
        const paso = pasosConfiguracion[pasoConfiguracionActual];
        modalConfiguracionTitulo.textContent = paso.titulo;
        configuracionOpcionesGrid.innerHTML = "";

        if (paso.multiple) {{
            const seleccionadas = new Set();
            paso.opciones.forEach(function(opcion) {{
                const boton = document.createElement("button");
                boton.type = "button";
                const agotada = opcion.disponible === false;
                boton.className = "sabor-btn" + (agotada ? " otro" : "");
                boton.textContent = agotada ? opcion.nombre + " (Agotado)" : opcion.nombre;
                boton.disabled = agotada;
                boton.addEventListener("click", function() {{
                    if (seleccionadas.has(opcion.nombre)) {{
                        seleccionadas.delete(opcion.nombre);
                        boton.classList.remove("activo");
                    }} else {{
                        if (seleccionadas.size >= paso.maximo) {{
                            alert("Maximo " + paso.maximo + " opcion(es) para " + paso.titulo);
                            return;
                        }}
                        seleccionadas.add(opcion.nombre);
                        boton.classList.add("activo");
                    }}
                }});
                configuracionOpcionesGrid.appendChild(boton);
            }});
            const continuar = document.createElement("button");
            continuar.type = "button";
            continuar.className = "sabor-btn combo-aceptar";
            continuar.textContent = "Continuar";
            continuar.addEventListener("click", function() {{
                if (seleccionadas.size < paso.minimo) {{
                    alert("Selecciona al menos " + paso.minimo + " opcion(es) para " + paso.titulo);
                    return;
                }}
                seleccionarOpcionConfiguracion(paso, Array.from(seleccionadas));
            }});
            configuracionOpcionesGrid.appendChild(continuar);
            return;
        }}

        paso.opciones.forEach(function(opcion) {{
            const boton = document.createElement("button");
            boton.type = "button";
            const agotada = opcion.disponible === false;
            boton.className = "sabor-btn" + (agotada ? " otro" : "");
            boton.textContent = agotada ? opcion.nombre + " (Agotado)" : opcion.nombre;
            boton.disabled = agotada;
            boton.addEventListener("click", function() {{
                seleccionarOpcionConfiguracion(paso, opcion.nombre);
            }});
            configuracionOpcionesGrid.appendChild(boton);
        }});
    }}

    function tituloCombo(producto) {{
        const match = (producto || "").match(/(\\d+)/);
        return match ? "COMBO #" + match[1] : (producto || "COMBO");
    }}

    function crearGrupoRadio(titulo, nombre, opciones) {{
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

        opciones.forEach(function(opcion) {{
            const option = document.createElement("option");
            option.value = opcion;
            option.textContent = opcion;
            select.appendChild(option);
        }});
        seccion.appendChild(select);
        return seccion;
    }}

    function crearGrupoExtraLumpia() {{
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

        [botonSinExtra, botonExtra].forEach(function(boton) {{
            boton.addEventListener("click", function() {{
                hidden.value = boton.dataset.valor;
                botonSinExtra.classList.toggle("activo", boton.dataset.valor === "0");
                botonExtra.classList.toggle("activo", boton.dataset.valor === "1");
            }});
            opciones.appendChild(boton);
        }});

        seccion.appendChild(opciones);
        return seccion;
    }}

    function abrirConfiguracionCombo(btn) {{
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

        if (cantidadAcompanantes === 1) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Acompañante", "acompanante_1", acompanantes));
        }} else {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Primer acompañante", "acompanante_1", acompanantes));
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Segundo acompañante", "acompanante_2", acompanantes));
        }}
        configuracionOpcionesGrid.appendChild(crearGrupoRadio("Bebida", "bebida", bebidas));

        const aceptar = document.createElement("button");
        aceptar.type = "button";
        aceptar.className = "sabor-btn combo-aceptar";
        aceptar.textContent = "Aceptar";
        aceptar.addEventListener("click", function() {{
            const destino = new URL(configuracionUrl, window.location.origin);
            for (let i = 1; i <= cantidadAcompanantes; i += 1) {{
                const elegido = configuracionOpcionesGrid.querySelector('select[name="acompanante_' + i + '"]');
                if (!elegido || !elegido.value) {{
                    alert("Debes seleccionar todos los acompañantes");
                    return;
                }}
                destino.searchParams.append("acompanante", elegido.value);
            }}
            const bebida = configuracionOpcionesGrid.querySelector('select[name="bebida"]');
            if (!bebida || !bebida.value) {{
                alert("Debes seleccionar una bebida");
                return;
            }}
            destino.searchParams.append("bebida", bebida.value);
            destino.searchParams.append("cantidad", String(configuracionCantidad));
            window.location.href = destino.pathname + destino.search;
        }});
        configuracionOpcionesGrid.appendChild(aceptar);

        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }}

    function abrirConfiguracion(btn) {{
        configuracionUrl = btn.dataset.url;
        configuracionCantidad = obtenerCantidadDesdeBoton(btn);
        modalConfiguracionProducto.textContent = btn.dataset.producto || "Producto";
        pasosConfiguracion = [];
        seleccionesConfiguracion = [];
        pasoConfiguracionActual = 0;
        configuracionOpcionesGrid.className = "sabores-grid";

        let grupos = [];
        try {{
            grupos = JSON.parse(btn.dataset.modificadores || "[]");
        }} catch (error) {{
            grupos = [];
        }}
        grupos.forEach(function(grupo) {{
            pasosConfiguracion.push({{
                titulo: grupo.nombre,
                parametro: "grupo_" + grupo.id,
                opciones: grupo.opciones,
                multiple: !!grupo.multiple,
                minimo: grupo.minimo || 1,
                maximo: grupo.maximo || 1
            }});
        }});

        if (!pasosConfiguracion.length) {{
            window.location.href = configuracionUrl + "?cantidad=" + configuracionCantidad;
            return;
        }}
        mostrarPasoConfiguracion();
        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }}

    function abrirConfiguracionSelect(btn) {{
        if (btn.dataset.tipo === "combo") {{
            abrirConfiguracionCombo(btn);
            return;
        }}

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

        if (pollos.length) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio("Tipo de pollo", "pollo", pollos));
        }}
        for (let i = 1; i <= cantidadArroces; i += 1) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio(cantidadArroces === 1 ? "Arroz" : "Arroz " + i, "arroz_" + i, arroces));
        }}
        for (let i = 1; i <= cantidadRefrescos; i += 1) {{
            configuracionOpcionesGrid.appendChild(crearGrupoRadio(cantidadRefrescos === 1 ? "Refresco" : "Refresco " + i, "sabor_" + i, sabores));
        }}
        configuracionOpcionesGrid.appendChild(crearGrupoExtraLumpia());

        const aceptar = document.createElement("button");
        aceptar.type = "button";
        aceptar.className = "sabor-btn combo-aceptar";
        aceptar.textContent = "Aceptar";
        aceptar.addEventListener("click", function() {{
            const destino = new URL(configuracionUrl, window.location.origin);
            const campoPollo = configuracionOpcionesGrid.querySelector('select[name="pollo"]');
            if (campoPollo) {{
                if (!campoPollo.value) {{
                    alert("Debes seleccionar un tipo de pollo");
                    campoPollo.focus();
                    return;
                }}
                destino.searchParams.append("pollo", campoPollo.value);
            }}

            for (let i = 1; i <= cantidadArroces; i += 1) {{
                const arroz = configuracionOpcionesGrid.querySelector('select[name="arroz_' + i + '"]');
                if (!arroz || !arroz.value) {{
                    alert("Debes seleccionar todos los arroces");
                    if (arroz) {{
                        arroz.focus();
                    }}
                    return;
                }}
                destino.searchParams.append("arroz", arroz.value);
            }}

            for (let i = 1; i <= cantidadRefrescos; i += 1) {{
                const sabor = configuracionOpcionesGrid.querySelector('select[name="sabor_' + i + '"]');
                if (!sabor || !sabor.value) {{
                    alert("Debes seleccionar todos los refrescos");
                    if (sabor) {{
                        sabor.focus();
                    }}
                    return;
                }}
                let saborFinal = sabor.value;
                if (saborFinal === "Otro") {{
                    saborFinal = prompt("Escribe el sabor del refresco");
                    if (saborFinal === null || !saborFinal.trim()) {{
                        return;
                    }}
                    saborFinal = saborFinal.trim();
                }}
                destino.searchParams.append("sabor", saborFinal);
            }}

            const extraLumpias = configuracionOpcionesGrid.querySelector('input[name="extra_lumpias"]');
            destino.searchParams.append("extra_lumpias", extraLumpias ? extraLumpias.value : "0");
            destino.searchParams.append("cantidad", String(configuracionCantidad));
            window.location.href = destino.pathname + destino.search;
        }});
        configuracionOpcionesGrid.appendChild(aceptar);

        modalConfiguracion.classList.add("activo");
        modalConfiguracion.setAttribute("aria-hidden", "false");
    }}

    document.querySelectorAll(".btn-configurable").forEach(function(btn) {{
        btn.addEventListener("click", function() {{ abrirConfiguracionSelect(btn); }});
    }});
    document.querySelectorAll(".btn-modificadores").forEach(function(btn) {{
        btn.addEventListener("click", function() {{ abrirConfiguracion(btn); }});
    }});
    cerrarModalConfiguracion.addEventListener("click", cerrarConfiguracion);
    modalConfiguracion.addEventListener("click", function(event) {{
        if (event.target === modalConfiguracion) {{ cerrarConfiguracion(); }}
    }});
    </script>
    </body>
    </html>
    """
    return html
