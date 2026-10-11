"""
navigation.py (presentacion)

Navegacion global de NekoPOS: un unico boton "☰ Menú" en el header
(barra_superior) que abre un drawer con las opciones del rol.

QUE opciones ve cada rol es EXACTAMENTE lo que antes pintaba index()
como fila de botones (`menu_links`), solo que ahora como datos:
`claves_navegacion_rol` reproduce esa misma cascada if/elif. Esto es
SOLO interfaz: la seguridad sigue en `proteger_sistema()` (web_app.py),
que bloquea cada endpoint por rol aunque alguien escriba la URL a mano.

Ademas del menu del rol, cada pantalla sigue pasando a barra_superior()
sus enlaces contextuales (ya filtrados por rol en esa pantalla, p. ej.
"Cartera de clientes" en CxC); se muestran en el grupo "En esta
pantalla" sin repetir lo que ya esta en el menu del rol.
"""

import html as html_lib
import re

# clave -> (href, icono, texto). "inicio" usa la ruta de inicio del rol.
NAV_ITEMS = {
    "inicio": (None, "🏠", "Inicio"),
    "despacho": ("/despacho", "🛎️", "Despacho"),
    "cocina": ("/cocina", "🍳", "Cocina"),
    "delivery": ("/delivery", "🛵", "Delivery"),
    "cxc": ("/cuentas_por_cobrar", "💰", "Cuentas por cobrar"),
    "tasa": ("/cambiar_tasa", "💲", "Tasa"),
    "cerrar_jornada": ("/cerrar_jornada", "🔒", "Cerrar jornada"),
    "cierre": ("/cierre", "📦", "Cierre"),
    "reportes": ("/reportes", "📊", "Reportes"),
    "dashboard": ("/dashboard", "📈", "Dashboard"),
    "exportar": ("/exportar", "📤", "Exportar"),
    "menu": ("/menu", "🍜", "Menú"),
    "inventario": ("/inventario", "📦", "Inventario"),
    "compras": ("/compras", "🛒", "Compras"),
    "produccion": ("/produccion", "👨‍🍳", "Producción"),
    "recetas": ("/recetas", "🧾", "Recetas"),
    "movimientos": ("/movimientos_inventario", "📋", "Movimientos"),
    "usuarios": ("/usuarios", "👥", "Usuarios"),
}

NAV_GRUPOS = (
    ("Operación", ("inicio", "despacho", "cocina", "delivery")),
    ("Caja y cobros", ("cxc", "tasa", "cerrar_jornada", "cierre")),
    ("Reportes", ("reportes", "dashboard", "exportar")),
    ("Administración", ("menu", "inventario", "compras", "produccion", "recetas", "movimientos", "usuarios")),
)


def claves_navegacion_rol(rol, puede_tomar_ordenes):
    """Mismas reglas que el antiguo `menu_links` de index()."""
    claves = ["inicio"]
    if rol == "master":
        claves += [
            "tasa", "exportar", "cierre", "reportes", "dashboard", "cerrar_jornada",
            "menu", "inventario", "compras", "produccion", "recetas", "movimientos",
            "usuarios", "cocina", "cxc", "delivery",
        ]
    elif rol in ("socio", "mesonera_reportes"):
        claves += ["reportes", "dashboard"]
    elif rol == "cocina_reportes":
        claves += ["cocina", "produccion", "inventario", "reportes", "dashboard"]
    if puede_tomar_ordenes:
        claves.append("despacho")
    return claves


_RE_ENLACE = re.compile(r'<a\s+[^>]*?href="([^"]+)"[^>]*>(.*?)</a>', re.S)


def _es_actual(href, ruta_actual):
    if not ruta_actual:
        return False
    if href == "/":
        return ruta_actual == "/"
    return ruta_actual == href or ruta_actual.startswith(href.rstrip("/") + "/")


def _item_html(href, icono, texto_html, actual):
    clase = "ds-nav-item activo" if actual else "ds-nav-item"
    aria = ' aria-current="page"' if actual else ""
    return (
        f'<a class="{clase}" href="{html_lib.escape(href, quote=True)}"{aria}>'
        f'<span class="ds-nav-icono" aria-hidden="true">{icono}</span><span>{texto_html}</span></a>'
    )


def render_menu_global(*, rol, puede_tomar_ordenes, ruta_inicio, ruta_actual, usuario, extra_links=""):
    """Devuelve (boton_html, drawer_html) para barra_superior()."""
    claves = claves_navegacion_rol(rol, puede_tomar_ordenes) if rol else []

    # (grupo, href, icono, texto_html) sin hrefs repetidos: el menu del rol
    # manda; los enlaces contextuales solo agregan lo que el menu no tiene.
    secciones = []
    vistos = set()
    for titulo, claves_grupo in NAV_GRUPOS:
        for clave in claves_grupo:
            if clave not in claves:
                continue
            href, icono, texto = NAV_ITEMS[clave]
            href = ruta_inicio if clave == "inicio" else href
            if href not in vistos:
                vistos.add(href)
                secciones.append((titulo, href, icono, html_lib.escape(texto)))
    contextuales = []
    for href, contenido in _RE_ENLACE.findall(extra_links or ""):
        if href in vistos or href == "/logout":
            continue
        vistos.add(href)
        contextuales.append(("En esta pantalla", href, "↪", contenido.strip()))
    secciones = contextuales + secciones + [("Sesión", "/logout", "🚪", "Salir")]

    # Solo UNA opcion marcada como actual: la coincidencia mas especifica.
    candidatas = [href for _, href, _, _ in secciones if _es_actual(href, ruta_actual)]
    actual = max(candidatas, key=len) if candidatas else None

    grupos_html = ""
    grupo_abierto = None
    for titulo, href, icono, texto_html in secciones:
        if titulo != grupo_abierto:
            if grupo_abierto is not None:
                grupos_html += "</div>"
            grupos_html += f'<div class="ds-nav-group"><div class="ds-nav-group-title">{titulo}</div>'
            grupo_abierto = titulo
        grupos_html += _item_html(href, icono, texto_html, href == actual)
    grupos_html += "</div>"

    usuario_html = html_lib.escape(usuario or "")
    boton = (
        '<button type="button" class="ds-menu-trigger" id="navMenuBtn" '
        'aria-controls="navDrawer" aria-expanded="false" aria-haspopup="dialog">'
        '<span class="ds-menu-trigger-icono" aria-hidden="true">☰</span><span>Menú</span></button>'
    )
    drawer = f"""
    <div class="ds-drawer-backdrop" id="navBackdrop"></div>
    <nav class="ds-drawer" id="navDrawer" aria-label="Menú principal" aria-hidden="true">
        <div class="ds-drawer-head">
            <div>
                <div class="ds-drawer-title">Menú</div>
                <div class="ds-drawer-subtitle">👤 {usuario_html}</div>
            </div>
            <button type="button" class="ds-drawer-close" id="navCerrar" aria-label="Cerrar menú">✕</button>
        </div>
        <div class="ds-drawer-body">{grupos_html}</div>
    </nav>
    <script>
    (function() {{
        var boton = document.getElementById("navMenuBtn");
        var drawer = document.getElementById("navDrawer");
        var fondo = document.getElementById("navBackdrop");
        var cerrarBtn = document.getElementById("navCerrar");
        if (!boton || !drawer) return;
        function abrir() {{
            drawer.classList.add("abierto");
            fondo.classList.add("activo");
            drawer.setAttribute("aria-hidden", "false");
            boton.setAttribute("aria-expanded", "true");
            document.body.classList.add("ds-drawer-abierto");
            var actual = drawer.querySelector(".ds-nav-item.activo") || drawer.querySelector(".ds-nav-item");
            if (actual) actual.focus({{ preventScroll: true }});
        }}
        function cerrar() {{
            if (!drawer.classList.contains("abierto")) return;
            drawer.classList.remove("abierto");
            fondo.classList.remove("activo");
            drawer.setAttribute("aria-hidden", "true");
            boton.setAttribute("aria-expanded", "false");
            document.body.classList.remove("ds-drawer-abierto");
            boton.focus({{ preventScroll: true }});
        }}
        boton.addEventListener("click", function() {{
            if (drawer.classList.contains("abierto")) cerrar(); else abrir();
        }});
        cerrarBtn.addEventListener("click", cerrar);
        fondo.addEventListener("click", cerrar);
        document.addEventListener("keydown", function(e) {{ if (e.key === "Escape") cerrar(); }});
    }})();
    </script>
    """
    return boton, drawer
