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

Decision de diseno (worker separado, no "--kitchen-worker" en este mismo
archivo): script_comanda_cocina.py ya esta fisicamente validado como
proceso independiente y su propia instancia unica (single_instance.py) es
mas simple de razonar como proceso de sistema operativo aparte que como un
modo interno de la GUI. Mantenerlo separado es la opcion de menor riesgo
para esta fase; nada impide fusionarlos despues si conviniera. Este mismo
"neko_local.py" (GUI) es el entrypoint pensado para empaquetarse a futuro
como NekoLocal.exe (PyInstaller) sin reescritura: `python neko_local.py`
hoy, `NekoLocal.exe` manana, mismo `main()`.

Recibos (Bloque B, todavia no implementado): la ventana ya deja hueco
visual para una fila "Recibos" con su propio estado, y `launcher_core`
esta pensado para poder sostener un segundo `GestorWorkerCocina`-like para
script_factura.py sin rediseño.
"""

import subprocess
import sys
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import neko_config
import port_detection
from launcher_core import GestorWorkerCocina, nekopos_accesible, resolver_y_persistir_puerto

POLL_INTERVAL_MS = 8000


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
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:bluetooth"], shell=False)
        except Exception as e:
            messagebox.showerror("Neko Local", f"No se pudo abrir la configuracion de Bluetooth: {e}")

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
        self.root.title("NEKO WOK — Neko Local")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)

        self.gestor_cocina = GestorWorkerCocina()

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

        for etiqueta, var in (
            ("NekoPOS", self._var_nekopos),
            ("Impresora", self._var_impresora),
            ("Puerto", self._var_puerto),
            ("Cocina", self._var_cocina),
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
            botones, text="CONFIGURAR IMPRESORA", command=self._abrir_asistente
        ).pack(fill="x", pady=2)
        ttk.Button(botones, text="ABRIR NEKOPOS", command=self._abrir_nekopos).pack(
            fill="x", pady=2
        )

    # ------------------------------------------------------------------
    def _abrir_asistente(self):
        AsistenteImpresora(self.root, on_guardado=lambda config: self._actualizar_estados())

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

        self._abrir_nekopos()
        self._actualizar_estados()

    def _detener(self):
        self.gestor_cocina.detener()
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
        if not self.gestor_cocina.activo:
            self.root.destroy()
            return

        respuesta = messagebox.askyesnocancel(
            "Neko Local",
            "La cocina esta activa. ¿Quieres mantenerla imprimiendo y solo cerrar "
            "esta ventana?\n\nSi - mantener cocina activa\nNo - detener cocina y cerrar\n"
            "Cancelar - no cerrar",
        )
        if respuesta is None:
            return
        if not respuesta:
            self.gestor_cocina.detener()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = NekoLocalApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
