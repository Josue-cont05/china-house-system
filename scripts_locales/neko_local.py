"""
neko_local.py

"Neko Local": launcher de escritorio (Tkinter, sin dependencias graficas
externas) para operar NekoPOS a diario sin abrir VS Code ni una terminal:

1. arranca el worker de cocina (script_comanda_cocina.py) como proceso
   hijo, si no esta ya activo;
2. abre NekoPOS en el navegador;
3. ofrece un asistente de configuracion de impresora cuando hace falta
   (deteccion de puertos, huella para sobrevivir a cambios de COM, prueba
   de impresion antes de guardar).

Toda la logica sin interfaz vive en modulos aparte, importados aqui, para
poder probarlos sin Tkinter y sin hardware:
- neko_config.py      -> configuracion local (%LOCALAPPDATA%\\NekoWok)
- port_detection.py   -> deteccion/huella de puertos serie
- single_instance.py  -> instancia unica del worker (mutex de Windows)
- launcher_core.py    -> arrancar/detener el worker, comprobar NekoPOS

Recibos: INICIAR NEKO arranca cocina Y recibos (dos procesos hijos
independientes, cada uno con su propio mutex de instancia unica, asi que
no se bloquean entre si pero cada uno impide un segundo de si mismo -
ver single_instance.py). DETENER detiene ambos. `GestorWorkerProceso`
(launcher_core.py) es generico: una instancia por worker.

EMPAQUETADO (PyInstaller, NekoLocal.exe): este archivo SI es el
entrypoint unico (seccion 4 de la mision de empaquetado). `main()`
despacha por argumentos:

    NekoLocal.exe                    -> GUI (este modulo)
    NekoLocal.exe --kitchen-worker   -> delega en script_comanda_cocina.main()
    NekoLocal.exe --receipt-worker   -> delega en script_factura.main()
    NekoLocal.exe --version          -> imprime version y termina
    NekoLocal.exe --diagnostics      -> imprime rutas/config (sin secretos) y termina
    NekoLocal.exe --help             -> ayuda (argparse), termina

Ninguno de --version/--diagnostics/--help toca Bluetooth, COM, polling ni
abre el navegador. En SOURCE, `python script_comanda_cocina.py`/
`python script_factura.py` siguen funcionando igual que siempre (no se
les quito su propio entrypoint) - son intercambiables con los modos
--kitchen-worker/--receipt-worker segun el contexto (ver
launcher_core.GestorWorkerProceso, que elige uno u otro automaticamente
segun resource_paths.es_frozen()).
"""

import argparse
import os
import subprocess
import sys
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

# PyInstaller con consola oculta (--noconsole/--windowed, usado tanto para
# la GUI como al relanzarse el propio .exe como --kitchen-worker/
# --receipt-worker) deja sys.stdout/sys.stderr en None: cualquier print()
# (los workers usan muchos, para diagnostico en consola durante
# desarrollo) lanzaria AttributeError. Solo se activa si de verdad estan
# en None (nunca pisa stdout real en modo fuente/consola).
if getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

import neko_config
import neko_log
import neko_version
import port_detection
import resource_paths
from launcher_core import (
    GestorWorkerProceso,
    MODO_FROZEN_COCINA,
    MODO_FROZEN_FACTURA,
    WORKER_COCINA_PATH,
    WORKER_FACTURA_PATH,
    nekopos_accesible,
    resolver_y_persistir_puerto,
)

POLL_INTERVAL_MS = 8000

log = neko_log.obtener_logger("neko_local")


def _imprimir_prueba(port, baudrate):
    """Prueba fisica minima e independiente de comanda_presentacion (no es
    una comanda: solo confirma que el puerto elegido imprime). Se ejecuta
    UNICAMENTE cuando el usuario pulsa "Imprimir prueba" en el asistente -
    nunca automaticamente."""
    from bluetooth_printer import BluetoothPrinter

    with BluetoothPrinter(port=port, baudrate=baudrate) as printer:
        printer.align("center")
        printer.set_bold(True)
        printer.print_line("NEKO LOCAL")
        printer.set_bold(False)
        printer.print_line("Prueba de impresion")
        printer.print_line(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        printer.feed(3)


def abrir_configuracion_bluetooth():
    """Abre la pantalla de Bluetooth de Windows para que el usuario haga
    el emparejamiento el mismo (nunca pairing programatico/hacks)."""
    try:
        subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:bluetooth"], shell=False)
        return True
    except Exception as e:
        messagebox.showerror("Neko Local", f"No se pudo abrir la configuracion de Bluetooth: {e}")
        return False


class AsistenteImpresora(tk.Toplevel):
    def __init__(self, master, on_guardado=None):
        super().__init__(master)
        self.title("Configurar impresora")
        self.resizable(False, False)
        self._on_guardado = on_guardado
        self._puerto_probado_ok = None

        self._lista = tk.Listbox(self, width=70, height=8)
        self._lista.pack(padx=12, pady=(12, 6))

        self._etiqueta_ayuda = ttk.Label(self, text="", foreground="#b00020", wraplength=420)
        self._etiqueta_ayuda.pack(padx=12, anchor="w")

        botones = ttk.Frame(self)
        botones.pack(padx=12, pady=8, fill="x")

        ttk.Button(botones, text="Buscar de nuevo", command=self._buscar).pack(side="left")
        ttk.Button(botones, text="Abrir Bluetooth", command=self._abrir_bluetooth).pack(
            side="left", padx=6
        )
        ttk.Button(botones, text="Imprimir prueba", command=self._probar).pack(side="left")
        self._btn_guardar = ttk.Button(
            botones, text="Confirmar y guardar", command=self._guardar, state="disabled"
        )
        self._btn_guardar.pack(side="right")

        self._puertos = []
        self._buscar()

    def _buscar(self):
        self._puertos = port_detection.listar_puertos()
        candidatos, resto = port_detection.listar_candidatos(self._puertos)

        self._lista.delete(0, tk.END)
        self._indice_a_puerto = []
        for puerto in candidatos:
            self._lista.insert(tk.END, f"★ {puerto.device} - {puerto.description or ''}")
            self._indice_a_puerto.append(puerto)
        for puerto in resto:
            self._lista.insert(tk.END, f"   {puerto.device} - {puerto.description or ''}")
            self._indice_a_puerto.append(puerto)

        self._btn_guardar.configure(state="disabled")
        self._puerto_probado_ok = None

        if not self._puertos:
            self._etiqueta_ayuda.configure(
                text="No se detecto ningun puerto serie. Empareja la impresora "
                "POS58 en Windows (Bluetooth) y pulsa 'Buscar de nuevo'."
            )
        elif len(candidatos) == 1:
            self._lista.selection_set(0)
            self._etiqueta_ayuda.configure(
                text="Se preselecciono el candidato mas probable. "
                "Puedes elegir otro puerto de la lista si no es el correcto."
            )
        elif not candidatos:
            self._etiqueta_ayuda.configure(
                text="No se identifico un candidato claro. Selecciona manualmente "
                "el puerto de tu impresora en la lista."
            )
        else:
            self._etiqueta_ayuda.configure(
                text="Hay varios candidatos posibles; selecciona el correcto en la lista."
            )

    def _abrir_bluetooth(self):
        abrir_configuracion_bluetooth()

    def _puerto_seleccionado(self):
        seleccion = self._lista.curselection()
        if not seleccion:
            return None
        return self._indice_a_puerto[seleccion[0]]

    def _probar(self):
        puerto = self._puerto_seleccionado()
        if puerto is None:
            messagebox.showwarning("Neko Local", "Selecciona un puerto de la lista primero.")
            return

        try:
            _imprimir_prueba(puerto.device, neko_config.DEFAULT_BAUDRATE)
        except Exception as e:
            self._puerto_probado_ok = None
            self._btn_guardar.configure(state="disabled")
            messagebox.showerror(
                "Neko Local",
                f"No se pudo imprimir en {puerto.device}: {e}\n\n"
                "Verifica que la impresora este encendida, emparejada y con papel.",
            )
            return

        respuesta = messagebox.askyesno(
            "Neko Local", f"¿Salio el ticket de prueba correctamente en {puerto.device}?"
        )
        if respuesta:
            self._puerto_probado_ok = puerto
            self._btn_guardar.configure(state="normal")
        else:
            self._puerto_probado_ok = None
            self._btn_guardar.configure(state="disabled")

    def _guardar(self):
        if self._puerto_probado_ok is None:
            return
        config = neko_config.cargar_config()
        config["printer_port"] = self._puerto_probado_ok.device
        config["printer_fingerprint"] = port_detection.construir_fingerprint(self._puerto_probado_ok)
        config["baudrate"] = config.get("baudrate") or neko_config.DEFAULT_BAUDRATE
        neko_config.guardar_config(config)
        if self._on_guardado:
            self._on_guardado(config)
        self.destroy()


class NekoLocalApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"NEKO WOK — {neko_version.version_texto()}")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        self.gestor_cocina = GestorWorkerProceso(
            worker_path=WORKER_COCINA_PATH, modo_frozen=MODO_FROZEN_COCINA
        )
        self.gestor_recibos = GestorWorkerProceso(
            worker_path=WORKER_FACTURA_PATH, modo_frozen=MODO_FROZEN_FACTURA
        )

        log.info(
            "%s iniciado (frozen=%s)", neko_version.version_texto(), resource_paths.es_frozen()
        )

        self._construir_ui()
        self._actualizar_estados()
        self._programar_poll()

    # ------------------------------------------------------------------
    def _construir_ui(self):
        marco = ttk.Frame(self.root, padding=14)
        marco.pack(fill="both", expand=True)

        self._var_nekopos = tk.StringVar(value="Verificando...")
        self._var_impresora = tk.StringVar(value="Verificando...")
        self._var_puerto = tk.StringVar(value="-")
        self._var_cocina = tk.StringVar(value="Detenida")
        self._var_recibos = tk.StringVar(value="Detenidos")

        for etiqueta, var in (
            ("NekoPOS", self._var_nekopos),
            ("Impresora", self._var_impresora),
            ("Puerto", self._var_puerto),
            ("Cocina", self._var_cocina),
            ("Recibos", self._var_recibos),
        ):
            fila = ttk.Frame(marco)
            fila.pack(fill="x", pady=2)
            ttk.Label(fila, text=etiqueta, width=12).pack(side="left")
            ttk.Label(fila, textvariable=var).pack(side="left")

        botones = ttk.Frame(marco)
        botones.pack(fill="x", pady=(12, 0))

        ttk.Button(botones, text="INICIAR NEKO", command=self._iniciar).pack(fill="x", pady=2)
        ttk.Button(botones, text="DETENER", command=self._detener).pack(fill="x", pady=2)
        ttk.Button(
            botones,
            text="CONFIGURAR IMPRESORA AUTOMÁTICAMENTE",
            command=self._configurar_automaticamente,
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones, text="Configuración avanzada", command=self._abrir_asistente
        ).pack(fill="x", pady=2)
        ttk.Button(botones, text="ABRIR NEKOPOS", command=self._abrir_nekopos).pack(
            fill="x", pady=2
        )

    # ------------------------------------------------------------------
    def _abrir_asistente(self):
        AsistenteImpresora(self.root, on_guardado=lambda config: self._actualizar_estados())

    def _configurar_automaticamente(self):
        """Flujo prioritario (seccion 12-15 de la mision de empaquetado):
        el socio NO elige COM. Prueba candidatos uno por uno, ordenados
        por probabilidad (fingerprint ya conocido primero), y solo
        pregunta SI/NO por cada uno. Nunca se envian bytes a un puerto
        que no paso el filtro de candidatos razonables."""
        config = neko_config.cargar_config()
        fingerprint_conocido = config.get("printer_fingerprint")
        baudrate = config.get("baudrate") or neko_config.DEFAULT_BAUDRATE

        puertos = port_detection.listar_puertos()
        candidatos = port_detection.ordenar_candidatos_por_probabilidad(puertos, fingerprint_conocido)
        log.info("Deteccion automatica: %d puertos, %d candidatos razonables", len(puertos), len(candidatos))

        if not candidatos:
            self._mostrar_sin_candidatos()
            return

        for puerto in candidatos:
            try:
                _imprimir_prueba(puerto.device, baudrate)
            except Exception as e:
                log.info("Candidato %s no respondio: %s", puerto.device, e)
                # Este candidato ni siquiera respondio: no tiene sentido
                # preguntar SI/NO de algo que no llego a imprimir nada;
                # se sigue con el siguiente candidato en silencio.
                continue

            log.info("Candidato probado: %s", puerto.device)
            salio = messagebox.askyesno(
                "Neko Local", f"¿Salió la prueba de impresión en {puerto.device}?"
            )
            log.info("Confirmacion candidato %s: %s", puerto.device, "SI" if salio else "NO")
            if salio:
                nueva_config = neko_config.cargar_config()
                nueva_config["printer_port"] = puerto.device
                nueva_config["printer_fingerprint"] = port_detection.construir_fingerprint(puerto)
                nueva_config["baudrate"] = baudrate
                neko_config.guardar_config(nueva_config)
                log.info("Impresora confirmada y guardada: %s", puerto.device)
                messagebox.showinfo("Neko Local", "IMPRESORA CONFIGURADA")
                self._actualizar_estados()
                return
            # NO: este candidato queda descartado solo durante esta
            # sesion de deteccion (no se persiste el descarte) y se sigue
            # con el siguiente candidato razonable.

        log.info("Deteccion automatica: ningun candidato confirmado")
        messagebox.showwarning(
            "Neko Local",
            "Ninguno de los candidatos detectados imprimió correctamente.\n\n"
            "Usa 'Configuración avanzada' para elegir el puerto manualmente,\n"
            "o confirma que la POS58 esté encendida y emparejada.",
        )

    def _mostrar_sin_candidatos(self):
        ventana = tk.Toplevel(self.root)
        ventana.title("No encontramos la POS58")
        ventana.resizable(False, False)

        ttk.Label(
            ventana,
            text=(
                "NO ENCONTRAMOS LA POS58\n\n"
                "1. Enciende la impresora.\n"
                "2. Verifica que esté emparejada en Bluetooth de Windows.\n"
                "3. Pulsa 'Emparejar impresora Bluetooth' si nunca se emparejó."
            ),
            justify="left",
            padding=14,
        ).pack()

        botones = ttk.Frame(ventana, padding=(14, 0, 14, 14))
        botones.pack(fill="x")

        ttk.Button(
            botones, text="Emparejar impresora Bluetooth", command=abrir_configuracion_bluetooth
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones,
            text="Buscar de nuevo",
            command=lambda: (ventana.destroy(), self._configurar_automaticamente()),
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones,
            text="Configuración avanzada",
            command=lambda: (ventana.destroy(), self._abrir_asistente()),
        ).pack(fill="x", pady=2)

    def _abrir_nekopos(self):
        webbrowser.open(neko_config.NEKOPOS_BASE_URL)

    def _iniciar(self):
        config = neko_config.cargar_config()
        if not neko_config.tiene_impresora_configurada(config):
            messagebox.showinfo(
                "Neko Local",
                "Todavia no hay una impresora configurada. Se abrira el asistente.",
            )
            self._abrir_asistente()
            return

        resultado = resolver_y_persistir_puerto(config)
        if resultado.status in ("ambiguous", "not_found"):
            messagebox.showwarning(
                "Neko Local",
                "No se pudo localizar la impresora configurada de forma segura. "
                "Usa 'Configurar impresora' para volver a elegirla.",
            )
            self._abrir_asistente()
            return

        if not self.gestor_cocina.activo:
            self.gestor_cocina.iniciar(resultado.port)
            log.info("Worker de cocina iniciado (puerto=%s)", resultado.port)
        if not self.gestor_recibos.activo:
            self.gestor_recibos.iniciar(resultado.port)
            log.info("Worker de recibos iniciado (puerto=%s)", resultado.port)

        self._abrir_nekopos()
        self._actualizar_estados()

    def _detener(self):
        self.gestor_cocina.detener()
        self.gestor_recibos.detener()
        self._actualizar_estados()

    # ------------------------------------------------------------------
    def _actualizar_estados(self):
        config = neko_config.cargar_config()

        if neko_config.tiene_impresora_configurada(config):
            resultado = resolver_y_persistir_puerto(config)
            if resultado.status in ("ok", "rematched"):
                self._var_impresora.set("configurada")
                self._var_puerto.set(resultado.port)
            elif resultado.status == "ambiguous":
                self._var_impresora.set("necesita configuracion (ambiguo)")
                self._var_puerto.set("-")
            else:
                self._var_impresora.set("no encontrada")
                self._var_puerto.set("-")
        else:
            self._var_impresora.set("necesita configuracion")
            self._var_puerto.set("-")

        self._var_cocina.set("activa" if self.gestor_cocina.activo else "detenida")
        self._var_recibos.set("activos" if self.gestor_recibos.activo else "detenidos")

        self._var_nekopos.set("verificando...")
        self.root.after(0, self._verificar_nekopos_async)

    def _verificar_nekopos_async(self):
        accesible = nekopos_accesible()
        self._var_nekopos.set("conectado" if accesible else "sin conexion")

    def _programar_poll(self):
        self.root.after(POLL_INTERVAL_MS, self._poll)

    def _poll(self):
        self._actualizar_estados()
        self._programar_poll()

    # ------------------------------------------------------------------
    def _al_cerrar(self):
        if not self.gestor_cocina.activo and not self.gestor_recibos.activo:
            self.root.destroy()
            return

        respuesta = messagebox.askyesnocancel(
            "Neko Local",
            "Cocina y/o recibos siguen activos. ¿Quieres mantenerlos imprimiendo y "
            "solo cerrar esta ventana?\n\nSi - mantener activos\n"
            "No - detener todo y cerrar\nCancelar - no cerrar",
        )
        if respuesta is None:
            return
        if not respuesta:
            self.gestor_cocina.detener()
            self.gestor_recibos.detener()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def _construir_parser():
    parser = argparse.ArgumentParser(
        prog="NekoLocal",
        description=f"{neko_version.version_texto()} - launcher local de NekoPOS "
        "(cocina + recibos por Bluetooth ESC/POS).",
    )
    parser.add_argument("--version", action="store_true", help="Muestra la version y termina.")
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Muestra version/rutas/config (sin secretos) y termina. No toca hardware.",
    )
    parser.add_argument(
        "--kitchen-worker",
        action="store_true",
        help="Modo interno: actua como worker de cocina (lo usa Neko Local, no es para uso manual).",
    )
    parser.add_argument(
        "--receipt-worker",
        action="store_true",
        help="Modo interno: actua como worker de recibos (lo usa Neko Local, no es para uso manual).",
    )
    parser.add_argument(
        "--port", default=None, help="Override manual de puerto para --kitchen-worker/--receipt-worker."
    )
    return parser


def _mostrar_diagnostics():
    config = neko_config.cargar_config()
    print(neko_version.version_texto())
    print(f"frozen: {resource_paths.es_frozen()}")
    print(f"directorio_base: {resource_paths.directorio_base()}")
    print(f"config_path: {neko_config.config_path()}")
    print(f"state_dir: {neko_config.state_dir()}")
    print(f"logs_dir: {neko_config.logs_dir()}")
    print(f"impresora configurada: {neko_config.tiene_impresora_configurada(config)}")
    if config.get("printer_port"):
        print(f"puerto guardado: {config.get('printer_port')}")


def main(argv=None):
    args = _construir_parser().parse_args(argv)

    if args.version:
        print(neko_version.version_texto())
        return 0

    if args.diagnostics:
        _mostrar_diagnostics()
        return 0

    if args.kitchen_worker:
        import script_comanda_cocina

        return script_comanda_cocina.main(["--port", args.port] if args.port else [])

    if args.receipt_worker:
        import script_factura

        return script_factura.main(["--port", args.port] if args.port else [])

    app = NekoLocalApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
