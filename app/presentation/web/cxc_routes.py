"""
cxc_routes.py (presentacion)

Blueprint de presentacion de Cuentas por Cobrar / clientes: las rutas
`/clientes*` y `/cuentas_por_cobrar*` que antes vivian directo en
web_app.py con su HTML inline. Las escrituras y lecturas de SQL ya
estaban extraidas a app/infrastructure/database/clientes.py y
app/infrastructure/database/cxc.py (sesiones anteriores) -- este modulo
solo mueve las rutas Flask y sus helpers de render, que eran la ultima
pieza de este dominio que seguia en el monolito.

Varios helpers usados aqui (formato_usd, estilos_base, estilos_admin_cxc,
barra_superior, texto_fecha_corta, monto_formateado_segun_metodo,
obtener_tasa_cobro, ahora_venezuela, a_float) siguen viviendo en
web_app.py porque los usan TAMBIEN otras pantallas (Delivery, facturas)
que no son parte de este dominio -- se reciben inyectados en
`crear_cxc_blueprint` en vez de importarse, para no crear un import
circular con web_app.py y sin duplicar su logica.
"""

import html as html_lib
import json

from flask import Blueprint, redirect, request, session

from app.domain.cxc.descripcion import (
    agrupar_productos,
    etiqueta_tipo_orden,
    texto_descripcion_cxc,
    texto_productos,
)
from app.domain.sales.calculations import TOLERANCIA_COBRO, etiqueta_metodo_pago
from app.shared.constants.system import METODOS_PAGO_VALIDOS
from app.application.cxc.abonos import registrar_abono_cuenta, registrar_pago_masivo_cliente
from app.infrastructure.database.clientes import (
    actualizar_cliente,
    alternar_activo_cliente,
    crear_cliente,
    listar_clientes_admin,
    listar_cuentas_cliente,
    obtener_cliente_admin,
    obtener_resumen_cliente,
)
from app.infrastructure.database.cxc import (
    listar_cuentas_por_cobrar_admin,
    listar_datos_descripcion_cxc,
    listar_movimientos_de_pago_masivo,
    obtener_detalle_cuenta_cxc,
    obtener_pago_masivo_cxc,
    resumen_cuentas_por_cobrar,
)


def estado_cxc_badge(estado):
    estado = (estado or "pendiente").lower()
    clases = {
        "pendiente": "estado-pendiente",
        "pagada": "estado-pagada",
        "anulada": "estado-anulada",
    }
    return (
        f'<span class="badge-estado {clases.get(estado, "estado-anulada")}">'
        f'{html_lib.escape(estado)}</span>'
    )


def tabs_cuentas_por_cobrar(activo):
    items = [
        ("cuentas", "/cuentas_por_cobrar", "Cuentas"),
        ("clientes", "/cuentas_por_cobrar/clientes", "Cartera de clientes"),
    ]
    return (
        '<div class="tabs-cxc">'
        + "".join(
            f'<a class="tab-cxc{" activo" if clave == activo else ""}" href="{url}">{texto}</a>'
            for clave, url, texto in items
        )
        + "</div>"
    )


def opciones_filtro_cliente(filtro_actual):
    opciones = [
        ("todos", "Todos"),
        ("con_saldo", "Con saldo pendiente"),
        ("sin_saldo", "Sin saldo pendiente"),
        ("activos", "Activos"),
        ("inactivos", "Inactivos"),
    ]
    return "".join(
        f'<option value="{valor}"{" selected" if valor == filtro_actual else ""}>{texto}</option>'
        for valor, texto in opciones
    )


def opciones_estado_cxc(estado_actual):
    opciones = [
        ("pendiente", "Pendientes"),
        ("pagada", "Pagadas"),
        ("anulada", "Anuladas"),
        ("todas", "Todas"),
    ]
    return "".join(
        f'<option value="{valor}"{" selected" if valor == estado_actual else ""}>{texto}</option>'
        for valor, texto in opciones
    )


def opciones_metodos_abono(metodo_actual="usd"):
    opciones = []
    for metodo in METODOS_PAGO_VALIDOS:
        etiqueta = etiqueta_metodo_pago(metodo)
        selected = " selected" if metodo == metodo_actual else ""
        opciones.append(f'<option value="{metodo}"{selected}>{html_lib.escape(etiqueta)}</option>')
    return "".join(opciones)


def crear_cxc_blueprint(
    connection_factory,
    last_id_getter,
    ahora_venezuela,
    a_float,
    formato_usd,
    estilos_base,
    estilos_admin_cxc,
    barra_superior,
    texto_fecha_corta,
    monto_formateado_segun_metodo,
    obtener_tasa_cobro,
):
    blueprint = Blueprint("cxc", __name__)

    def descripciones_por_orden(cursor, orden_ids):
        """{orden_id: texto} con la descripcion derivada de la venta origen."""
        datos = listar_datos_descripcion_cxc(cursor, orden_ids)
        return {
            orden_id: texto_descripcion_cxc(
                d["tipo"], d["referencia"], d["observacion"], agrupar_productos(d["productos"])
            )
            for orden_id, d in datos.items()
        }

    def celda_descripcion(descripciones, orden_id):
        texto = descripciones.get(orden_id) or "Sin detalle de la venta"
        return f'<td class="descripcion-cxc">{html_lib.escape(texto)}</td>'

    def formato_bs(monto):
        return f"Bs {a_float(monto):,.2f}"

    def render_form_cliente(cliente=None):
        cliente = cliente or ("", "", "", "", "", 1, "")
        cliente_id = cliente[0] or ""
        titulo = "Nuevo cliente" if not cliente_id else "Editar cliente"
        activo = int(cliente[5] if len(cliente) > 5 else 1)
        opciones_activo = (
            f'<option value="1"{" selected" if activo else ""}>Activo</option>'
            f'<option value="0"{" selected" if not activo else ""}>Inactivo</option>'
        )
        accion_desactivar = ""
        if cliente_id:
            etiqueta = "Desactivar" if activo else "Activar"
            estilo = "btn-danger" if activo else ""
            accion_desactivar = f"""
            <form method="post" action="/cuentas_por_cobrar/clientes/{cliente_id}/activar" style="margin-top:12px;">
                <button type="submit" class="btn-mini {estilo}">{etiqueta}</button>
            </form>
            """

        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
        <body>
        {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuentas por cobrar</h1>
            {tabs_cuentas_por_cobrar("clientes")}
            <h2>{titulo}</h2>
            <div class="card-admin">
                <form method="post" class="form-grid">
                    <div><label>Nombre</label><input name="nombre" required value="{html_lib.escape(cliente[1] or '', quote=True)}"></div>
                    <div><label>Telefono</label><input name="telefono" value="{html_lib.escape(cliente[2] or '', quote=True)}"></div>
                    <div><label>Documento</label><input name="documento" value="{html_lib.escape(cliente[3] or '', quote=True)}"></div>
                    <div><label>Estado</label><select name="activo">{opciones_activo}</select></div>
                    <div class="full"><label>Notas</label><textarea name="notas">{html_lib.escape(cliente[4] or '')}</textarea></div>
                    <div class="acciones full">
                        <button type="submit">Guardar</button>
                        <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes">Cancelar</a>
                    </div>
                </form>
                {accion_desactivar}
            </div>
        </div></body></html>
        """

    def render_form_abono_cxc(cuenta_id, detalle, error="", completo=False, valores=None):
        valores = valores or {}
        c = detalle["cuenta"]
        tasa_actual = None
        try:
            conn = connection_factory()
            cursor = conn.cursor()
            tasa_actual = obtener_tasa_cobro(cursor)
            conn.close()
        except Exception:
            tasa_actual = None

        metodo = valores.get("metodo_pago") or "usd"
        monto_val = valores.get("monto") or (str(round(a_float(c[6]), 2)) if completo else "")
        referencia = valores.get("referencia") or ""
        observacion = valores.get("observacion") or ""
        equivalente_bs = formato_bs(a_float(c[6]) * tasa_actual) if tasa_actual else "Tasa no disponible"
        titulo = "Pagar saldo completo" if completo else "Registrar abono"

        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
        <body>
        {barra_superior('<a href="/cuentas_por_cobrar">Cuentas</a><a href="/cuentas_por_cobrar/clientes">Cartera de clientes</a><a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuentas por cobrar</h1>
            {tabs_cuentas_por_cobrar("cuentas")}
            <h2>{titulo}</h2>
            {"<div class='error'>" + html_lib.escape(error) + "</div>" if error else ""}
            <div class="metricas">
                <div class="metrica"><small>Cliente</small><b>{html_lib.escape(c[3] or c[10] or "-")}</b></div>
                <div class="metrica"><small>Orden origen</small><b>#{html_lib.escape(str(c[13] or c[1]))}</b></div>
                <div class="metrica"><small>Deuda original</small><b>{formato_usd(c[5])}</b></div>
                <div class="metrica"><small>Saldo pendiente</small><b>{formato_usd(c[6])}</b></div>
            </div>
            <div class="card-admin">
                <p><b>Equivalente para pago completo en Bs:</b> {equivalente_bs}</p>
                <form method="post" class="form-grid" id="formAbonoCxc">
                    <div>
                        <label>Metodo de pago</label>
                        <select name="metodo_pago" id="metodo_pago_abono">{opciones_metodos_abono(metodo)}</select>
                    </div>
                    <div>
                        <label>Monto recibido</label>
                        <input name="monto" id="monto_abono" type="number" step="0.01" min="0.01" value="{html_lib.escape(str(monto_val), quote=True)}" required>
                    </div>
                    <div>
                        <label>Referencia</label>
                        <input name="referencia" value="{html_lib.escape(referencia, quote=True)}">
                    </div>
                    <div>
                        <label>Observaci&oacute;n</label>
                        <input name="observacion" value="{html_lib.escape(observacion, quote=True)}">
                    </div>
                    <div class="acciones full">
                        <button type="submit">Confirmar</button>
                        <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/{cuenta_id}">Cancelar</a>
                    </div>
                </form>
            </div>
        </div>
        <script>
        const formAbono = document.getElementById("formAbonoCxc");
        const metodoAbono = document.getElementById("metodo_pago_abono");
        const montoAbono = document.getElementById("monto_abono");
        const saldoActual = {round(a_float(c[6]), 2)};
        const tasaActual = {json.dumps(tasa_actual)};
        function metodoBs(metodo) {{
            return metodo === "punto_venta" || metodo === "bs_pago_movil" || metodo === "bs_efectivo";
        }}
        function numeroAbono(valor) {{
            const n = parseFloat(String(valor || "0").replace(",", "."));
            return Number.isFinite(n) ? n : 0;
        }}
        formAbono.addEventListener("submit", function(event) {{
            const monto = numeroAbono(montoAbono.value);
            let equivalente = monto;
            let mensaje = "Registrar abono de $" + equivalente.toFixed(2) + "\\n";
            if (metodoBs(metodoAbono.value)) {{
                if (!tasaActual || tasaActual <= 0) {{
                    event.preventDefault();
                    alert("No hay una tasa de cambio valida para registrar el abono.");
                    return;
                }}
                equivalente = monto / tasaActual;
                mensaje = "Pago recibido: " + monto.toFixed(2) + " Bs\\nTasa: " + tasaActual.toFixed(2) + " Bs/$\\nAbono equivalente: $" + equivalente.toFixed(2) + "\\n";
            }}
            const nuevoSaldo = Math.max(saldoActual - equivalente, 0);
            mensaje += "Saldo anterior: $" + saldoActual.toFixed(2) + "\\nNuevo saldo: $" + nuevoSaldo.toFixed(2) + "\\nConfirmar?";
            if (!confirm(mensaje)) {{
                event.preventDefault();
            }}
        }});
        </script>
        </body></html>
        """

    def render_form_pago_masivo(cliente, cuentas_pendientes, error="", valores=None, descripciones=None):
        valores = valores or {}
        descripciones = descripciones or {}
        cliente_id = cliente[0]
        total_pendiente = round(sum(a_float(c[5]) for c in cuentas_pendientes), 2)

        filas = ""
        for cuenta in cuentas_pendientes:
            cuenta_id, orden_id, numero, fecha, _original, saldo, _estado, _snapshot = cuenta
            filas += f"""
            <tr>
                <td><label><input type="checkbox" name="cuenta_seleccionada" value="{cuenta_id}"> #{html_lib.escape(str(numero or orden_id))}</label></td>
                {celda_descripcion(descripciones, orden_id)}
                <td>{texto_fecha_corta(fecha)}</td>
                <td class="monto">{formato_usd(saldo)}</td>
                <td><input name="monto_{cuenta_id}" type="number" step="0.01" min="0" placeholder="0.00" class="monto-manual"></td>
            </tr>
            """
        if not filas:
            filas = '<tr><td colspan="5">Este cliente no tiene cuentas pendientes.</td></tr>'

        metodo = valores.get("metodo_pago") or "usd"
        monto_val = valores.get("monto") or ""
        referencia = valores.get("referencia") or ""
        observacion = valores.get("observacion") or ""
        modo = valores.get("modo") or "automatico"

        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}
        .modo-pago-masivo {{ display:flex; gap:16px; margin-bottom:12px; }}
        .monto-manual {{ width:100px; }}
        </style></head>
        <body>
        {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuentas por cobrar</h1>
            {tabs_cuentas_por_cobrar("clientes")}
            <h2>Pago masivo - {html_lib.escape(cliente[1] or '')}</h2>
            {"<div class='error'>" + html_lib.escape(error) + "</div>" if error else ""}
            <div class="metricas">
                <div class="metrica"><small>Saldo pendiente total</small><b>{formato_usd(total_pendiente)}</b></div>
                <div class="metrica"><small>Cuentas pendientes</small><b>{len(cuentas_pendientes)}</b></div>
            </div>
            <div class="card-admin">
                <form method="post" id="formPagoMasivo">
                    <div class="modo-pago-masivo">
                        <label><input type="radio" name="modo" value="automatico" {"checked" if modo == "automatico" else ""}> Automatico (deuda mas antigua primero)</label>
                        <label><input type="radio" name="modo" value="manual" {"checked" if modo == "manual" else ""}> Seleccion manual</label>
                    </div>
                    <div class="form-grid">
                        <div>
                            <label>Metodo de pago</label>
                            <select name="metodo_pago">{opciones_metodos_abono(metodo)}</select>
                        </div>
                        <div>
                            <label>Monto recibido (total del pago)</label>
                            <input name="monto" type="number" step="0.01" min="0.01" value="{html_lib.escape(str(monto_val), quote=True)}" required>
                        </div>
                        <div>
                            <label>Referencia</label>
                            <input name="referencia" value="{html_lib.escape(referencia, quote=True)}">
                        </div>
                        <div>
                            <label>Observaci&oacute;n</label>
                            <input name="observacion" value="{html_lib.escape(observacion, quote=True)}">
                        </div>
                    </div>
                    <table>
                        <thead><tr><th>Cuenta</th><th>Generada</th><th>Pendiente</th><th>Monto a aplicar (modo manual)</th></tr></thead>
                        <tbody>{filas}</tbody>
                    </table>
                    <div class="acciones full" style="margin-top:12px;">
                        <button type="submit">Confirmar pago masivo</button>
                        <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes/{cliente_id}">Cancelar</a>
                    </div>
                </form>
            </div>
        </div>
        <script>
        const radiosModo = document.querySelectorAll('input[name="modo"]');
        function actualizarModoPagoMasivo() {{
            const manual = document.querySelector('input[name="modo"]:checked').value === "manual";
            document.querySelectorAll('.monto-manual').forEach(function(input) {{ input.disabled = !manual; }});
        }}
        radiosModo.forEach(function(radio) {{ radio.addEventListener("change", actualizarModoPagoMasivo); }});
        actualizarModoPagoMasivo();
        </script>
        </body></html>
        """

    def render_resultado_pago_masivo(pago_masivo, movimientos):
        (
            pago_id, _cliente_id, metodo_pago, _moneda_pago, _monto_pago, _tasa,
            referencia, observacion, fecha, _usuario_id, monto_total, monto_aplicado, monto_sobrante,
        ) = pago_masivo

        filas = "".join(
            f"<tr><td>#{html_lib.escape(str(orden_id))}</td><td class='monto'>{formato_usd(-monto_saldo)}</td><td>{texto_fecha_corta(mov_fecha)}</td></tr>"
            for _mov_id, _cuenta_id, orden_id, monto_saldo, mov_fecha in movimientos
        )

        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
        <body>
        {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuentas por cobrar</h1>
            {tabs_cuentas_por_cobrar("clientes")}
            <h2>Pago masivo #{pago_id} registrado</h2>
            <div class="metricas">
                <div class="metrica"><small>Metodo</small><b>{html_lib.escape(etiqueta_metodo_pago(metodo_pago))}</b></div>
                <div class="metrica"><small>Monto total recibido</small><b>{formato_usd(monto_total)}</b></div>
                <div class="metrica"><small>Monto aplicado</small><b>{formato_usd(monto_aplicado)}</b></div>
                <div class="metrica"><small>Sobrante no aplicado</small><b>{formato_usd(monto_sobrante)}</b></div>
            </div>
            <div class="card-admin">
                <p><b>Referencia:</b> {html_lib.escape(referencia or '-')}</p>
                <p><b>Observaci&oacute;n:</b> {html_lib.escape(observacion or '-')}</p>
                <p><b>Fecha:</b> {texto_fecha_corta(fecha)}</p>
                <h3>Distribucion por cuenta</h3>
                <table>
                    <thead><tr><th>Orden</th><th>Monto aplicado</th><th>Fecha</th></tr></thead>
                    <tbody>{filas or "<tr><td colspan='3'>Sin movimientos.</td></tr>"}</tbody>
                </table>
            </div>
            <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes">Volver a cartera</a>
        </div></body></html>
        """

    @blueprint.route("/clientes")
    @blueprint.route("/cuentas_por_cobrar/clientes")
    def clientes():
        if request.path == "/clientes":
            return redirect("/cuentas_por_cobrar/clientes")

        conn = connection_factory()
        cursor = conn.cursor()
        busqueda = (request.args.get("q") or "").strip()
        filtro = (request.args.get("filtro") or "todos").strip().lower()
        clientes_rows = listar_clientes_admin(cursor, busqueda, filtro)
        conn.close()

        filas = ""
        for row in clientes_rows:
            cliente_id, nombre, telefono, documento, activo, saldo, cuentas, pagadas = row
            estado = "Activo" if activo else "Inactivo"
            filas += f"""
            <tr>
                <td><b>{html_lib.escape(nombre or '')}</b></td>
                <td>{html_lib.escape(telefono or '-')}</td>
                <td>{html_lib.escape(documento or '-')}</td>
                <td>{estado}</td>
                <td class="monto">{formato_usd(saldo)}</td>
                <td class="monto">{int(cuentas or 0)}</td>
                <td class="acciones">
                    <a class="btn-mini" href="/cuentas_por_cobrar/clientes/{cliente_id}">Ver</a>
                    <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes/{cliente_id}/editar">Editar</a>
                </td>
            </tr>
            """
        if not filas:
            filas = '<tr><td colspan="7">No hay clientes para este filtro.</td></tr>'

        return f"""
        <html>
        <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
        <body>
        {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuentas por cobrar</h1>
            {tabs_cuentas_por_cobrar("clientes")}
            <h2>Cartera de clientes</h2>
            <div class="card-admin">
                <form method="get" class="toolbar">
                    <div><label>Buscar</label><input name="q" value="{html_lib.escape(busqueda, quote=True)}" placeholder="Nombre, telefono o documento"></div>
                    <div><label>Filtro</label><select name="filtro">{opciones_filtro_cliente(filtro)}</select></div>
                    <button type="submit">Buscar</button>
                    <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes">Limpiar</a>
                    <a class="btn-mini" href="/cuentas_por_cobrar/clientes/nuevo">Nuevo cliente</a>
                </form>
            </div>
            <div class="card-admin">
                <table>
                    <thead><tr><th>Cliente</th><th>Telefono</th><th>Documento</th><th>Estado</th><th>Saldo pendiente</th><th>Cuentas</th><th>Acciones</th></tr></thead>
                    <tbody>{filas}</tbody>
                </table>
            </div>
        </div></body></html>
        """

    @blueprint.route("/clientes/nuevo", methods=["GET", "POST"])
    @blueprint.route("/cuentas_por_cobrar/clientes/nuevo", methods=["GET", "POST"])
    def crear_cliente_route():
        if request.method == "POST":
            nombre = (request.form.get("nombre") or "").strip()
            telefono = (request.form.get("telefono") or "").strip()
            documento = (request.form.get("documento") or "").strip()
            notas = (request.form.get("notas") or "").strip()
            activo = 1 if request.form.get("activo", "1") == "1" else 0
            if not nombre:
                return "El nombre del cliente es obligatorio", 400
            conn = connection_factory()
            cursor = conn.cursor()
            cliente_id = crear_cliente(
                cursor,
                nombre,
                telefono,
                documento,
                notas,
                activo,
                ahora_venezuela().strftime("%Y-%m-%d %H:%M:%S"),
                last_id_getter,
            )
            conn.commit()
            conn.close()
            return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")

        return render_form_cliente()

    @blueprint.route("/clientes/<int:cliente_id>")
    @blueprint.route("/cuentas_por_cobrar/clientes/<int:cliente_id>")
    def detalle_cliente(cliente_id):
        if request.path.startswith("/clientes/"):
            return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")

        conn = connection_factory()
        cursor = conn.cursor()
        cliente = obtener_cliente_admin(cursor, cliente_id)
        if not cliente:
            conn.close()
            return "Cliente no encontrado", 404
        resumen = obtener_resumen_cliente(cursor, cliente_id)
        cuentas = listar_cuentas_cliente(cursor, cliente_id)
        descripciones = descripciones_por_orden(cursor, [c[1] for c in cuentas])
        conn.close()

        filas = ""
        for cuenta in cuentas:
            cuenta_id, orden_id, numero, fecha, original, saldo, estado, snapshot = cuenta
            filas += f"""
            <tr>
                <td><a href="/cuentas_por_cobrar/{cuenta_id}">#{html_lib.escape(str(numero or orden_id))}</a></td>
                {celda_descripcion(descripciones, orden_id)}
                <td>{texto_fecha_corta(fecha)}</td>
                <td class="monto">{formato_usd(original)}</td>
                <td class="monto">{formato_usd(saldo)}</td>
                <td>{estado_cxc_badge(estado)}</td>
                <td>{html_lib.escape(snapshot or '')}</td>
            </tr>
            """
        if not filas:
            filas = '<tr><td colspan="7">Este cliente no tiene cuentas por cobrar.</td></tr>'

        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
        <body>
        {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuentas por cobrar</h1>
            {tabs_cuentas_por_cobrar("clientes")}
            <h1>{html_lib.escape(cliente[1] or '')}</h1>
            <div class="acciones" style="margin-bottom:12px;">
                <a class="btn-mini" href="/cuentas_por_cobrar/clientes/{cliente_id}/editar">Editar cliente</a>
                {f'<a class="btn-mini" href="/cuentas_por_cobrar/clientes/{cliente_id}/pago_masivo">Pago masivo</a>' if resumen["cuentas_pendientes"] else ""}
                <a class="btn-mini btn-sec" href="/cuentas_por_cobrar?cliente_id={cliente_id}&estado=todas">Ver sus cuentas</a>
                <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/clientes">Volver a cartera</a>
            </div>
            <div class="card-admin">
                <h2>Datos</h2>
                <p><b>Telefono:</b> {html_lib.escape(cliente[2] or '-')}</p>
                <p><b>Documento:</b> {html_lib.escape(cliente[3] or '-')}</p>
                <p><b>Notas:</b> {html_lib.escape(cliente[4] or '-')}</p>
                <p><b>Estado:</b> {'Activo' if cliente[5] else 'Inactivo'}</p>
            </div>
            <div class="metricas">
                <div class="metrica"><small>Saldo pendiente</small><b>{formato_usd(resumen["saldo_pendiente"])}</b></div>
                <div class="metrica"><small>Cuentas pendientes</small><b>{resumen["cuentas_pendientes"]}</b></div>
                <div class="metrica"><small>Cuentas pagadas</small><b>{resumen["cuentas_pagadas"]}</b></div>
                <div class="metrica"><small>Deuda historica</small><b>{formato_usd(resumen["total_deuda_generada"])}</b></div>
            </div>
            <div class="card-admin">
                <h2>Cuentas por cobrar</h2>
                <table>
                    <thead><tr><th>Orden</th><th>Descripción</th><th>Generada</th><th>Original</th><th>Pendiente</th><th>Estado</th><th>Snapshot cliente</th></tr></thead>
                    <tbody>{filas}</tbody>
                </table>
            </div>
        </div></body></html>
        """

    def _cuentas_pendientes_cliente_ordenadas(cursor, cliente_id):
        cuentas = [c for c in listar_cuentas_cliente(cursor, cliente_id) if c[6] == "pendiente" and a_float(c[5]) > 0]
        cuentas.sort(key=lambda c: (c[3] or "", c[0]))
        return cuentas

    @blueprint.route("/clientes/<int:cliente_id>/pago_masivo", methods=["GET", "POST"])
    @blueprint.route("/cuentas_por_cobrar/clientes/<int:cliente_id>/pago_masivo", methods=["GET", "POST"])
    def pago_masivo_cliente(cliente_id):
        if request.path.startswith("/clientes/"):
            return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}/pago_masivo")

        conn = connection_factory()
        cursor = conn.cursor()
        cliente = obtener_cliente_admin(cursor, cliente_id)
        if not cliente:
            conn.close()
            return "Cliente no encontrado", 404

        if request.method == "GET":
            cuentas_pendientes = _cuentas_pendientes_cliente_ordenadas(cursor, cliente_id)
            descripciones = descripciones_por_orden(cursor, [c[1] for c in cuentas_pendientes])
            conn.close()
            return render_form_pago_masivo(cliente, cuentas_pendientes, descripciones=descripciones)

        modo = request.form.get("modo", "automatico")
        cuentas_manual = []
        if modo == "manual":
            for cuenta_id_str in request.form.getlist("cuenta_seleccionada"):
                monto_str = request.form.get(f"monto_{cuenta_id_str}", "")
                if not monto_str:
                    continue
                try:
                    cuentas_manual.append((int(cuenta_id_str), a_float(monto_str)))
                except ValueError:
                    continue

        valores = {
            "metodo_pago": request.form.get("metodo_pago", ""),
            "monto": request.form.get("monto", ""),
            "referencia": request.form.get("referencia", ""),
            "observacion": request.form.get("observacion", ""),
            "modo": modo,
        }
        try:
            resultado = registrar_pago_masivo_cliente(
                cursor,
                cliente_id=cliente_id,
                metodo_pago=valores["metodo_pago"],
                monto_recibido=valores["monto"],
                modo=modo,
                cuentas_manual=cuentas_manual,
                referencia=valores["referencia"],
                observacion=valores["observacion"],
                usuario_id=session.get("usuario_id"),
                obtener_tasa_cobro=obtener_tasa_cobro,
                ahora_venezuela=ahora_venezuela,
                formato_usd=formato_usd,
                obtener_ultimo_id=last_id_getter,
            )
            conn.commit()
            conn.close()
            return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}/pago_masivo/{resultado['pago_masivo_id']}")
        except ValueError as exc:
            conn.rollback()
            cuentas_pendientes = _cuentas_pendientes_cliente_ordenadas(cursor, cliente_id)
            descripciones = descripciones_por_orden(cursor, [c[1] for c in cuentas_pendientes])
            conn.close()
            return render_form_pago_masivo(
                cliente, cuentas_pendientes, error=str(exc), valores=valores, descripciones=descripciones
            ), 400
        except Exception:
            conn.rollback()
            conn.close()
            raise

    @blueprint.route("/clientes/<int:cliente_id>/pago_masivo/<int:pago_masivo_id>")
    @blueprint.route("/cuentas_por_cobrar/clientes/<int:cliente_id>/pago_masivo/<int:pago_masivo_id>")
    def resultado_pago_masivo(cliente_id, pago_masivo_id):
        if request.path.startswith("/clientes/"):
            return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}/pago_masivo/{pago_masivo_id}")

        conn = connection_factory()
        cursor = conn.cursor()
        pago_masivo = obtener_pago_masivo_cxc(cursor, pago_masivo_id)
        if not pago_masivo or pago_masivo[1] != cliente_id:
            conn.close()
            return "Pago masivo no encontrado", 404
        movimientos = listar_movimientos_de_pago_masivo(cursor, pago_masivo_id)
        conn.close()
        return render_resultado_pago_masivo(pago_masivo, movimientos)

    @blueprint.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
    @blueprint.route("/cuentas_por_cobrar/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
    def editar_cliente(cliente_id):
        conn = connection_factory()
        cursor = conn.cursor()
        cliente = obtener_cliente_admin(cursor, cliente_id)
        if not cliente:
            conn.close()
            return "Cliente no encontrado", 404

        if request.method == "POST":
            nombre = (request.form.get("nombre") or "").strip()
            telefono = (request.form.get("telefono") or "").strip()
            documento = (request.form.get("documento") or "").strip()
            notas = (request.form.get("notas") or "").strip()
            activo = 1 if request.form.get("activo", "1") == "1" else 0
            if not nombre:
                conn.close()
                return "El nombre del cliente es obligatorio", 400
            actualizar_cliente(cursor, cliente_id, nombre, telefono, documento, notas, activo)
            conn.commit()
            conn.close()
            return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")

        conn.close()
        return render_form_cliente(cliente)

    @blueprint.route("/clientes/<int:cliente_id>/activar", methods=["POST"])
    @blueprint.route("/cuentas_por_cobrar/clientes/<int:cliente_id>/activar", methods=["POST"])
    def activar_cliente(cliente_id):
        conn = connection_factory()
        cursor = conn.cursor()
        try:
            alternar_activo_cliente(cursor, cliente_id)
        except ValueError as exc:
            conn.close()
            return str(exc), 404
        conn.commit()
        conn.close()
        return redirect(f"/cuentas_por_cobrar/clientes/{cliente_id}")

    @blueprint.route("/cuentas_por_cobrar")
    @blueprint.route("/cuentas_por_cobrar/cuentas")
    def cuentas_por_cobrar_admin():
        conn = connection_factory()
        cursor = conn.cursor()
        busqueda = (request.args.get("q") or "").strip()
        estado = (request.args.get("estado") or "pendiente").strip().lower()
        cliente_id = (request.args.get("cliente_id") or "").strip()
        resumen = resumen_cuentas_por_cobrar(cursor)
        cuentas = listar_cuentas_por_cobrar_admin(cursor, busqueda, estado, cliente_id)
        descripciones = descripciones_por_orden(cursor, [row[6] for row in cuentas])
        clientes_filtro = listar_clientes_admin(cursor, "", "todos")
        conn.close()

        opciones_cliente = ['<option value="">Todos los clientes</option>']
        for cliente in clientes_filtro:
            selected = " selected" if str(cliente[0]) == cliente_id else ""
            opciones_cliente.append(
                f'<option value="{cliente[0]}"{selected}>{html_lib.escape(cliente[1] or "")}</option>'
            )

        filas = ""
        for row in cuentas:
            cuenta_id, cli_id, snapshot, nombre_actual, telefono, documento, orden_id, numero, fecha, original, saldo, estado_row = row
            cliente_texto = snapshot or nombre_actual or "Cliente"
            filas += f"""
            <tr>
                <td><a href="/cuentas_por_cobrar/clientes/{cli_id}">{html_lib.escape(cliente_texto)}</a><br><small>{html_lib.escape(telefono or documento or '')}</small></td>
                <td>#{html_lib.escape(str(numero or orden_id))}</td>
                {celda_descripcion(descripciones, orden_id)}
                <td>{texto_fecha_corta(fecha)}</td>
                <td class="monto">{formato_usd(original)}</td>
                <td class="monto">{formato_usd(saldo)}</td>
                <td>{estado_cxc_badge(estado_row)}</td>
                <td><a class="btn-mini" href="/cuentas_por_cobrar/{cuenta_id}">Ver</a></td>
            </tr>
            """
        if not filas:
            filas = '<tr><td colspan="8">No hay cuentas por cobrar para este filtro.</td></tr>'

        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
        <body>
        {barra_superior('<a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuentas por cobrar</h1>
            {tabs_cuentas_por_cobrar("cuentas")}
            <div class="metricas">
                <div class="metrica"><small>Saldo total pendiente</small><b>{formato_usd(resumen["saldo_total"])}</b></div>
                <div class="metrica"><small>Clientes con deuda</small><b>{resumen["clientes_con_deuda"]}</b></div>
                <div class="metrica"><small>Cuentas pendientes</small><b>{resumen["cuentas_pendientes"]}</b></div>
                <div class="metrica"><small>Cuentas pagadas</small><b>{resumen["cuentas_pagadas"]}</b></div>
            </div>
            {f'''
            <div class="card-admin">
                <form method="get" class="toolbar">
                    <div><label>Buscar</label><input name="q" value="{html_lib.escape(busqueda, quote=True)}" placeholder="Cliente, orden, telefono o documento"></div>
                    <div><label>Estado</label><select name="estado">{opciones_estado_cxc(estado)}</select></div>
                    <div><label>Cliente</label><select name="cliente_id">{''.join(opciones_cliente)}</select></div>
                    <button type="submit">Filtrar</button>
                    <a class="btn-mini btn-sec" href="/cuentas_por_cobrar">Limpiar</a>
                </form>
            </div>
            <div class="card-admin">
                <h2>Cuentas</h2>
                <table>
                    <thead><tr><th>Cliente</th><th>Orden</th><th>Descripción</th><th>Generada</th><th>Original</th><th>Pendiente</th><th>Estado</th><th>Accion</th></tr></thead>
                    <tbody>{filas}</tbody>
                </table>
            </div>
            '''}
        </div></body></html>
        """

    @blueprint.route("/cuentas_por_cobrar/<int:cuenta_id>")
    def detalle_cuenta_por_cobrar(cuenta_id):
        conn = connection_factory()
        cursor = conn.cursor()
        detalle = obtener_detalle_cuenta_cxc(cursor, cuenta_id)
        venta = None
        if detalle:
            orden_origen = detalle["cuenta"][1]
            venta = listar_datos_descripcion_cxc(cursor, [orden_origen]).get(orden_origen)
        conn.close()
        if not detalle:
            return "Cuenta por cobrar no encontrada", 404

        c = detalle["cuenta"]
        venta = venta or {"tipo": None, "referencia": None, "observacion": None, "productos": []}
        productos_venta = agrupar_productos(venta["productos"])
        descripcion_venta = texto_descripcion_cxc(
            venta["tipo"], venta["referencia"], venta["observacion"], productos_venta
        )
        tipo_venta = " · ".join(
            parte
            for parte in (etiqueta_tipo_orden(venta["tipo"]), (venta["referencia"] or "").strip())
            if parte and parte != "-"
        )
        observacion_venta = (venta["observacion"] or "").strip() or "-"
        movimientos = ""
        for mov in detalle["movimientos"]:
            fecha, tipo, monto_saldo, moneda_pago, monto_pago, tasa_mov, metodo, referencia, usuario, observacion = mov
            signo = "+" if a_float(monto_saldo) > 0 else ""
            movimientos += f"""
            <tr>
                <td>{texto_fecha_corta(fecha)}</td>
                <td>{html_lib.escape(tipo or '')}</td>
                <td class="monto">{signo}{formato_usd(monto_saldo)}</td>
                <td>{html_lib.escape(moneda_pago or '-')}</td>
                <td class="monto">{monto_formateado_segun_metodo(metodo, monto_pago) if monto_pago is not None else '-'}</td>
                <td>{a_float(tasa_mov) if tasa_mov else '-'}</td>
                <td>{html_lib.escape(etiqueta_metodo_pago(metodo))}</td>
                <td>{html_lib.escape(referencia or '-')}</td>
                <td>{html_lib.escape(usuario or '-')}</td>
                <td>{html_lib.escape(observacion or '-')}</td>
            </tr>
            """
        if not movimientos:
            movimientos = '<tr><td colspan="10">No hay movimientos registrados.</td></tr>'

        alerta = ""
        if detalle["inconsistente"]:
            print(
                f"[CXC INCONSISTENTE] cuenta_id={c[0]} saldo={c[6]} suma_movimientos={detalle['suma_movimientos']}"
            )
            alerta = (
                '<div class="nota-alerta">Atencion: el saldo cacheado no coincide con '
                'la suma de movimientos. Revisar administrativamente.</div>'
            )

        numero_orden = c[13] or c[1]
        pagado = detalle["pagado_inicial"]
        fecha_venta = c[14] or c[7]
        acciones_abono = ""
        if not detalle["inconsistente"] and c[8] == "pendiente" and a_float(c[6]) > TOLERANCIA_COBRO:
            acciones_abono = f"""
            <div class="card-admin">
                <h2>Acciones</h2>
                <div class="acciones">
                    <a class="btn-mini" href="/cuentas_por_cobrar/{cuenta_id}/abono">Registrar abono</a>
                    <a class="btn-mini btn-sec" href="/cuentas_por_cobrar/{cuenta_id}/abono?completo=1">Pagar saldo completo</a>
                </div>
            </div>
            """
        elif c[8] == "pagada" or a_float(c[6]) <= TOLERANCIA_COBRO:
            acciones_abono = '<div class="card-admin"><h2>Cuenta pagada</h2><p>No hay saldo pendiente para abonar.</p></div>'
        return f"""
        <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>{estilos_base()}{estilos_admin_cxc()}</style></head>
        <body>
        {barra_superior('<a href="/cuentas_por_cobrar">Cuentas por cobrar</a><a href="/">Inicio</a>')}
        <div class="contenido">
            <h1>Cuenta por cobrar #{cuenta_id}</h1>
            {tabs_cuentas_por_cobrar("cuentas")}
            {alerta}
            <div class="descripcion-cxc-destacada"><small>Descripción</small>{html_lib.escape(descripcion_venta)}</div>
            <div class="acciones" style="margin-bottom:12px;">
                <a class="btn-mini" href="/cuentas_por_cobrar/clientes/{c[2]}">Ver cliente</a>
                <a class="btn-mini btn-sec" href="/cuentas_por_cobrar">Volver a cuentas</a>
                <a class="btn-mini btn-sec" href="/orden/{c[1]}">Ver orden</a>
            </div>
            <div class="metricas">
                <div class="metrica"><small>Valor de venta</small><b>{formato_usd(c[19])}</b></div>
                <div class="metrica"><small>Cobrado al cerrar</small><b>{formato_usd(pagado["usd"])}</b></div>
                <div class="metrica"><small>Deuda generada</small><b>{formato_usd(c[5])}</b></div>
                <div class="metrica"><small>Saldo actual</small><b>{formato_usd(c[6])}</b></div>
            </div>
            {acciones_abono}
            <div class="card-admin">
                <h2>Cliente</h2>
                <p><b>Snapshot:</b> {html_lib.escape(c[3] or '')}</p>
                <p><b>Nombre actual:</b> {html_lib.escape(c[10] or '-')}</p>
                <p><b>Telefono:</b> {html_lib.escape(c[11] or '-')}</p>
                <p><b>Documento:</b> {html_lib.escape(c[12] or '-')}</p>
            </div>
            <div class="card-admin">
                <h2>Venta origen</h2>
                <p><b>Orden:</b> #{html_lib.escape(str(numero_orden))}</p>
                <p><b>Tipo:</b> {html_lib.escape(tipo_venta or '-')}</p>
                <p><b>Productos:</b> {html_lib.escape(texto_productos(productos_venta) or '-')}</p>
                <p><b>Observación de la orden:</b> {html_lib.escape(observacion_venta)}</p>
                <p><b>Fecha de venta:</b> {texto_fecha_corta(fecha_venta)}</p>
                <p><b>Total original de venta:</b> {formato_usd(c[19])} / {formato_bs(c[20])}</p>
                <p><b>Pagado al momento:</b> {formato_usd(pagado["usd"])} / {formato_bs(pagado["bs"])}</p>
                <p><b>Tasa historica:</b> {a_float(c[16])}</p>
            </div>
            <div class="card-admin">
                <h2>Estado actual</h2>
                <p><b>Deuda original:</b> {formato_usd(c[5])}</p>
                <p><b>Saldo pendiente:</b> {formato_usd(c[6])}</p>
                <p><b>Suma movimientos:</b> {formato_usd(detalle["suma_movimientos"])}</p>
                <p><b>Estado:</b> {estado_cxc_badge(c[8])}</p>
            </div>
            <div class="card-admin">
                <h2>Movimientos</h2>
                <table>
                    <thead><tr><th>Fecha</th><th>Tipo</th><th>Monto saldo</th><th>Moneda pago</th><th>Monto pago</th><th>Tasa</th><th>Metodo</th><th>Referencia</th><th>Usuario</th><th>Observacion</th></tr></thead>
                    <tbody>{movimientos}</tbody>
                </table>
            </div>
        </div></body></html>
        """

    @blueprint.route("/cuentas_por_cobrar/<int:cuenta_id>/abono", methods=["GET", "POST"])
    def registrar_abono_cxc(cuenta_id):
        conn = connection_factory()
        cursor = conn.cursor()
        detalle = obtener_detalle_cuenta_cxc(cursor, cuenta_id)
        if not detalle:
            conn.close()
            return "Cuenta por cobrar no encontrada", 404

        completo = request.args.get("completo") == "1"
        if request.method == "GET":
            conn.close()
            return render_form_abono_cxc(cuenta_id, detalle, completo=completo)

        valores = {
            "metodo_pago": request.form.get("metodo_pago", ""),
            "monto": request.form.get("monto", ""),
            "referencia": request.form.get("referencia", ""),
            "observacion": request.form.get("observacion", ""),
        }
        try:
            registrar_abono_cuenta(
                cursor,
                cuenta_id,
                valores["metodo_pago"],
                valores["monto"],
                valores["referencia"],
                valores["observacion"],
                session.get("usuario_id"),
                obtener_tasa_cobro,
                ahora_venezuela,
                formato_usd,
            )
            conn.commit()
            conn.close()
            return redirect(f"/cuentas_por_cobrar/{cuenta_id}")
        except ValueError as exc:
            conn.rollback()
            detalle = obtener_detalle_cuenta_cxc(cursor, cuenta_id)
            conn.close()
            return render_form_abono_cxc(cuenta_id, detalle, error=str(exc), completo=completo, valores=valores), 400
        except Exception:
            conn.rollback()
            conn.close()
            raise

    return blueprint
