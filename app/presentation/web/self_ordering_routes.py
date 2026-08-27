import html

from flask import Blueprint, jsonify, request

from app.application.self_ordering.catalog import construir_catalogo_self_ordering
from app.application.self_ordering.links import (
    ESTADO_MESA_NO_HABILITADA,
    OrdenSelfOrderingArchivada,
    OrdenSelfOrderingCerrada,
    OrdenSelfOrderingNoExiste,
    MesaSelfOrderingOcupada,
    obtener_o_crear_link_mesa,
    revocar_link_mesa_de_orden,
    validar_self_order_link_para_catalogo,
)
from app.application.self_ordering.mesas import MesaSelfOrderingInvalida
from app.infrastructure.database.self_ordering_catalog import SqlSelfOrderingCatalogRepository
from app.infrastructure.database.self_ordering_links import SqlSelfOrderLinkRepository
from app.presentation.web.self_ordering_catalog_view import render_catalogo_publico
from app.presentation.web.self_ordering_ui import (
    ErrorConfiguracionSelfOrdering,
    self_order_public_url,
)
from app.shared.qr.svg import qr_svg_data_uri


def crear_self_ordering_blueprint(
    connection_factory,
    last_id_getter,
    public_base_url_getter=None,
    catalog_rules_getter=None,
):
    blueprint = Blueprint("self_ordering", __name__)

    def repository():
        return SqlSelfOrderLinkRepository(connection_factory, last_id_getter)

    def catalog_repository():
        return SqlSelfOrderingCatalogRepository(connection_factory)

    def catalog_rules():
        if catalog_rules_getter is None:
            raise RuntimeError("Reglas de catalogo self-ordering no configuradas.")
        return catalog_rules_getter()

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
        except MesaSelfOrderingInvalida as exc:
            return jsonify({"error": str(exc)}), 400
        except MesaSelfOrderingOcupada as exc:
            return jsonify({"error": str(exc)}), 409
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
        except MesaSelfOrderingInvalida as exc:
            return jsonify({"error": str(exc)}), 400
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
        resultado = validar_self_order_link_para_catalogo(repository(), token)
        if resultado.estado == ESTADO_MESA_NO_HABILITADA:
            return _respuesta_mesa_no_habilitada(), 200
        if not resultado.valido:
            return _respuesta_publica_bloqueada(resultado.estado), 404

        catalogo = construir_catalogo_self_ordering(catalog_repository(), catalog_rules())
        return render_catalogo_publico(catalogo), 200

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
        "mesa_clave": link.mesa_clave,
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


def _respuesta_mesa_no_habilitada():
    return """
    <!doctype html>
    <html lang="es">
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="font-family:Arial,sans-serif;background:#0F1115;color:#F8F9FA;margin:0;padding:28px;">
        <main style="max-width:560px;margin:0 auto;">
            <h1>Mesa no habilitada</h1>
            <p>Esta mesa todavia no esta habilitada.</p>
        </main>
    </body>
    </html>
    """
