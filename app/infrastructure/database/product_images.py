"""
product_images.py (infraestructura / base de datos)

Imagenes de producto guardadas EN LA BASE DE DATOS (no en disco de
Render ni en almacenamiento externo): una fila por producto en
`producto_imagenes` con dos versiones ya optimizadas (ver
app.infrastructure.images.product_image_processing):

- `datos`: imagen principal (lado mayor <= 1000 px) para vistas grandes
  y el futuro menu QR.
- `miniatura`: lado mayor <= 400 px, la que usan las tarjetas del POS.

Tabla separada (y no columnas en `productos`) para que ninguna consulta
de catalogo arrastre bytes por accidente: el catalogo solo pide
`producto_id, version` (listar_versiones_imagenes). Compatible
SQLite (BLOB) / PostgreSQL (BYTEA); psycopg2 devuelve memoryview, por eso
toda lectura pasa por bytes(). Idempotente: CREATE TABLE IF NOT EXISTS,
sin DROP ni migraciones destructivas.
"""

import hashlib

from app.infrastructure.database.schema import es_postgres


def tipo_blob_sql():
    return "BYTEA" if es_postgres() else "BLOB"


def crear_tabla_producto_imagenes(get_connection, pk_autoincrement_sql):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS producto_imagenes (
            id {pk_autoincrement_sql()},
            producto_id INTEGER NOT NULL UNIQUE,
            mime_type TEXT NOT NULL,
            datos {tipo_blob_sql()} NOT NULL,
            miniatura {tipo_blob_sql()} NOT NULL,
            ancho INTEGER,
            alto INTEGER,
            tamano_bytes INTEGER,
            tamano_original_bytes INTEGER,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def version_imagen(updated_at, tamano_bytes):
    """Token corto para la URL (?v=...): cambia en cada reemplazo, asi la
    imagen puede cachearse "para siempre" sin servir una vieja."""
    base = f"{updated_at}|{tamano_bytes}".encode("utf-8")
    return hashlib.sha1(base).hexdigest()[:12]


def guardar_imagen_producto(cursor, producto_id, imagen, fecha):
    """Inserta o reemplaza la imagen del producto (una por producto)."""
    cursor.execute("DELETE FROM producto_imagenes WHERE producto_id=?", (producto_id,))
    cursor.execute(
        """
        INSERT INTO producto_imagenes (
            producto_id, mime_type, datos, miniatura, ancho, alto,
            tamano_bytes, tamano_original_bytes, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            producto_id,
            imagen.mime_type,
            imagen.datos,
            imagen.miniatura,
            imagen.ancho,
            imagen.alto,
            len(imagen.datos),
            imagen.tamano_original_bytes,
            fecha,
        ),
    )


def eliminar_imagen_producto(cursor, producto_id):
    cursor.execute("DELETE FROM producto_imagenes WHERE producto_id=?", (producto_id,))


def obtener_imagen_producto(cursor, producto_id, miniatura=False):
    """(mime_type, bytes, version) o None. Solo lee la columna pedida."""
    columna = "miniatura" if miniatura else "datos"
    cursor.execute(
        f"""
        SELECT mime_type, {columna}, updated_at, tamano_bytes
        FROM producto_imagenes
        WHERE producto_id=?
        """,
        (producto_id,),
    )
    fila = cursor.fetchone()
    if not fila:
        return None
    return fila[0], bytes(fila[1]), version_imagen(fila[2], fila[3])


def obtener_info_imagen_producto(cursor, producto_id):
    """Metadatos sin bytes, para la pantalla de edicion."""
    cursor.execute(
        """
        SELECT ancho, alto, tamano_bytes, tamano_original_bytes, updated_at
        FROM producto_imagenes
        WHERE producto_id=?
        """,
        (producto_id,),
    )
    fila = cursor.fetchone()
    if not fila:
        return None
    return {
        "ancho": fila[0],
        "alto": fila[1],
        "tamano_bytes": fila[2],
        "tamano_original_bytes": fila[3],
        "version": version_imagen(fila[4], fila[2]),
    }


def listar_versiones_imagenes(cursor):
    """{producto_id: version} SIN bytes: lo que necesita un listado."""
    cursor.execute("SELECT producto_id, updated_at, tamano_bytes FROM producto_imagenes")
    return {fila[0]: version_imagen(fila[1], fila[2]) for fila in cursor.fetchall()}


def url_imagen_producto(producto_id, version, miniatura=True):
    sufijo = "&t=mini" if miniatura else ""
    return f"/producto/{producto_id}/imagen?v={version}{sufijo}"
