"""
usuarios.py (infraestructura)

Repositorio SQL puro de `usuarios` (login, administracion, flags de
delivery). Deliberadamente NO conoce `session`/Flask -- eso sigue
siendo responsabilidad exclusiva de las rutas en web_app.py (mision:
"Auth -- preservar exactamente session/login/permisos/roles;
presentation puede seguir usando session, application/domain NO").
"""

FLAGS_DELIVERY_USUARIO = {
    "conductor": "es_conductor_delivery",
    "conductor_default": "es_conductor_delivery_default",
    "coordinador": "es_coordinador_delivery",
}


def listar_usuarios_activos_login(cursor):
    cursor.execute("SELECT id, nombre FROM usuarios WHERE COALESCE(activo, 1) = 1 ORDER BY nombre")
    return cursor.fetchall()


def verificar_credenciales(cursor, usuario_id, pin):
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(rol, 'mesonera')
        FROM usuarios
        WHERE id=? AND pin=? AND COALESCE(activo, 1) = 1
        """,
        (usuario_id, pin),
    )
    return cursor.fetchone()


def listar_usuarios_admin(cursor):
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(rol, 'mesonera'), pin, COALESCE(activo, 1),
               COALESCE(es_conductor_delivery, 0), COALESCE(es_conductor_delivery_default, 0),
               COALESCE(es_coordinador_delivery, 0)
        FROM usuarios
        ORDER BY COALESCE(activo, 1) DESC, rol ASC, nombre ASC
        """
    )
    return cursor.fetchall()


def crear_usuario(cursor, nombre, pin, rol, activo):
    cursor.execute(
        "INSERT INTO usuarios (nombre, pin, rol, activo) VALUES (?, ?, ?, ?)",
        (nombre, pin, rol, activo),
    )


def obtener_usuario_para_editar(cursor, usuario_id):
    cursor.execute(
        """
        SELECT id, nombre, COALESCE(rol, 'mesonera'), pin
        FROM usuarios
        WHERE id=?
        """,
        (usuario_id,),
    )
    return cursor.fetchone()


def actualizar_usuario(cursor, usuario_id, nombre, rol, pin=None):
    if pin:
        cursor.execute(
            "UPDATE usuarios SET nombre=?, pin=?, rol=? WHERE id=?",
            (nombre, pin, rol, usuario_id),
        )
    else:
        cursor.execute(
            "UPDATE usuarios SET nombre=?, rol=? WHERE id=?",
            (nombre, rol, usuario_id),
        )


def alternar_activo_usuario(cursor, usuario_id):
    cursor.execute("SELECT COALESCE(activo, 1) FROM usuarios WHERE id=?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Usuario no encontrado")
    nuevo_activo = 0 if row[0] else 1
    cursor.execute("UPDATE usuarios SET activo=? WHERE id=?", (nuevo_activo, usuario_id))
    return nuevo_activo


def alternar_flag_delivery_usuario(cursor, usuario_id, flag):
    """Mision "configuracion del driver por defecto"/"coordinadores de
    delivery": quien puede ser conductor interno, quien es el UNICO
    conductor por defecto (se desmarca de los demas al marcar uno
    nuevo), y quienes son coordinadores. Nada de esto vive en logica de
    negocio hardcodeada: son flags reales sobre `usuarios`."""
    columna = FLAGS_DELIVERY_USUARIO.get((flag or "").strip())
    if not columna:
        raise ValueError("Flag invalido")

    cursor.execute(f"SELECT COALESCE({columna}, 0) FROM usuarios WHERE id=?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        raise LookupError("Usuario no encontrado")

    nuevo_valor = 0 if row[0] else 1
    if flag == "conductor_default" and nuevo_valor == 1:
        cursor.execute("UPDATE usuarios SET es_conductor_delivery_default=0")
    cursor.execute(f"UPDATE usuarios SET {columna}=? WHERE id=?", (nuevo_valor, usuario_id))
    return nuevo_valor
