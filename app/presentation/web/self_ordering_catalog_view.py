import html


def render_catalogo_publico(catalogo):
    tabs_html = []
    secciones_html = []
    modales_html = []

    for index, categoria in enumerate(catalogo.categorias):
        activa = index == 0
        categoria_id = f"categoria-{index}"
        tabs_html.append(_render_tab(categoria.nombre, categoria_id, activa))
        productos_html = "".join(
            _render_producto_card(producto, categoria.nombre)
            for producto in categoria.productos
        )
        if not productos_html:
            productos_html = "<p class='empty-state'>Esta categoria no tiene productos disponibles por ahora.</p>"
        secciones_html.append(
            f"""
            <section class="catalog-section{' active' if activa else ''}" id="{categoria_id}" {'data-active="true"' if activa else 'hidden'}>
                <div class="section-title">
                    <p>Categoria</p>
                    <h2>{html.escape(categoria.nombre)}</h2>
                </div>
                <div class="product-grid">{productos_html}</div>
            </section>
            """
        )
        modales_html.extend(_render_producto_modal(producto, categoria.nombre) for producto in categoria.productos)

    contenido = "".join(secciones_html) or "<p class='empty-state'>El menu no esta disponible por ahora.</p>"
    return f"""
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Neko Wok Autoservicio</title>
        <style>
            :root {{
                color-scheme: dark;
                --bg:#0F1115;
                --panel:#181B20;
                --panel-2:#22262D;
                --line:#31363F;
                --text:#F8F9FA;
                --muted:#B0B6BE;
                --green:#3DDC84;
                --warm:#F8D083;
                --danger:#EF4444;
            }}
            * {{ box-sizing:border-box; }}
            body {{ margin:0; font-family:Arial,sans-serif; background:var(--bg); color:var(--text); }}
            main {{ max-width:980px; margin:0 auto; padding:18px 14px 40px; }}
            header {{ margin-bottom:16px; }}
            h1 {{ margin:0 0 6px; color:var(--green); font-size:30px; }}
            .sub {{ margin:0; color:var(--muted); font-size:14px; line-height:1.4; }}
            .category-tabs {{
                position:sticky; top:0; z-index:5; display:flex; gap:8px; overflow-x:auto;
                padding:10px 0 12px; background:rgba(15,17,21,.96); border-bottom:1px solid rgba(49,54,63,.7);
            }}
            .category-tab {{
                flex:0 0 auto; border:1px solid var(--line); background:var(--panel);
                color:var(--text); min-height:44px; padding:0 14px; border-radius:999px;
                font-weight:900; cursor:pointer;
            }}
            .category-tab.active {{ background:var(--warm); border-color:var(--warm); color:#1B1205; }}
            .catalog-section {{ margin-top:18px; }}
            .catalog-section[hidden] {{ display:none; }}
            .section-title {{ display:flex; align-items:end; justify-content:space-between; gap:12px; margin-bottom:12px; }}
            .section-title p {{ margin:0; color:var(--muted); font-size:12px; text-transform:uppercase; font-weight:900; }}
            .section-title h2 {{ margin:0; font-size:22px; }}
            .product-grid {{ display:grid; gap:14px; }}
            .product-card {{
                display:grid; grid-template-columns:104px 1fr; gap:13px; width:100%; text-align:left;
                border:1px solid var(--line); background:var(--panel); color:var(--text);
                border-radius:18px; padding:10px; cursor:pointer; min-height:132px;
            }}
            .product-card:focus-visible, .category-tab:focus-visible, .sheet-close:focus-visible, .option-pill:focus-visible {{
                outline:3px solid var(--green); outline-offset:2px;
            }}
            .product-visual {{
                min-height:112px; border-radius:14px; background:var(--panel-2);
                display:grid; place-items:center; border:1px solid rgba(255,255,255,.06);
            }}
            .visual-mark {{ font-size:25px; font-weight:900; color:var(--warm); letter-spacing:0; }}
            .visual-combos {{ background:#123528; }}
            .visual-arroz {{ background:#25304A; }}
            .visual-promociones {{ background:#3B2617; }}
            .visual-bebidas {{ background:#173447; }}
            .product-info {{ min-width:0; display:flex; flex-direction:column; gap:7px; }}
            .product-name {{ margin:0; font-size:18px; line-height:1.18; }}
            .product-desc {{ margin:0; color:var(--muted); font-size:13px; line-height:1.35; }}
            .product-actions {{ margin-top:auto; display:flex; align-items:center; justify-content:space-between; gap:10px; }}
            .price {{ color:var(--green); font-size:19px; font-weight:900; white-space:nowrap; }}
            .cta {{ color:#07130C; background:var(--green); border-radius:999px; padding:8px 10px; font-weight:900; font-size:12px; white-space:nowrap; }}
            .empty-state {{ color:var(--muted); margin:18px 0; }}
            .sheet {{
                position:fixed; inset:0; z-index:20; background:rgba(0,0,0,.58);
                display:flex; align-items:flex-end; justify-content:center; padding:0 10px 10px;
            }}
            .sheet[hidden] {{ display:none; }}
            .sheet-panel {{
                width:min(720px, 100%); max-height:88vh; overflow:auto;
                background:#15181D; border:1px solid var(--line); border-radius:22px 22px 16px 16px;
                padding:14px; box-shadow:0 -20px 50px rgba(0,0,0,.35);
            }}
            .sheet-head {{ display:grid; grid-template-columns:92px 1fr auto; gap:12px; align-items:start; }}
            .sheet-head .product-visual {{ min-height:92px; }}
            .sheet h3 {{ margin:0 0 6px; font-size:22px; }}
            .sheet .product-desc {{ font-size:14px; }}
            .sheet-close {{
                width:40px; height:40px; border-radius:999px; border:1px solid var(--line);
                background:var(--panel-2); color:var(--text); font-size:22px; cursor:pointer;
            }}
            .option-group {{ margin-top:16px; border-top:1px solid var(--line); padding-top:14px; }}
            .option-title {{ display:flex; justify-content:space-between; gap:10px; color:var(--warm); font-weight:900; }}
            .option-help {{ color:var(--muted); font-size:13px; margin:6px 0 0; }}
            .option-grid {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }}
            .option-pill {{
                border:1px solid #3C4350; background:var(--panel); color:var(--text);
                border-radius:999px; padding:10px 12px; font-weight:700; cursor:pointer; min-height:42px;
            }}
            .option-pill.selected {{ border-color:var(--green); background:#123528; color:var(--green); }}
            .sheet-actions {{ margin-top:18px; display:flex; gap:10px; }}
            .disabled-action {{
                flex:1; min-height:46px; border-radius:999px; border:0; background:#2A2F38;
                color:var(--muted); font-weight:900;
            }}
            @media (min-width:720px) {{
                .product-grid {{ grid-template-columns:repeat(2, minmax(0,1fr)); }}
                .product-card {{ grid-template-columns:128px 1fr; }}
                .product-visual {{ min-height:128px; }}
            }}
        </style>
    </head>
    <body>
        <main>
            <header>
                <h1>Neko Wok</h1>
                <p class="sub">Autoservicio de mesa. Explora el menu; el envio del pedido estara disponible proximamente.</p>
            </header>
            <nav class="category-tabs" aria-label="Categorias publicas">
                {''.join(tabs_html)}
            </nav>
            {contenido}
        </main>
        {''.join(modales_html)}
        <script>
        (function() {{
            const tabs = Array.from(document.querySelectorAll(".category-tab"));
            const sections = Array.from(document.querySelectorAll(".catalog-section"));
            tabs.forEach(function(tab) {{
                tab.addEventListener("click", function() {{
                    const target = tab.dataset.categoryTarget;
                    tabs.forEach(function(item) {{ item.classList.toggle("active", item === tab); }});
                    sections.forEach(function(section) {{
                        const active = section.id === target;
                        section.toggleAttribute("hidden", !active);
                        section.classList.toggle("active", active);
                    }});
                }});
            }});

            function closeSheet(sheet) {{
                if (sheet) sheet.setAttribute("hidden", "");
            }}

            document.querySelectorAll("[data-product-modal]").forEach(function(card) {{
                card.addEventListener("click", function() {{
                    const sheet = document.getElementById(card.dataset.productModal);
                    if (sheet) sheet.removeAttribute("hidden");
                }});
            }});
            document.querySelectorAll("[data-close-sheet]").forEach(function(button) {{
                button.addEventListener("click", function() {{ closeSheet(button.closest(".sheet")); }});
            }});
            document.querySelectorAll(".sheet").forEach(function(sheet) {{
                sheet.addEventListener("click", function(event) {{
                    if (event.target === sheet) closeSheet(sheet);
                }});
            }});
            document.addEventListener("keydown", function(event) {{
                if (event.key === "Escape") closeSheet(document.querySelector(".sheet:not([hidden])"));
            }});

            document.querySelectorAll(".option-pill").forEach(function(button) {{
                button.addEventListener("click", function() {{
                    const group = button.closest(".option-group");
                    const max = Number(group.dataset.max || 1);
                    const optional = group.dataset.optional === "true";
                    const selected = Array.from(group.querySelectorAll(".option-pill.selected"));
                    if (max === 1) {{
                        const previous = selected.find(function(item) {{ return item !== button; }});
                        if (button.classList.contains("selected")) {{
                            if (optional) button.classList.remove("selected");
                        }} else {{
                            if (previous) previous.classList.remove("selected");
                            button.classList.add("selected");
                        }}
                    }} else if (button.classList.contains("selected")) {{
                        button.classList.remove("selected");
                    }} else if (selected.length < max) {{
                        button.classList.add("selected");
                    }}
                    const count = group.querySelector("[data-option-count]");
                    if (count) {{
                        count.textContent = group.querySelectorAll(".option-pill.selected").length + " de " + max;
                    }}
                }});
            }});
        }})();
        </script>
    </body>
    </html>
    """


def _render_tab(nombre, categoria_id, activa):
    return (
        f"<button class='category-tab{' active' if activa else ''}' "
        f"type='button' data-category-target='{categoria_id}'>{html.escape(nombre)}</button>"
    )


def _render_producto_card(producto, categoria_nombre):
    modal_id = f"producto-modal-{producto.id}"
    cta = "Ver opciones" if producto.opciones else "Seleccionar"
    return f"""
    <button class="product-card" type="button" data-product-modal="{modal_id}" data-producto-id="{producto.id}">
        {_render_visual(categoria_nombre)}
        <span class="product-info">
            <span class="product-name">{html.escape(producto.nombre)}</span>
            <span class="product-desc">{html.escape(producto.descripcion)}</span>
            <span class="product-actions">
                <span class="price">${producto.precio:.2f}</span>
                <span class="cta">{cta}</span>
            </span>
        </span>
    </button>
    """


def _render_producto_modal(producto, categoria_nombre):
    modal_id = f"producto-modal-{producto.id}"
    opciones = "".join(_render_opcion(opcion) for opcion in producto.opciones)
    if not opciones:
        opciones = "<p class='empty-state'>Este producto no requiere opciones.</p>"
    return f"""
    <div class="sheet" id="{modal_id}" hidden>
        <div class="sheet-panel" role="dialog" aria-modal="true" aria-label="{html.escape(producto.nombre, quote=True)}">
            <div class="sheet-head">
                {_render_visual(categoria_nombre)}
                <div>
                    <h3>{html.escape(producto.nombre)}</h3>
                    <p class="product-desc">{html.escape(producto.descripcion)}</p>
                    <div class="price">${producto.precio:.2f}</div>
                </div>
                <button class="sheet-close" type="button" data-close-sheet aria-label="Cerrar">x</button>
            </div>
            {opciones}
            <div class="sheet-actions">
                <button class="disabled-action" type="button" disabled>Disponible proximamente</button>
                <button class="category-tab" type="button" data-close-sheet>Listo</button>
            </div>
        </div>
    </div>
    """


def _render_visual(categoria_nombre):
    clase = {
        "Combos personales": "visual-combos",
        "Arroz chino": "visual-arroz",
        "Promociones": "visual-promociones",
        "Bebidas": "visual-bebidas",
    }.get(categoria_nombre, "")
    marca = {
        "Combos personales": "COMBO",
        "Arroz chino": "ARROZ",
        "Promociones": "PROMO",
        "Bebidas": "BEBIDA",
    }.get(categoria_nombre, "NEKO")
    return f"<span class='product-visual {clase}' aria-hidden='true'><span class='visual-mark'>{marca}</span></span>"


def _render_opcion(opcion):
    valores = "".join(
        f"<button class='option-pill' type='button'>{html.escape(valor)}</button>"
        for valor in opcion.valores
        if valor
    )
    ayuda = f"<p class='option-help'>{html.escape(opcion.ayuda)}</p>" if opcion.ayuda else ""
    return f"""
    <div class="option-group" data-max="{opcion.maximas}" data-required="{opcion.requeridas}" data-optional="{'true' if opcion.opcional else 'false'}">
        <div class="option-title">
            <span>{html.escape(_texto_cardinalidad(opcion))}</span>
            <span data-option-count>0 de {opcion.maximas}</span>
        </div>
        {ayuda}
        <div class="option-grid">{valores}</div>
    </div>
    """


def _texto_cardinalidad(opcion):
    titulo = opcion.titulo.lower()
    if opcion.opcional:
        return f"{opcion.titulo}: Opcional"
    if opcion.requeridas == 1:
        singular = {
            "acompanantes": "acompanante",
            "bebidas": "bebida",
            "pollos": "pollo",
            "arroces": "arroz",
            "sabores": "sabor",
        }.get(titulo, titulo[:-1] if titulo.endswith("s") else titulo)
        return f"Elige 1 {singular}"
    return f"Elige {opcion.requeridas} {titulo}"
