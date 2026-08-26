import html

from flask import Blueprint, jsonify, request

from app.application.self_ordering.links import (
    OrdenSelfOrderingArchivada,
    OrdenSelfOrderingCerrada,
    OrdenSelfOrderingNoExiste,
    obtener_o_crear_link_mesa,
    revocar_link_mesa_de_orden,
    validar_self_order_link,
)
from app.infrastructure.database.self_ordering_links import SqlSelfOrderLinkRepository
from app.presentation.web.self_ordering_ui import (
    ErrorConfiguracionSelfOrdering,
    self_order_public_url,
)
from app.shared.qr.svg import qr_svg_data_uri


def crear_self_ordering_blueprint(connection_factory, last_id_getter, public_base_url_getter=None):
    blueprint = Blueprint("self_ordering", __name__)

    def repository():
        return SqlSelfOrderLinkRepository(connection_factory, last_id_getter)

    def public_base_url():
        if public_base_url_getter is None:
            return ""
        return public_base_url_getter() or ""

    def resolver_url_publica(token):
        return self_order_public_url(public_base_url(), request.host_url, token)

    @blueprint.post("/orden/<int:orden_id>/self-ordering/link")
    def crear_o_obtener_link_mesa(orden_id):
        try:
            resolver_url_publica("token-config-check")
            link, creado = obtener_o_crear_link_mesa(repository(), orden_id)
        except OrdenSelfOrderingNoExiste as exc:
            return jsonify({"error": str(exc)}), 404
        except (OrdenSelfOrderingArchivada, OrdenSelfOrderingCerrada) as exc:
            return jsonify({"error": str(exc)}), 409
        except ErrorConfiguracionSelfOrdering as exc:
            return jsonify({"error": str(exc)}), 503

        return jsonify({"link": _link_to_json(link, resolver_url_publica), "creado": creado})

    @blueprint.post("/orden/<int:orden_id>/self-ordering/link/<int:link_id>/revocar")
    def revocar_link_mesa(orden_id, link_id):
        try:
            resolver_url_publica("token-config-check")
            revocado = revocar_link_mesa_de_orden(repository(), orden_id, link_id)
        except OrdenSelfOrderingNoExiste as exc:
            return jsonify({"error": str(exc)}), 404
        except (OrdenSelfOrderingArchivada, OrdenSelfOrderingCerrada) as exc:
            return jsonify({"error": str(exc)}), 409
        except ErrorConfiguracionSelfOrdering as exc:
            return jsonify({"error": str(exc)}), 503

        if not revocado:
            return jsonify({"error": "Link no encontrado para esta orden."}), 404

        link = repository().buscar_por_id(link_id)
        return jsonify({"link": _link_to_json(link, resolver_url_publica), "revocado": True})

    @blueprint.get("/self-order/<token>")
    def self_order_publico(token):
        resultado = validar_self_order_link(repository(), token)
        if not resultado.valido:
            return _respuesta_publica_bloqueada(resultado.estado), 404

        return (
            """
            <!doctype html>
            <html lang="es">
            <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
            <body style="font-family:Arial,sans-serif;background:#0F1115;color:#F8F9FA;margin:0;padding:28px;">
                <main style="max-width:560px;margin:0 auto;">
                    <h1>Autoservicio NekoPOS</h1>
                    <p>Este enlace de autoservicio esta activo.</p>
                    <p>El menu estara disponible proximamente.</p>
                </main>
            </body>
            </html>
            """,
            200,
        )

    return blueprint


def _link_to_json(link, public_url_builder):
    public_url = public_url_builder(link.token)
    return {
        "id": link.id,
        "token": link.token,
        "public_url": public_url,
        "qr_svg": qr_svg_data_uri(public_url),
        "canal": link.canal,
        "estado": link.estado,
        "fecha_creacion": link.fecha_creacion,
        "fecha_expiracion": link.fecha_expiracion,
    }


def _respuesta_publica_bloqueada(estado):
    estado_seguro = html.escape(estado or "invalido")
    return f"""
    <!doctype html>
    <html lang="es">
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="font-family:Arial,sans-serif;background:#0F1115;color:#F8F9FA;margin:0;padding:28px;">
        <main style="max-width:560px;margin:0 auto;">
            <h1>Enlace no disponible</h1>
            <p>Este enlace de autoservicio no esta disponible.</p>
            <p>Estado: {estado_seguro}</p>
        </main>
    </body>
    </html>
    """
