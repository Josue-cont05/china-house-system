    return html


@app.route("/cerrar_dia")
def cerrar_dia():
    conn = get_connection()
    cursor = conn.cursor()

    ahora = ahora_venezuela()
    inicio = ahora.strftime("%Y-%m-%d") + " 00:00:00"
    fin = ahora.strftime("%Y-%m-%d") + " 23:59:59"

    cursor.execute(
        """
        SELECT COUNT(*) FROM ordenes
        WHERE estado = 'cerrada'
        AND fecha_hora BETWEEN ? AND ?
        """,
        (inicio, fin),
    )
    total_ordenes = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT SUM(i.precio)
        FROM orden_items i
        JOIN ordenes o ON i.orden_id = o.id
        WHERE o.estado = 'cerrada'
        AND o.fecha_hora BETWEEN ? AND ?
        """,
        (inicio, fin),
    )
    total_ventas_usd = cursor.fetchone()[0] or 0

    cursor.execute("SELECT valor FROM tasa LIMIT 1")
    tasa = cursor.fetchone()[0]
    total_ventas_bs = total_ventas_usd * tasa

    cursor.execute(
        """
        SELECT metodo, SUM(monto)
        FROM pagos
        WHERE fecha BETWEEN ? AND ?
        GROUP BY metodo
        """,
        (inicio, fin),
    )

    total_pagado_usd = 0
    total_pagado_bs = 0
    for metodo, monto in cursor.fetchall():
        if metodo == "usd":
            total_pagado_usd += monto
        else:
            total_pagado_bs += monto

    total_pagado_usd += total_pagado_bs / tasa
    diferencia = total_pagado_usd - total_ventas_usd
    fecha_cierre = ahora.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        """
        INSERT INTO cierres (
            fecha_inicio, fecha_fin, total_ordenes, total_ventas_usd, total_ventas_bs,
            total_pagado_usd, total_pagado_bs, diferencia, fecha_cierre
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            inicio,
            fin,
            total_ordenes,
            total_ventas_usd,
            total_ventas_bs,
            total_pagado_usd,
            total_pagado_bs,
            diferencia,
            fecha_cierre,
        ),
    )

    conn.commit()
    conn.close()

    alerta = ""
    if abs(diferencia) > 0.01:
        alerta = f"<h2 style='color:red;'>⚠️ DESCADRE: {round(diferencia, 2)} USD</h2>"

    return f"""
    <h1>✅ CIERRE REALIZADO</h1>
    {alerta}
    <p>Órdenes: {total_ordenes}</p>
    <p>Ventas USD: ${round(total_ventas_usd, 2)}</p>
    <p>Pagado USD: ${round(total_pagado_usd, 2)}</p>
    <a href="/">⬅ Volver</a>
    """


@app.route("/facturas_pendientes")
def facturas_pendientes():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, numero_orden, tipo, cliente, referencia
            FROM ordenes
            WHERE facturar = 1
            """
        )
        ordenes = cursor.fetchall()

        resultado = []
        for o in ordenes:
            cursor.execute(
                """
                SELECT producto, precio
                FROM orden_items
                WHERE orden_id=?
                """,
                (o[0],),
            )
            items = cursor.fetchall()
            resultado.append(
                {
                    "id": o[0],
                    "numero": o[1],
                    "tipo": o[2],
                    "cliente": o[3],
                    "referencia": o[4],
                    "items": [f"{i[0]} - ${i[1]}" for i in items],
                    "total": sum(i[1] for i in items),
                }
            )

        conn.close()
        return jsonify(resultado)
    except Exception as e:
        print("❌ ERROR EN FACTURAS:", e)
        return jsonify([])


@app.route("/activar_factura/<int:orden_id>")
def activar_factura(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ordenes SET facturar=1 WHERE id=?", (orden_id,))
    conn.commit()
    conn.close()
    return redirect(f"/orden/{orden_id}")


@app.route("/desactivar_factura/<int:orden_id>")
def desactivar_factura(orden_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE ordenes SET facturar=0 WHERE id=?", (orden_id,))
    conn.commit()
    conn.close()
    return "ok"


if __name__ == "__main__":
    init_db()
    cargar_productos()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
