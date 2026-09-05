# Neko Local

Launcher de escritorio (Tkinter) para operar NekoPOS a diario sin abrir
VS Code ni una terminal. Arranca el worker de impresión de comandas de
cocina y abre NekoPOS en el navegador. **No incluye recibos/facturas
todavía** (Bloque B pendiente).

## A. Uso diario

1. Enciende la PC y la impresora POS58.
2. Doble clic en el acceso directo **"INICIAR NEKO"** del Escritorio (o en
   `INICIAR_NEKO.bat`).
3. Se abre la ventana de Neko Local. Pulsa **INICIAR NEKO**.
4. Se abre NekoPOS en el navegador y el worker de cocina queda activo
   (fila "Cocina: activa").
5. Para terminar el día: pulsa **DETENER**, o simplemente cierra la
   ventana (te preguntará si quieres mantener la cocina activa o
   detenerla).

## B. Primera configuración (impresora)

Si "Impresora" muestra **necesita configuración**, pulsa
**CONFIGURAR IMPRESORA**:

1. Se listan los puertos serie detectados; los que parecen ser la POS58
   (Bluetooth SPP, YICHIP, etc.) aparecen marcados con `★`.
2. Si hay un único candidato claro, ya viene preseleccionado (puedes
   cambiarlo).
3. Pulsa **Imprimir prueba** — solo entonces se abre el puerto elegido y
   se envía un ticket corto de prueba. Nunca se prueba un puerto sin que
   lo pidas.
4. Confirma si el ticket salió bien y pulsa **Confirmar y guardar**.

La configuración se guarda en `%LOCALAPPDATA%\NekoWok\config.json`,
**única por computadora** — nunca se sube a git.

## C. Instalar en otra computadora (laptop de un socio)

1. Copia/clona la carpeta de NekoPOS completa.
2. Doble clic en `INSTALAR_NEKO_LOCAL.bat`.
3. El instalador: busca Python 3, crea un entorno virtual local (`.venv`,
   dentro de la carpeta del proyecto, sin tocar el Python del sistema),
   instala `pyserial`/`Pillow`/`requests`/`pywin32`, y crea el acceso
   directo "INICIAR NEKO" en el Escritorio. Es seguro ejecutarlo más de
   una vez (no duplica nada, no toca datos de NekoPOS).
4. Al final te pregunta si quieres abrir Neko Local — acepta y sigue la
   sección B para configurar esa impresora (cada PC tiene su propia
   configuración).

## D. Emparejar la POS58 por Bluetooth

Neko Local **no empareja Bluetooth por ti** (eso lo hace Windows). Si el
asistente no encuentra ningún puerto, mostrará
**"Empareja la impresora POS58 en Windows"** con un botón
**Abrir Bluetooth** (abre la configuración de Windows) y otro
**Buscar de nuevo** para reintentar la detección después de emparejar.

## E. Cambio automático de puerto COM

Windows puede reasignar la POS58 a otro COM (por ejemplo, de COM6 a
COM8) tras un reemparejamiento. Neko Local no depende de que el número
de puerto sea fijo:

- Guarda, junto al puerto, una **huella** de la impresora (hwid, número
  de serie, descripción, fabricante).
- Al iniciar: si el COM guardado sigue existiendo, lo usa tal cual. Si
  desapareció, busca esa huella entre los puertos actuales.
- Si encuentra **exactamente una** coincidencia, actualiza la
  configuración sola — no hace falta que nadie toque nada.
- Si hay **varias** coincidencias posibles (ambigüedad), **nunca elige al
  azar**: pide reconfigurar manualmente desde "CONFIGURAR IMPRESORA".

## F. Si no detecta la impresora

- Confirma que la POS58 está encendida y emparejada en
  Windows → Bluetooth y dispositivos.
- Usa **Buscar de nuevo** en el asistente.
- Si sigue sin aparecer, revisa el Administrador de dispositivos de
  Windows para confirmar que existe un puerto COM asignado al
  "Standard Serial over Bluetooth link" de esa impresora.

## G. Inicio y detención

- **INICIAR NEKO**: valida la impresora configurada, arranca el worker de
  cocina (si no está ya activo) y abre NekoPOS en el navegador.
- **DETENER**: cierra únicamente el worker que Neko Local inició — nunca
  procesos ajenos ni "todos los python.exe".
- El worker tiene protección de instancia única (mutex de Windows): si ya
  hay uno corriendo (por ejemplo, iniciado manualmente antes), un segundo
  intento lo detecta, muestra un mensaje y termina sin interferir.

## H. Ubicación de la configuración

```
%LOCALAPPDATA%\NekoWok\config.json
```

Si `LOCALAPPDATA` no existe en esa máquina, se usa `~/.nekowok/config.json`
como respaldo. El archivo nunca contiene secretos, solo puerto, baudrate y
la huella de la impresora. Si el archivo está corrupto, Neko Local lo
respalda como `config.json.bak` y pide reconfigurar en vez de fallar.

## I. Ejecutar manualmente (diagnóstico)

```
cd scripts_locales
python script_comanda_cocina.py              # usa la config guardada
python script_comanda_cocina.py --port COM6  # fuerza un puerto, ignora la config
python neko_local.py                         # abre la GUI directamente
```

## J. Futuro soporte de recibos (Bloque B)

La arquitectura ya deja espacio para un segundo worker (`script_factura.py`)
con su propia fila de estado ("Recibos: activa/detenida") gestionado por el
mismo Neko Local — `launcher_core.GestorWorkerCocina` es genérico por
diseño y `neko_config`/`port_detection` no asumen que solo exista una
impresora de comandas. No se implementa todavía.
