import html
from urllib.parse import urljoin, urlparse

from app.application.self_ordering.links import obtener_link_activo_mesa
from app.application.self_ordering.mesas import MesaSelfOrderingInvalida, etiqueta_mesa
from app.infrastructure.database.self_ordering_links import SqlSelfOrderLinkRepository
from app.shared.qr.svg import qr_svg_data_uri


class ErrorConfiguracionSelfOrdering(ValueError):
    pass


def render_self_ordering_panel(
    orden_id,
    tipo,
    referencia,
    estado,
    cierre_id,
    public_base_url,
    fallback_base_url,
    connection_factory,
    last_id_getter,
):
    if estado != "abierta" or cierre_id is not None:
        return ""
    if (tipo or "").strip().lower() != "mesa":
        return ""
    try:
        mesa_etiqueta = etiqueta_mesa(referencia)
    except MesaSelfOrderingInvalida:
        return ""

    repository = SqlSelfOrderLinkRepository(connection_factory, last_id_getter)
    link = obtener_link_activo_mesa(repository, orden_id)

    if link is None:
        return f"""
        <section class="self-order-panel" id="selfOrderPanel" data-orden-id="{orden_id}">
            <div class="self-order-head">
                <div>
                    <h3>Autoservicio / QR</h3>
                    <p>{html.escape(mesa_etiqueta)} · QR permanente de mesa.</p>
                </div>
                <span class="self-order-pill inactivo">Inactivo</span>
            </div>
            <button class="btn self-order-action" type="button" id="generarSelfOrder">
                Inicializar QR permanente
            </button>
            <div class="delivery-help" id="selfOrderMensaje"></div>
        </section>
        """

    try:
        public_url = self_order_public_url(public_base_url, fallback_base_url, link.token)
        qr_data_uri = qr_svg_data_uri(public_url)
        qr_html = f'<img src="{qr_data_uri}" alt="QR de autoservicio de mesa">'
        config_error = ""
    except ErrorConfiguracionSelfOrdering as exc:
        public_url = ""
        qr_html = "<div class='delivery-alerta'>QR no disponible por configuracion.</div>"
        config_error = f"<div class='delivery-alerta'>{html.escape(str(exc))}</div>"

    return f"""
    <section class="self-order-panel activo" id="selfOrderPanel" data-orden-id="{orden_id}" data-link-id="{link.id}">
        <div class="self-order-head">
            <div>
                <h3>Autoservicio / QR</h3>
                <p>{html.escape(mesa_etiqueta)} · QR permanente reutilizable.</p>
            </div>
            <span class="self-order-pill activo">QR permanente: Activo</span>
        </div>
        <div class="self-order-qr">
            {qr_html}
            <div class="self-order-info">
                {config_error}
                <label>Link interno</label>
                <input id="selfOrderUrl" value="{html.escape(public_url, quote=True)}" readonly>
                <label>Token</label>
                <code>{html.escape(link.token)}</code>
                <div class="self-order-actions">
                    <button class="btn" type="button" id="copiarSelfOrder">Copiar link</button>
                </div>
                <div class="delivery-help" id="selfOrderMensaje"></div>
            </div>
        </div>
    </section>
    """


def self_order_public_url(public_base_url, fallback_base_url, token):
    base = _resolver_base_publica(public_base_url, fallback_base_url)
    return urljoin(base, f"self-order/{token}")


def _resolver_base_publica(public_base_url, fallback_base_url):
    configured = (public_base_url or "").strip()
    if configured:
        parsed = urlparse(configured)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ErrorConfiguracionSelfOrdering("SELF_ORDER_PUBLIC_BASE_URL no es una URL valida.")
        return configured.rstrip("/") + "/"

    fallback = (fallback_base_url or "").strip()
    parsed = urlparse(fallback)
    hostname = (parsed.hostname or "").lower()
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return fallback.rstrip("/") + "/"

    raise ErrorConfiguracionSelfOrdering(
        "Configura SELF_ORDER_PUBLIC_BASE_URL para generar el QR publico."
    )
