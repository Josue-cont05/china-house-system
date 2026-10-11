"""
design_system.py (presentacion)

Design system OFICIAL de NekoPOS: tema oscuro tomado del rediseno de
/orden/<id>. Es la unica fuente de colores y componentes visuales
compartidos; `web_app.estilos_base()` devuelve `estilos_design_system()`,
asi que TODA pantalla que ya inyecta estilos_base() recibe:

1. TOKENS (:root): paleta oficial (--bg-*, --text-*, --accent-*, estados)
   + espaciado/radios/sombras/alturas tactiles.
2. ALIAS LEGACY: las variables historicas (--panel, --tarjeta, --borde,
   --texto, --verde-neko, --naranja, --azul, --rojo...) apuntan a los
   tokens oficiales. Las pantallas aun no migradas adoptan la paleta sin
   tocar su marcado; al migrarlas se reemplazan por los tokens.
3. BASE: body, header/navegacion global (barra_superior), inputs,
   botones y tablas genericas -- los mismos selectores de siempre, ahora
   sobre tokens.
4. COMPONENTES `ds-*`: clases nuevas con prefijo para no chocar con los
   estilos locales que muchas pantallas siguen definiendo. Las pantallas
   migradas usan SOLO estas clases + layout propio minimo.

Por que un string Python y no /static/*.css: todo el HTML se genera con
f-strings y estilos inline en <style>; Neko Local se empaqueta con
PyInstaller sin carpeta static. Un modulo Python viaja con el codigo sin
tocar el empaquetado ni el despliegue. Si algun dia se sirve como archivo,
basta exponer `estilos_design_system()` en una ruta con cache.

CASCADA (importante): barra_superior() vuelve a inyectar estilos_base()
dentro del <body>, DESPUES del <style> de cada pagina. Una regla local con
la misma especificidad que una de DS_BASE (p. ej. `.card`, `th`, `table`)
pierde. En pantallas migradas, escribir las reglas locales con un
contenedor delante (`.panel-der .card`, `.contenido th`) o usar solo
clases ds-*. Paso pendiente del plan: cuando todas las pantallas incluyan
estilos_base() en su <head>, barra_superior dejara de reinyectarlo.

Reglas para pantallas nuevas/migradas:
- Colores SOLO via tokens (nunca hex sueltos).
- Botones: .ds-btn + variante (.ds-btn-primary/-secondary/-danger/
  -warning/-ghost), tamano .ds-btn-sm/.ds-btn-block.
- Estados: .ds-badge + (-success/-warning/-danger/-info/-neutral).
- Mensajes: .ds-alert + variante. Totales/KPI: .ds-kpi-grid > .ds-kpi.
- Nada de fondos saturados completos: el color orienta (borde, badge,
  icono), no rellena.
"""

DS_TOKENS = """
:root {
    /* Paleta oficial */
    --bg-main: #0F1115;
    --bg-panel: #161A22;
    --bg-card: #1C2230;
    --bg-hover: #242C3B;
    --bg-header: #12151C;
    --border: #2E3747;
    --border-strong: #3C4658;

    --text-primary: #F5F7FA;
    --text-secondary: #AAB3C2;
    --text-muted: #7D8796;
    --text-on-accent: #0B0D10;

    --accent-primary: #35D07F;
    --accent-primary-hover: #4BDB8E;
    --accent-primary-soft: rgba(53, 208, 127, 0.14);
    --accent-secondary: #F2B94B;
    --accent-secondary-hover: #F6C766;

    --success: #35D07F;
    --success-soft: rgba(53, 208, 127, 0.14);
    --warning: #F2B94B;
    --warning-soft: rgba(242, 185, 75, 0.14);
    --danger: #EF4444;
    --danger-strong: #DC2626;
    --danger-soft: rgba(239, 68, 68, 0.12);
    --danger-text: #FCA5A5;
    --info: #4DA3FF;
    --info-strong: #2563EB;
    --info-soft: rgba(77, 163, 255, 0.14);

    /* Forma y ritmo */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-pill: 999px;
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-5: 20px;
    --space-6: 24px;
    --touch-min: 44px;
    --touch-lg: 52px;
    --font-sans: system-ui, 'Segoe UI', Roboto, Arial, sans-serif;
    --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.22);
    --shadow-md: 0 10px 24px rgba(0, 0, 0, 0.28);
    --shadow-lg: 0 24px 50px rgba(0, 0, 0, 0.45);
    --focus-ring: 0 0 0 3px rgba(53, 208, 127, 0.25);

    /* Alias legacy -> tokens (no usar en codigo nuevo) */
    --fondo-principal: var(--bg-main);
    --gris-fondo: var(--bg-main);
    --panel: var(--bg-panel);
    --panel-secundario: var(--bg-card);
    --tarjeta: var(--bg-card);
    --borde: var(--border);
    --texto: var(--text-primary);
    --carbon: var(--text-primary);
    --texto-secundario: var(--text-secondary);
    --verde-neko: var(--accent-primary);
    --verde: var(--accent-primary);
    --verde-oscuro: var(--accent-primary-hover);
    --hover-neko: var(--accent-primary-hover);
    --naranja: var(--accent-secondary);
    --dorado: var(--accent-secondary);
    --crema: #fef3c7;
    --azul: var(--info-strong);
    --rojo: var(--danger-strong);
    --sombra: var(--shadow-md);
    --sombra-suave: var(--shadow-sm), 0 8px 20px rgba(0, 0, 0, 0.14);
}
"""

DS_BASE = """
* { box-sizing: border-box; }
body {
    font-family: var(--font-sans);
    color: var(--text-primary);
    background: var(--bg-main);
    min-height: 100vh;
}
[hidden] { display: none !important; }
a:focus-visible, button:focus-visible, summary:focus-visible,
input:focus-visible, select:focus-visible, textarea:focus-visible {
    outline: 3px solid var(--info);
    outline-offset: 2px;
}

/* ---- Header / navegacion global (barra_superior) ---- */
.header {
    background: var(--bg-header);
    color: var(--text-primary);
    padding: 10px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    border-bottom: 1px solid var(--border);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.25);
    position: sticky;
    top: 0;
    z-index: 20;
}
.titulo {
    font-size: 22px;
    font-weight: 900;
    letter-spacing: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--accent-primary);
}
.titulo span.brand-dot { color: var(--accent-primary); }
a.titulo-inicio { text-decoration: none; white-space: nowrap; flex-shrink: 0; border-radius: 10px; padding: 4px 6px; margin: -4px -6px; transition: background 0.15s ease, opacity 0.15s ease; }
a.titulo-inicio:hover { background: var(--accent-primary-soft); }
a.titulo-inicio:active { opacity: 0.8; }
a.titulo-inicio:focus-visible { outline: 3px solid var(--accent-primary); outline-offset: 2px; }
.header-acciones { display: flex; align-items: center; gap: 10px; min-width: 0; }
.header-usuario { font-size: 13px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 220px; }
.header-usuario b { color: var(--text-primary); }
.menu-top { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.menu-top a, .volver, .btn-accion, .btn-ver, .btn-cobrar, .btn-acceso {
    color: var(--text-primary);
    text-decoration: none;
    font-weight: 700;
    border-radius: var(--radius-sm);
    min-height: 40px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
}
.menu-top a { background: var(--bg-card); border: 1px solid var(--border); padding: 8px 12px; font-size: 13px; transition: background 0.15s ease, border-color 0.15s ease; }
.menu-top a:hover { background: var(--bg-hover); border-color: var(--border-strong); }
.contenido, .contenedor { max-width: 1280px; margin: 0 auto; }
.card, .panel-izq, .panel-der, .panel, .login-box {
    background: var(--bg-panel);
    color: var(--text-primary);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
}
h1, h2, h3 { letter-spacing: -0.3px; color: var(--text-primary); }

/* ---- Formularios ---- */
input, select, textarea {
    border: 1px solid var(--border);
    min-height: 46px;
    background: var(--bg-card);
    color: var(--text-primary);
    border-radius: var(--radius-sm);
    padding: 10px 14px;
    font-size: 15px;
}
input::placeholder, textarea::placeholder { color: var(--text-muted); }
input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--accent-primary);
    box-shadow: var(--focus-ring);
}
button, .btn, .btn-agregar, .btn-guardar {
    font-weight: 800;
    min-height: 48px;
    box-shadow: var(--shadow-sm);
    border-radius: 10px;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
button:hover, .btn:hover, .btn-agregar:hover, .btn-guardar:hover { box-shadow: 0 8px 18px rgba(0, 0, 0, 0.22); }
button:active, .btn:active { transform: scale(0.98); }

/* ---- Tablas genericas ---- */
table { color: var(--text-primary); }
th { background: var(--bg-card); color: var(--accent-primary); border-bottom: 1px solid var(--border); }
td { border-bottom: 1px solid var(--border); }
tbody tr:nth-child(even) { background: rgba(255, 255, 255, 0.02); }
tbody tr:hover { background: rgba(255, 255, 255, 0.045); }

@media (min-width: 900px) {
    .contenedor { flex-direction: row !important; align-items: flex-start; padding: 18px !important; }
    .panel-izq { flex: 0 0 360px; }
    .panel-der { flex: 1; }
    .card { flex-direction: row !important; justify-content: space-between; align-items: center; }
}
@media (max-width: 768px) {
    .header { padding: 8px 12px; gap: 8px; }
    .titulo { font-size: 19px; }
    .header-usuario { display: none; }
    .menu-top { justify-content: stretch; }
    .menu-top a { flex: 1 1 42%; }
}
"""

DS_COMPONENTES = """
/* ---- Layout de pagina ---- */
.ds-page { max-width: 1280px; margin: 0 auto; padding: var(--space-5); }
.ds-page-narrow { max-width: 760px; }
.ds-page-header { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; margin: 0 0 var(--space-4); }
.ds-page-title { margin: 0; font-size: 26px; font-weight: 900; color: var(--text-primary); }
.ds-page-subtitle { margin: 4px 0 0; color: var(--text-secondary); font-size: 15px; }
.ds-section-title { margin: var(--space-5) 0 var(--space-2); font-size: 12px; font-weight: 800; letter-spacing: 0.8px; text-transform: uppercase; color: var(--text-muted); }

/* ---- Superficies ---- */
.ds-panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-5); box-shadow: var(--shadow-sm); }
.ds-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: var(--space-4); }
.ds-card-interactive { transition: background 0.15s ease, border-color 0.15s ease; }
.ds-card-interactive:hover { background: var(--bg-hover); border-color: var(--border-strong); }
.ds-accent-left { border-left: 4px solid var(--ds-accent, var(--border)); }
.ds-empty { text-align: center; padding: 36px 16px; color: var(--text-muted); font-size: 15px; border: 1px dashed var(--border); border-radius: var(--radius-md); }

/* ---- Botones ---- */
.ds-btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    min-height: var(--touch-min); padding: 10px 16px;
    border-radius: var(--radius-md); border: 1px solid transparent;
    font-family: inherit; font-size: 15px; font-weight: 800; line-height: 1.2;
    text-decoration: none; text-align: center; cursor: pointer;
    box-shadow: none;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}
.ds-btn:active { transform: scale(0.98); }
.ds-btn:disabled, .ds-btn[aria-disabled="true"] { opacity: 0.55; cursor: not-allowed; transform: none; }
.ds-btn-primary { background: var(--accent-primary); border-color: var(--accent-primary); color: var(--text-on-accent); }
.ds-btn-primary:hover { background: var(--accent-primary-hover); }
.ds-btn-warning { background: var(--accent-secondary); border-color: var(--accent-secondary); color: var(--text-on-accent); }
.ds-btn-warning:hover { background: var(--accent-secondary-hover); }
.ds-btn-secondary { background: var(--bg-card); border-color: var(--border); color: var(--text-primary); }
.ds-btn-secondary:hover { background: var(--bg-hover); border-color: var(--border-strong); }
.ds-btn-ghost { background: transparent; border-color: var(--border); color: var(--accent-primary); }
.ds-btn-ghost:hover { background: var(--accent-primary-soft); }
.ds-btn-danger { background: var(--danger-soft); border-color: rgba(239, 68, 68, 0.5); color: var(--danger-text); }
.ds-btn-danger:hover { background: rgba(239, 68, 68, 0.2); }
.ds-btn-sm { min-height: 36px; padding: 6px 12px; font-size: 13px; border-radius: var(--radius-sm); }
.ds-btn-lg { min-height: var(--touch-lg); font-size: 16px; }
.ds-btn-block { display: flex; width: 100%; }
.ds-btn-group { display: flex; flex-wrap: wrap; gap: var(--space-2); }

/* ---- Formularios ---- */
.ds-field { display: block; margin: 0 0 var(--space-3); }
.ds-label { display: block; margin: 0 0 6px; color: var(--text-secondary); font-size: 13px; font-weight: 700; }
.ds-input { width: 100%; margin: 0; }
.ds-segmented { display: grid; grid-template-columns: repeat(var(--ds-segmentos, 3), minmax(0, 1fr)); gap: var(--space-2); margin: 0 0 var(--space-3); }
.ds-segmented-option { position: relative; display: block; cursor: pointer; }
.ds-segmented-option input { position: absolute; opacity: 0; width: 1px; height: 1px; min-height: 0; margin: 0; padding: 0; pointer-events: none; }
.ds-segmented-option span {
    display: flex; align-items: center; justify-content: center;
    min-height: var(--touch-lg); padding: 8px 4px; gap: 4px;
    border-radius: var(--radius-md); border: 1.5px solid var(--border);
    background: var(--bg-card); color: var(--text-secondary);
    font-size: 14px; font-weight: 800; text-align: center; white-space: nowrap;
    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}
.ds-segmented-option:hover span { border-color: var(--border-strong); color: var(--text-primary); }
.ds-segmented-option input:checked + span { background: var(--accent-primary-soft); border-color: var(--accent-primary); color: var(--accent-primary); box-shadow: inset 0 0 0 1px var(--accent-primary); }
.ds-segmented-option input:focus-visible + span { outline: 3px solid var(--info); outline-offset: 2px; }

/* ---- Tablas ---- */
.ds-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; border: 1px solid var(--border); border-radius: var(--radius-md); }
.ds-table { width: 100%; border-collapse: collapse; }
.ds-table th { position: sticky; top: 0; padding: 10px 12px; background: var(--bg-card); color: var(--text-secondary); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; text-align: left; }
.ds-table td { padding: 10px 12px; vertical-align: top; }
.ds-num { text-align: right; white-space: nowrap; font-weight: 800; font-variant-numeric: tabular-nums; }

/* ---- Badges / estados ---- */
.ds-badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: var(--radius-pill); border: 1px solid; font-size: 12px; font-weight: 900; letter-spacing: 0.4px; text-transform: uppercase; white-space: nowrap; }
.ds-badge-success { color: var(--success); background: var(--success-soft); border-color: rgba(53, 208, 127, 0.45); }
.ds-badge-warning { color: var(--warning); background: var(--warning-soft); border-color: rgba(242, 185, 75, 0.45); }
.ds-badge-danger { color: var(--danger-text); background: var(--danger-soft); border-color: rgba(239, 68, 68, 0.45); }
.ds-badge-info { color: var(--info); background: var(--info-soft); border-color: rgba(77, 163, 255, 0.45); }
.ds-badge-neutral { color: var(--text-secondary); background: var(--bg-card); border-color: var(--border); }

/* ---- Alertas ---- */
.ds-alert { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; margin: 0 0 var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--border); border-left-width: 4px; background: var(--bg-card); color: var(--text-primary); font-size: 15px; line-height: 1.45; }
.ds-alert-success { border-color: rgba(53, 208, 127, 0.45); border-left-color: var(--success); background: var(--success-soft); }
.ds-alert-warning { border-color: rgba(242, 185, 75, 0.45); border-left-color: var(--warning); background: var(--warning-soft); }
.ds-alert-danger { border-color: rgba(239, 68, 68, 0.45); border-left-color: var(--danger); background: var(--danger-soft); }
.ds-alert-info { border-color: rgba(77, 163, 255, 0.45); border-left-color: var(--info); background: var(--info-soft); }

/* ---- KPI / totales ---- */
.ds-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: var(--space-3); margin: var(--space-3) 0; }
.ds-kpi { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px; }
.ds-kpi small { display: block; color: var(--text-secondary); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
.ds-kpi b { display: block; margin-top: 6px; font-size: 24px; font-weight: 900; color: var(--text-primary); font-variant-numeric: tabular-nums; }
.ds-kpi-accent b { color: var(--accent-primary); }
.ds-total { font-size: 26px; font-weight: 900; color: var(--accent-primary); letter-spacing: -0.4px; }

/* ---- Pestanas ---- */
.ds-tabs { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: var(--space-3) 0 var(--space-4); }
.ds-tab { display: inline-flex; align-items: center; justify-content: center; min-height: var(--touch-min); padding: 8px 16px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: var(--bg-panel); color: var(--text-secondary); font-weight: 800; text-decoration: none; }
.ds-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.ds-tab.activo { background: var(--accent-primary-soft); border-color: var(--accent-primary); color: var(--accent-primary); }

/* ---- Modal / dialogo ---- */
.ds-modal-backdrop { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; padding: var(--space-4); background: rgba(5, 7, 10, 0.7); }
.ds-modal-page { min-height: calc(100vh - 90px); display: flex; align-items: center; justify-content: center; padding: var(--space-5) var(--space-4); }
.ds-modal { width: min(520px, 100%); max-height: 90vh; overflow-y: auto; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-6); box-shadow: var(--shadow-lg); color: var(--text-primary); }
.ds-modal-title { margin: 0 0 10px; font-size: 24px; font-weight: 900; color: var(--text-primary); }
.ds-modal-text { margin: 0 0 8px; color: var(--text-secondary); font-size: 16px; line-height: 1.45; }
.ds-modal-text strong { color: var(--text-primary); }
.ds-modal-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: var(--space-5); }
.ds-modal-actions form { margin: 0; }
.ds-modal-actions .ds-btn { width: 100%; min-height: var(--touch-lg); }

/* ---- Navegacion global: boton Menu + drawer (barra_superior) ---- */
.ds-menu-trigger {
    display: inline-flex; align-items: center; gap: 8px;
    min-height: var(--touch-min); padding: 0 16px;
    border-radius: var(--radius-md); border: 1px solid var(--border);
    background: var(--bg-card); color: var(--text-primary);
    font-family: inherit; font-size: 15px; font-weight: 800; box-shadow: none; cursor: pointer;
}
.ds-menu-trigger:hover, .ds-menu-trigger[aria-expanded="true"] { background: var(--bg-hover); border-color: var(--accent-primary); }
.ds-menu-trigger-icono { font-size: 18px; line-height: 1; }
.ds-drawer-backdrop { position: fixed; inset: 0; z-index: 900; background: rgba(5, 7, 10, 0.6); opacity: 0; pointer-events: none; transition: opacity 0.2s ease; }
.ds-drawer-backdrop.activo { opacity: 1; pointer-events: auto; }
.ds-drawer {
    position: fixed; top: 0; right: 0; bottom: 0; z-index: 910;
    width: min(380px, 88vw);
    display: flex; flex-direction: column;
    background: var(--bg-panel); border-left: 1px solid var(--border);
    box-shadow: var(--shadow-lg);
    transform: translateX(102%); visibility: hidden;
    transition: transform 0.22s ease, visibility 0s linear 0.22s;
}
.ds-drawer.abierto { transform: none; visibility: visible; transition: transform 0.22s ease, visibility 0s; }
body.ds-drawer-abierto { overflow: hidden; }
.ds-drawer-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border); }
.ds-drawer-title { font-size: 18px; font-weight: 900; color: var(--text-primary); }
.ds-drawer-subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 2px; }
.ds-drawer-close { width: var(--touch-min); min-height: var(--touch-min); padding: 0; border-radius: var(--radius-md); border: 1px solid var(--border); background: var(--bg-card); color: var(--text-primary); font-size: 16px; box-shadow: none; cursor: pointer; }
.ds-drawer-body { flex: 1 1 auto; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 6px 12px calc(16px + env(safe-area-inset-bottom, 0px)); }
.ds-nav-group { padding: 8px 0; border-bottom: 1px solid var(--border); }
.ds-nav-group:last-child { border-bottom: none; }
.ds-nav-group-title { padding: 6px 8px; font-size: 11px; font-weight: 800; letter-spacing: 0.8px; text-transform: uppercase; color: var(--text-muted); }
.ds-nav-item {
    display: flex; align-items: center; gap: 12px;
    min-height: var(--touch-min); padding: 8px 10px;
    border-radius: var(--radius-sm); border: 1px solid transparent;
    color: var(--text-primary); text-decoration: none; font-size: 15px; font-weight: 700;
}
.ds-nav-item:hover { background: var(--bg-hover); }
.ds-nav-item.activo { background: var(--accent-primary-soft); border-color: rgba(53, 208, 127, 0.45); color: var(--accent-primary); }
.ds-nav-icono { width: 24px; text-align: center; font-size: 17px; flex-shrink: 0; }
@media (min-width: 1024px) {
    .ds-drawer { width: 560px; }
    .ds-drawer-body { display: grid; grid-template-columns: 1fr 1fr; column-gap: 16px; align-content: start; }
    .ds-nav-group { border-bottom: none; }
}

/* ---- Listas simples ---- */
.ds-list { list-style: none; margin: 0; padding: 0; }
.ds-list li { display: flex; justify-content: space-between; gap: var(--space-3); padding: 10px 0; border-bottom: 1px solid var(--border); }
.ds-list li:last-child { border-bottom: none; }

@media (max-width: 760px) {
    .ds-page { padding: var(--space-3); }
    .ds-page-title { font-size: 22px; }
    .ds-modal { padding: var(--space-5); }
    .ds-modal-actions { grid-template-columns: 1fr; }
    .ds-modal-actions > :last-child { order: -1; }
    .ds-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (prefers-reduced-motion: reduce) {
    * { transition: none !important; animation: none !important; }
}
"""


def estilos_design_system():
    return DS_TOKENS + DS_BASE + DS_COMPONENTES
