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
import platform
import queue
import subprocess
import sys
import threading
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
import printer_diagnostics
import resource_paths
import windows_bluetooth
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


class VentanaProgreso(tk.Toplevel):
    """Ventana minima "Probando conexión... [barra]" que se muestra
    mientras `_PuenteHiloGUI` trabaja en segundo plano. Nunca se cierra
    con la X (evitaria dejar un hilo huerfano sin avisar): se cierra
    solo desde codigo, cuando el trabajo termina."""

    def __init__(self, master, titulo="Neko Local"):
        super().__init__(master)
        self.title(titulo)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._var_estado = tk.StringVar(value="Iniciando...")
        ttk.Label(self, textvariable=self._var_estado, padding=16, wraplength=320).pack()
        self._barra = ttk.Progressbar(self, mode="indeterminate", length=280)
        self._barra.pack(padx=16, pady=(0, 16))
        self._barra.start(12)

    def actualizar(self, texto):
        self._var_estado.set(texto)

    def cerrar(self):
        self._barra.stop()
        self.destroy()


class _PuenteHiloGUI:
    """Corre `funcion(progreso, preguntar)` en un hilo aparte para que la
    GUI de Tkinter NUNCA se bloquee (el fallo real que motivo este
    modulo: abrir un COM Bluetooth a medio crear puede colgarse
    indefinidamente).

    `funcion` recibe dos callbacks que puede llamar desde el hilo de
    trabajo con seguridad:
    - progreso(texto): informa un mensaje de estado (no bloquea).
    - preguntar(texto): pide una confirmacion SI/NO. BLOQUEA el hilo de
      TRABAJO (nunca el de Tkinter) hasta que el hilo principal muestre
      el messagebox real y responda.

    El resultado final de `funcion` llega a `on_terminado`, ya en el
    hilo principal (vía root.after), para que pueda tocar widgets con
    seguridad.
    """

    def __init__(self, root, funcion, on_progreso, on_terminado):
        self._root = root
        self._funcion = funcion
        self._on_progreso = on_progreso
        self._on_terminado = on_terminado
        self._cola = queue.Queue()

    def iniciar(self):
        threading.Thread(target=self._ejecutar, daemon=True).start()
        self._root.after(80, self._bombear)

    def _progreso(self, texto):
        self._cola.put(("progreso", texto))

    def _preguntar(self, texto):
        evento = threading.Event()
        caja = {}
        self._cola.put(("preguntar", texto, evento, caja))
        evento.wait()
        return caja.get("respuesta", False)

    def _ejecutar(self):
        try:
            resultado = self._funcion(self._progreso, self._preguntar)
        except Exception as e:
            resultado = ("error", e)
        self._cola.put(("fin", resultado))

    def _bombear(self):
        try:
            while True:
                item = self._cola.get_nowait()
                if item[0] == "progreso":
                    self._on_progreso(item[1])
                elif item[0] == "preguntar":
                    _, texto, evento, caja = item
                    caja["respuesta"] = messagebox.askyesno("Neko Local", texto)
                    evento.set()
                elif item[0] == "fin":
                    self._on_terminado(item[1])
                    return
        except queue.Empty:
            pass
        self._root.after(80, self._bombear)


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
            botones,
            text="SOLUCIONAR PROBLEMAS DE IMPRESORA",
            command=self._solucionar_problemas,
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
        """Flujo prioritario: el socio NO elige COM. Comparte el mismo
        motor de diagnostico que "SOLUCIONAR PROBLEMAS DE IMPRESORA"
        (seccion 2 de la mision de troubleshooting): ambos botones deben
        llevar exactamente al mismo lugar."""
        self._lanzar_diagnostico()

    def _solucionar_problemas(self):
        self._lanzar_diagnostico()

    def _lanzar_diagnostico(self, titulo="Configurando impresora..."):
        """Arranca el motor de diagnostico (printer_diagnostics) en un
        hilo aparte via _PuenteHiloGUI: la ventana de progreso queda
        respondiendo en todo momento, sin importar que abrir un COM
        Bluetooth a medio emparejar se cuelgue (el fallo real que motivo
        este asistente)."""
        self._ventana_progreso = VentanaProgreso(self.root, titulo=titulo)
        puente = _PuenteHiloGUI(
            self.root, self._trabajo_deteccion, self._ventana_progreso.actualizar, self._al_terminar_deteccion
        )
        puente.iniciar()

    def _trabajo_deteccion(self, progreso, preguntar):
        """Corre en el hilo de trabajo (nunca en el de Tkinter). Devuelve
        un printer_diagnostics.Diagnostico; nunca toca widgets."""
        config = neko_config.cargar_config()
        fingerprint_conocido = config.get("printer_fingerprint")
        baudrate = config.get("baudrate") or neko_config.DEFAULT_BAUDRATE

        progreso("Revisando Bluetooth...")
        bluetooth_ok, pos58_pareada = windows_bluetooth.evaluar_bluetooth()
        log.info("Diagnostico: bluetooth=%s pos58_pareada=%s", bluetooth_ok, pos58_pareada)

        progreso("Buscando impresora POS58...")
        puertos = port_detection.listar_puertos()
        candidatos = port_detection.ordenar_candidatos_por_probabilidad(puertos, fingerprint_conocido)
        log.info("Diagnostico: %d puertos, %d candidatos razonables", len(puertos), len(candidatos))

        def abridor(puerto):
            _imprimir_prueba(puerto, baudrate)

        def probador(puerto):
            return printer_diagnostics.probar_apertura(abridor, puerto)

        asistente = printer_diagnostics.AsistenteDeteccion(
            candidatos=candidatos,
            probador=probador,
            preguntar_si_no=lambda: preguntar("¿Salió la prueba de impresión correctamente?"),
            en_progreso=progreso,
            log=log,
        )
        estado, puerto_confirmado, resultados = asistente.ejecutar()

        if estado == printer_diagnostics.ESTADO_OK:
            nueva_config = neko_config.cargar_config()
            nueva_config["printer_port"] = puerto_confirmado.device
            nueva_config["printer_fingerprint"] = port_detection.construir_fingerprint(puerto_confirmado)
            nueva_config["baudrate"] = baudrate
            neko_config.guardar_config(nueva_config)
            log.info("Impresora confirmada y guardada: %s", puerto_confirmado.device)

        return printer_diagnostics.construir_diagnostico(
            candidatos=candidatos,
            resultados=resultados,
            estado=estado,
            puerto_confirmado=puerto_confirmado,
            bluetooth=bluetooth_ok,
            pos58_pareada=pos58_pareada,
        )

    def _al_terminar_deteccion(self, resultado):
        self._ventana_progreso.cerrar()

        if isinstance(resultado, tuple) and len(resultado) == 2 and resultado[0] == "error":
            log.info("Diagnostico: error inesperado: %s", resultado[1])
            messagebox.showerror(
                "Neko Local", f"Ocurrió un problema inesperado al diagnosticar la impresora: {resultado[1]}"
            )
            return

        diagnostico = resultado
        if diagnostico.estado == printer_diagnostics.ESTADO_SIN_CANDIDATOS:
            self._mostrar_sin_candidatos()
        elif diagnostico.estado == printer_diagnostics.ESTADO_OK:
            messagebox.showinfo("Neko Local", "IMPRESORA CONFIGURADA")
            self._actualizar_estados()
        else:  # ESTADO_PAREADA_SIN_ENLACE
            self._mostrar_asistente_reparacion(diagnostico)

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

    def _mostrar_asistente_reparacion(self, diagnostico):
        """Windows emparejó la POS58, pero ningún candidato pudo
        abrirse: exactamente el caso real (COM3/COM4 ambos fallan) que
        motivó este asistente. Nunca se pide elegir COM manualmente."""
        ventana = tk.Toplevel(self.root)
        ventana.title("Neko Local — Reparar impresora")
        ventana.resizable(False, False)

        marco = ttk.Frame(ventana, padding=14)
        marco.pack()
        ttk.Label(marco, text="REPARAR IMPRESORA", font=("", 11, "bold")).pack(anchor="w", pady=(0, 6))

        for etiqueta, valor in printer_diagnostics.resumen_humano(diagnostico):
            signo = "✓" if valor in ("OK", "Emparejada") else ("✕" if valor == "Problema" else "…")
            ttk.Label(marco, text=f"{signo} {etiqueta}: {valor}").pack(anchor="w")

        ttk.Label(
            marco,
            text=(
                "\nWindows emparejó la impresora, pero todavía no logramos\n"
                "crear una conexión de impresión que funcione."
            ),
            justify="left",
        ).pack(anchor="w", pady=(8, 8))

        botones = ttk.Frame(marco)
        botones.pack(fill="x")
        ttk.Button(
            botones, text="INTENTAR REPARAR", command=lambda: (ventana.destroy(), self._intentar_reparar())
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones,
            text="VOLVER A EMPAREJAR POS58",
            command=lambda: (ventana.destroy(), self._mostrar_guia_reemparejar()),
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones, text="Ver detalles técnicos", command=lambda: self._mostrar_detalles(diagnostico)
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones, text="Copiar diagnóstico", command=lambda: self._copiar_diagnostico(diagnostico)
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones, text="Guardar diagnóstico", command=lambda: self._guardar_diagnostico(diagnostico)
        ).pack(fill="x", pady=2)

    def _mostrar_guia_reemparejar(self):
        ventana = tk.Toplevel(self.root)
        ventana.title("Reemparejar POS58")
        ventana.resizable(False, False)

        ttk.Label(
            ventana,
            text=(
                "1. Enciende la POS58.\n"
                "2. En Windows (Bluetooth y dispositivos), quita el\n"
                "   emparejamiento anterior de la POS58 si aparece,\n"
                "   y vuelve a emparejarla.\n"
                "3. Cuando Windows termine, vuelve aquí."
            ),
            justify="left",
            padding=14,
        ).pack()

        botones = ttk.Frame(ventana, padding=(14, 0, 14, 14))
        botones.pack(fill="x")
        ttk.Button(
            botones, text="Abrir Bluetooth de Windows", command=abrir_configuracion_bluetooth
        ).pack(fill="x", pady=2)
        ttk.Button(
            botones,
            text="YA TERMINÉ — COMPROBAR DE NUEVO",
            command=lambda: (ventana.destroy(), self._lanzar_diagnostico()),
        ).pack(fill="x", pady=2)

    def _intentar_reparar(self):
        """INTENTAR REPARAR (automatico, sin intervencion del usuario mas
        alla de confirmar SI/NO en la prueba de impresion): refresca la
        lista de puertos dandole tiempo a un enlace Bluetooth recien
        creado, y vuelve a correr la deteccion completa."""

        def trabajo(progreso, preguntar):
            progreso("Actualizando dispositivos...")
            snapshot_antes = port_detection.listar_puertos()
            _actuales, nuevos = printer_diagnostics.esperar_puertos_nuevos(
                port_detection.listar_puertos, snapshot_antes
            )
            log.info("Reparar: %d puertos antes, %d nuevos tras esperar", len(snapshot_antes), len(nuevos))
            return self._trabajo_deteccion(progreso, preguntar)

        self._ventana_progreso = VentanaProgreso(self.root, titulo="Reparando...")
        puente = _PuenteHiloGUI(
            self.root, trabajo, self._ventana_progreso.actualizar, self._al_terminar_deteccion
        )
        puente.iniciar()

    def _texto_diagnostico(self, diagnostico):
        return printer_diagnostics.formatear_diagnostico_texto(
            diagnostico, neko_version.version_texto(), resource_paths.es_frozen(), platform.platform()
        )

    def _mostrar_detalles(self, diagnostico):
        ventana = tk.Toplevel(self.root)
        ventana.title("Detalles técnicos")
        caja = tk.Text(ventana, width=80, height=22, wrap="word")
        caja.insert("1.0", self._texto_diagnostico(diagnostico))
        caja.configure(state="disabled")
        caja.pack(padx=8, pady=8)

    def _copiar_diagnostico(self, diagnostico):
        self.root.clipboard_clear()
        self.root.clipboard_append(self._texto_diagnostico(diagnostico))
        messagebox.showinfo("Neko Local", "Diagnóstico copiado. Puedes pegarlo en un mensaje o correo.")

    def _guardar_diagnostico(self, diagnostico):
        ruta = printer_diagnostics.guardar_diagnostico(self._texto_diagnostico(diagnostico))
        log.info("Diagnostico guardado: %s", ruta)
        messagebox.showinfo("Neko Local", f"Diagnóstico guardado en:\n{ruta}")

    def _abrir_nekopos(self):
        webbrowser.open(neko_config.NEKOPOS_BASE_URL)

    def _iniciar(self):
        config = neko_config.cargar_config()
        if not neko_config.tiene_impresora_configurada(config):
            messagebox.showinfo(
                "Neko Local",
                "Todavía no hay una impresora configurada. Se abrirá la configuración automática.",
            )
            self._configurar_automaticamente()
            return

        resultado = resolver_y_persistir_puerto(config)
        if resultado.status in ("ambiguous", "not_found"):
            messagebox.showwarning(
                "Neko Local",
                "La impresora necesita atención: no se pudo localizar de forma segura.",
            )
            self._solucionar_problemas()
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
                self._var_impresora.set("necesita atención (varios puertos posibles)")
                self._var_puerto.set("-")
            else:
                self._var_impresora.set("necesita atención")
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
