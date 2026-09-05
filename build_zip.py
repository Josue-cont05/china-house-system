"""Empaqueta una carpeta de release en un ZIP.

Reintenta si algun archivo esta bloqueado momentaneamente (por ejemplo,
un antivirus escaneando el .exe recien copiado) y verifica que el ZIP
resultante contenga exactamente los mismos archivos que la carpeta de
origen antes de darlo por bueno. Se usa desde BUILD_NEKO_LOCAL.bat en
vez de PowerShell Compress-Archive porque este ultimo puede emitir un
error no terminante (archivo bloqueado) y aun asi devolver exit code 0,
produciendo un ZIP incompleto sin que el .bat lo detecte.
"""
import sys
import time
import zipfile
from pathlib import Path


def _archivos(carpeta):
    return sorted(p for p in carpeta.rglob("*") if p.is_file())


def _nombres_relativos(rutas, carpeta):
    return {str(p.relative_to(carpeta)).replace("\\", "/") for p in rutas}


def empaquetar(carpeta_release, zip_destino, intentos=5, espera_seg=2):
    carpeta_release = Path(carpeta_release)
    zip_destino = Path(zip_destino)
    esperados = _archivos(carpeta_release)
    esperados_rel = _nombres_relativos(esperados, carpeta_release)

    for intento in range(1, intentos + 1):
        if zip_destino.exists():
            zip_destino.unlink()
        try:
            with zipfile.ZipFile(zip_destino, "w", zipfile.ZIP_DEFLATED) as zf:
                for archivo in esperados:
                    zf.write(archivo, archivo.relative_to(carpeta_release))
        except OSError as exc:
            print(f"Intento {intento}/{intentos} fallo al escribir el ZIP ({exc}); reintentando...")
            time.sleep(espera_seg)
            continue

        with zipfile.ZipFile(zip_destino) as zf:
            nombres = {n.replace("\\", "/") for n in zf.namelist()}

        if nombres == esperados_rel:
            return True

        faltantes = esperados_rel - nombres
        print(
            f"Intento {intento}/{intentos}: ZIP incompleto "
            f"({len(nombres)}/{len(esperados_rel)} archivos, faltan: {sorted(faltantes)[:5]}); "
            "reintentando..."
        )
        time.sleep(espera_seg)

    return False


def main_para_test():
    if len(sys.argv) != 3:
        print("Uso: build_zip.py <carpeta_release> <zip_destino>")
        sys.exit(2)
    ok = empaquetar(sys.argv[1], sys.argv[2])
    if not ok:
        print("No se pudo generar un ZIP completo tras varios intentos.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main_para_test()
