from flask import Blueprint, jsonify

from app.application.self_ordering.links import (
    OrdenSelfOrderingArchivada,
    OrdenSelfOrderingCerrada,
    OrdenSelfOrderingNoExiste,
    obtener_o_crear_link_mesa,
    revocar_link_mesa_de_orden,
)
from app.infrastructure.database.self_ordering_links import SqlSelfOrderLinkRepository


def crear_self_ordering_blueprint(connection_factory, last_id_getter):
    blueprint = Blueprint("self_ordering", __name__)

    def repository():
        return SqlSelfOrderLinkRepository(connection_factory, last_id_getter)

    @blueprint.post("/orden/<int:orden_id>/self-ordering/link")
    def crear_o_obtener_link_mesa(orden_id):
        try:
            link, creado = obtener_o_crear_link_mesa(repository(), orden_id)
        except OrdenSelfOrderingNoExiste as exc:
            return jsonify({"error": str(exc)}), 404
        except (OrdenSelfOrderingArchivada, OrdenSelfOrderingCerrada) as exc:
            return jsonify({"error": str(exc)}), 409

        return jsonify({"link": _link_to_json(link), "creado": creado})

    @blueprint.post("/orden/<int:orden_id>/self-ordering/link/<int:link_id>/revocar")
    def revocar_link_mesa(orden_id, link_id):
        try:
            revocado = revocar_link_mesa_de_orden(repository(), orden_id, link_id)
        except OrdenSelfOrderingNoExiste as exc:
            return jsonify({"error": str(exc)}), 404
        except (OrdenSelfOrderingArchivada, OrdenSelfOrderingCerrada) as exc:
            return jsonify({"error": str(exc)}), 409

        if not revocado:
            return jsonify({"error": "Link no encontrado para esta orden."}), 404

        link = repository().buscar_por_id(link_id)
        return jsonify({"link": _link_to_json(link), "revocado": True})

    return blueprint


def _link_to_json(link):
    return {
        "id": link.id,
        "token": link.token,
        "canal": link.canal,
        "estado": link.estado,
        "fecha_creacion": link.fecha_creacion,
        "fecha_expiracion": link.fecha_expiracion,
    }

