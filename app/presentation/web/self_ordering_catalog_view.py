import html


def render_catalogo_publico(catalogo, submit_url=None):
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
            .customer-note {{
                width:100%; min-height:76px; resize:vertical; border:1px solid var(--line);
                border-radius:14px; background:var(--panel); color:var(--text);
                padding:10px 12px; font:inherit; margin-top:8px;
            }}
            .add-to-cart, .disabled-action {{
                flex:1; min-height:46px; border-radius:999px; border:0; background:#2A2F38;
                color:var(--muted); font-weight:900;
            }}
            .add-to-cart {{ background:var(--green); color:#07130C; cursor:pointer; }}
            .add-to-cart:disabled {{ background:#2A2F38; color:var(--muted); cursor:not-allowed; }}
            .cart-bar {{
                position:fixed; left:12px; right:12px; bottom:12px; z-index:15; min-height:58px;
                border:0; border-radius:999px; background:var(--green); color:#07130C;
                font-weight:900; font-size:16px; box-shadow:0 12px 28px rgba(0,0,0,.35); cursor:pointer;
            }}
            .cart-bar[hidden], .cart-sheet[hidden] {{ display:none; }}
            .cart-sheet {{ position:fixed; inset:0; z-index:30; background:rgba(0,0,0,.62); display:flex; align-items:flex-end; padding:0 10px 10px; }}
            .cart-panel {{ width:min(720px, 100%); margin:0 auto; max-height:88vh; overflow:auto; background:#15181D; border:1px solid var(--line); border-radius:22px 22px 16px 16px; padding:14px; box-shadow:0 -20px 50px rgba(0,0,0,.35); }}
            .cart-head {{ display:flex; justify-content:space-between; gap:12px; align-items:center; margin-bottom:12px; }}
            .cart-head h2 {{ margin:0; }}
            .cart-line {{ display:grid; grid-template-columns:1fr auto; gap:10px; border-top:1px solid var(--line); padding:12px 0; }}
            .cart-line h3 {{ margin:0 0 5px; font-size:17px; }}
            .cart-config {{ margin:0; color:var(--muted); font-size:13px; line-height:1.35; }}
            .cart-controls {{ display:flex; gap:6px; align-items:center; justify-content:flex-end; }}
            .cart-controls button, .remove-line {{ min-width:40px; min-height:40px; border-radius:999px; border:1px solid var(--line); background:var(--panel-2); color:var(--text); font-weight:900; cursor:pointer; }}
            .remove-line {{ color:#FCA5A5; }}
            .cart-total {{ display:flex; justify-content:space-between; gap:10px; font-size:20px; font-weight:900; border-top:1px solid var(--line); padding-top:14px; margin-top:6px; }}
            .send-request {{ width:100%; min-height:50px; margin-top:14px; border:0; border-radius:999px; background:#2A2F38; color:var(--muted); font-weight:900; }}
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
                <p class="sub">Autoservicio de mesa. Arma tu pedido y envialo cuando este listo.</p>
            </header>
            <nav class="category-tabs" aria-label="Categorias publicas">
                {''.join(tabs_html)}
            </nav>
            {contenido}
        </main>
        {''.join(modales_html)}
        <button class="cart-bar" id="cartBar" type="button" hidden>
            Ver pedido · <span id="cartBarCount">0 productos</span> · <span id="cartBarTotal">$0.00</span>
        </button>
        <div class="cart-sheet" id="cartSheet" hidden>
            <div class="cart-panel" role="dialog" aria-modal="true" aria-label="Pedido">
                <div class="cart-head">
                    <h2>Tu pedido</h2>
                    <button class="sheet-close" type="button" id="closeCart" aria-label="Cerrar carrito">x</button>
                </div>
                <div id="cartLines"></div>
                <div class="cart-total">
                    <span>Total</span>
                    <span id="cartTotal">$0.00</span>
                </div>
                <p class="cart-config" id="cartSubmitStatus" aria-live="polite"></p>
                <button class="send-request" id="sendRequest" type="button" disabled>Enviar solicitud</button>
            </div>
        </div>
        <script>
        (function() {{
            const cart = [];
            const tabs = Array.from(document.querySelectorAll(".category-tab"));
            const sections = Array.from(document.querySelectorAll(".catalog-section"));
            const cartBar = document.getElementById("cartBar");
            const cartBarCount = document.getElementById("cartBarCount");
            const cartBarTotal = document.getElementById("cartBarTotal");
            const cartSheet = document.getElementById("cartSheet");
            const cartLines = document.getElementById("cartLines");
            const cartTotal = document.getElementById("cartTotal");
            const closeCart = document.getElementById("closeCart");
            const sendRequest = document.getElementById("sendRequest");
            const cartSubmitStatus = document.getElementById("cartSubmitStatus");
            const submitUrl = "{html.escape(submit_url or '', quote=True)}";
            let currentSubmissionId = "";

            function money(cents) {{
                return "$" + (cents / 100).toFixed(2);
            }}

            function selectedValues(group) {{
                return Array.from(group.querySelectorAll(".option-pill.selected"))
                    .map(function(button) {{
                        return {{
                            valor: button.dataset.optionValue || button.textContent.trim(),
                            recargoCentavos: Number(button.dataset.optionExtraCents || 0)
                        }};
                    }});
            }}

            function collectConfig(sheet) {{
                return Array.from(sheet.querySelectorAll("[data-option-group]")).map(function(group) {{
                    const opciones = selectedValues(group);
                    return {{
                        titulo: group.dataset.title || "",
                        valores: opciones.map(function(opcion) {{ return opcion.valor; }}),
                        recargoCentavos: opciones.reduce(function(total, opcion) {{
                            return total + opcion.recargoCentavos;
                        }}, 0),
                        requeridas: Number(group.dataset.required || 0),
                        maximas: Number(group.dataset.max || 1),
                        opcional: group.dataset.optional === "true"
                    }};
                }});
            }}

            function configIsValid(config) {{
                return config.every(function(group) {{
                    const total = group.valores.length;
                    if (total > group.maximas) return false;
                    if (group.opcional) return true;
                    return total === group.requeridas;
                }});
            }}

            function configKey(config) {{
                return JSON.stringify(config.map(function(group) {{
                    return {{
                        titulo: group.titulo,
                        valores: group.valores.slice().sort()
                    }};
                }}).sort(function(a, b) {{
                    return a.titulo.localeCompare(b.titulo);
                }}));
            }}

            function normalizeNote(note) {{
                return (note || "").trim();
            }}

            function lineKey(productId, config, note) {{
                return productId + "|" + configKey(config) + "|" + normalizeNote(note);
            }}

            function configSummary(config) {{
                const lines = [];
                config.forEach(function(group) {{
                    if (group.valores.length) {{
                        lines.push(group.titulo + ": " + group.valores.join(", "));
                    }}
                }});
                return lines.join(" · ");
            }}

            function configExtraCents(config) {{
                return config.reduce(function(total, group) {{
                    return total + group.recargoCentavos;
                }}, 0);
            }}

            function updateAddButton(sheet) {{
                const button = sheet.querySelector("[data-add-to-cart]");
                if (!button) return;
                const config = collectConfig(sheet);
                button.disabled = !configIsValid(config);
            }}

            function totalItems() {{
                return cart.reduce(function(total, item) {{ return total + item.quantity; }}, 0);
            }}

            function totalCents() {{
                return cart.reduce(function(total, item) {{
                    return total + item.unitPriceCents * item.quantity;
                }}, 0);
            }}

            function renderCart() {{
                const count = totalItems();
                const total = totalCents();
                cartBar.hidden = count === 0;
                if (sendRequest) sendRequest.disabled = count === 0 || !submitUrl;
                cartBarCount.textContent = count + (count === 1 ? " producto" : " productos");
                cartBarTotal.textContent = money(total);
                cartTotal.textContent = money(total);
                cartLines.innerHTML = "";
                if (!cart.length) {{
                    const empty = document.createElement("p");
                    empty.className = "empty-state";
                    empty.textContent = "Tu pedido esta vacio.";
                    cartLines.appendChild(empty);
                    return;
                }}
                cart.forEach(function(item, index) {{
                    const line = document.createElement("div");
                    line.className = "cart-line";

                    const info = document.createElement("div");
                    const title = document.createElement("h3");
                    title.textContent = item.name;
                    const config = document.createElement("p");
                    config.className = "cart-config";
                    config.textContent = item.summary || "Sin opciones";
                    const subtotal = document.createElement("p");
                    subtotal.className = "cart-config";
                    subtotal.textContent = item.quantity + " x " + money(item.unitPriceCents) + " = " + money(item.unitPriceCents * item.quantity);
                    info.appendChild(title);
                    info.appendChild(config);
                    if (item.indication) {{
                        const note = document.createElement("p");
                        note.className = "cart-config";
                        note.textContent = "Nota: " + item.indication;
                        info.appendChild(note);
                    }}
                    info.appendChild(subtotal);

                    const controls = document.createElement("div");
                    controls.className = "cart-controls";
                    const minus = document.createElement("button");
                    minus.type = "button";
                    minus.textContent = "-";
                    minus.dataset.cartMinus = String(index);
                    const qty = document.createElement("strong");
                    qty.textContent = String(item.quantity);
                    const plus = document.createElement("button");
                    plus.type = "button";
                    plus.textContent = "+";
                    plus.dataset.cartPlus = String(index);
                    const remove = document.createElement("button");
                    remove.type = "button";
                    remove.className = "remove-line";
                    remove.textContent = "Eliminar";
                    remove.dataset.cartRemove = String(index);
                    controls.appendChild(minus);
                    controls.appendChild(qty);
                    controls.appendChild(plus);
                    controls.appendChild(remove);

                    line.appendChild(info);
                    line.appendChild(controls);
                    cartLines.appendChild(line);
                }});
            }}

            function addItemFromSheet(sheet) {{
                const config = collectConfig(sheet);
                if (!configIsValid(config)) return;
                const productId = Number(sheet.dataset.productId);
                const basePriceCents = Number(sheet.dataset.priceCents || 0);
                const unitPriceCents = basePriceCents + configExtraCents(config);
                const noteInput = sheet.querySelector("[data-customer-note]");
                const indication = normalizeNote(noteInput ? noteInput.value : "");
                const key = lineKey(productId, config, indication);
                const existing = cart.find(function(item) {{ return item.key === key; }});
                if (existing) {{
                    existing.quantity += 1;
                }} else {{
                    cart.push({{
                        key: key,
                        productId: productId,
                        name: sheet.dataset.productName || "",
                        basePriceCents: basePriceCents,
                        unitPriceCents: unitPriceCents,
                        config: config,
                        summary: configSummary(config),
                        indication: indication,
                        quantity: 1
                    }});
                }}
                renderCart();
                closeSheet(sheet);
                if (noteInput) noteInput.value = "";
            }}

            function submissionId() {{
                if (!currentSubmissionId) {{
                    if (window.crypto && window.crypto.randomUUID) {{
                        currentSubmissionId = window.crypto.randomUUID();
                    }} else {{
                        currentSubmissionId = "client-" + Date.now() + "-" + Math.random().toString(16).slice(2);
                    }}
                }}
                return currentSubmissionId;
            }}

            function payloadItems() {{
                return cart.map(function(item) {{
                    return {{
                        producto_id: item.productId,
                        cantidad: item.quantity,
                        configuracion: item.config.map(function(group) {{
                            return {{
                                titulo: group.titulo,
                                valores: group.valores
                            }};
                        }}),
                        indicacion: item.indication || ""
                    }};
                }});
            }}

            async function sendCart() {{
                if (!cart.length || !submitUrl || sendRequest.disabled) return;
                sendRequest.disabled = true;
                sendRequest.textContent = "Enviando...";
                cartSubmitStatus.textContent = "";
                try {{
                    const response = await fetch(submitUrl, {{
                        method: "POST",
                        headers: {{"Content-Type": "application/json"}},
                        body: JSON.stringify({{
                            submission_id: submissionId(),
                            items: payloadItems()
                        }})
                    }});
                    const payload = await response.json().catch(function() {{ return {{}}; }});
                    if (!response.ok) {{
                        throw new Error(payload.error || "No se pudo enviar el pedido.");
                    }}
                    cart.splice(0, cart.length);
                    currentSubmissionId = "";
                    renderCart();
                    cartSubmitStatus.textContent = "Pedido enviado correctamente · Total " + money(Math.round(Number(payload.total_usd || 0) * 100));
                    sendRequest.textContent = "Enviar solicitud";
                    sendRequest.disabled = true;
                }} catch (error) {{
                    cartSubmitStatus.textContent = error.message || "No se pudo enviar el pedido.";
                    sendRequest.textContent = "Reintentar envio";
                    sendRequest.disabled = cart.length === 0;
                }}
            }}

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
                    if (sheet) {{
                        updateAddButton(sheet);
                        sheet.removeAttribute("hidden");
                    }}
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
                    updateAddButton(group.closest(".sheet"));
                }});
            }});
            document.querySelectorAll("[data-add-to-cart]").forEach(function(button) {{
                button.addEventListener("click", function() {{
                    addItemFromSheet(button.closest(".sheet"));
                }});
            }});
            cartBar.addEventListener("click", function() {{
                cartSheet.hidden = false;
            }});
            closeCart.addEventListener("click", function() {{
                cartSheet.hidden = true;
            }});
            if (sendRequest) {{
                sendRequest.addEventListener("click", sendCart);
            }}
            cartSheet.addEventListener("click", function(event) {{
                if (event.target === cartSheet) cartSheet.hidden = true;
            }});
            cartLines.addEventListener("click", function(event) {{
                const minus = event.target.closest("[data-cart-minus]");
                const plus = event.target.closest("[data-cart-plus]");
                const remove = event.target.closest("[data-cart-remove]");
                if (minus) {{
                    const index = Number(minus.dataset.cartMinus);
                    cart[index].quantity -= 1;
                    if (cart[index].quantity <= 0) cart.splice(index, 1);
                    renderCart();
                }} else if (plus) {{
                    const index = Number(plus.dataset.cartPlus);
                    cart[index].quantity += 1;
                    renderCart();
                }} else if (remove) {{
                    cart.splice(Number(remove.dataset.cartRemove), 1);
                    renderCart();
                }}
            }});
            renderCart();
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
    <div class="sheet" id="{modal_id}" hidden data-product-id="{producto.id}" data-product-name="{html.escape(producto.nombre, quote=True)}" data-price-cents="{int(round(producto.precio * 100))}">
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
            <div class="customer-note-group">
                <div class="option-title">
                    <span>Nota para cocina (opcional)</span>
                </div>
                <p class="option-help">Ejemplo: Sin cebolla, por favor</p>
                <textarea class="customer-note" data-customer-note maxlength="180" placeholder="Sin cebolla, por favor"></textarea>
            </div>
            <div class="sheet-actions">
                <button class="add-to-cart" type="button" data-add-to-cart>Agregar al pedido</button>
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
    precios_adicionales = opcion.precios_adicionales_centavos or {}
    valores = "".join(
        _render_valor_opcion(valor, precios_adicionales.get(valor, 0))
        for valor in opcion.valores
        if valor
    )
    ayuda = f"<p class='option-help'>{html.escape(opcion.ayuda)}</p>" if opcion.ayuda else ""
    return f"""
    <div class="option-group" data-option-group data-title="{html.escape(opcion.titulo, quote=True)}" data-max="{opcion.maximas}" data-required="{opcion.requeridas}" data-optional="{'true' if opcion.opcional else 'false'}">
        <div class="option-title">
            <span>{html.escape(_texto_cardinalidad(opcion))}</span>
            <span data-option-count>0 de {opcion.maximas}</span>
        </div>
        {ayuda}
        <div class="option-grid">{valores}</div>
    </div>
    """


def _render_valor_opcion(valor, recargo_centavos):
    recargo = int(recargo_centavos or 0)
    texto_recargo = f" +${recargo / 100:.2f}" if recargo else ""
    return (
        "<button class='option-pill' type='button' "
        f"data-option-value='{html.escape(valor, quote=True)}' "
        f"data-option-extra-cents='{recargo}'>"
        f"{html.escape(valor)}{texto_recargo}</button>"
    )


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
