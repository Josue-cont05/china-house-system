@echo off
setlocal enabledelayedexpansion

set "DIR=%~dp0"
cd /d "%DIR%"

echo ==================================================
echo  Instalando Neko Local en esta computadora
echo ==================================================
echo Esto NO modifica NekoPOS ni sus datos, solo prepara
echo el worker de impresion local (cocina) en esta PC.
echo.

rem --- 1. localizar Python ---
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)

if not defined PY (
    echo No se encontro Python 3 instalado.
    echo Instala Python desde https://www.python.org/downloads/
    echo ^(marca "Add python.exe to PATH" durante la instalacion^) y vuelve a ejecutar este archivo.
    pause
    exit /b 1
)

echo Python encontrado:
%PY% --version
echo.

rem --- 2. crear/actualizar entorno virtual local (no toca Python del sistema) ---
if not exist "%DIR%.venv\Scripts\python.exe" (
    echo Creando entorno virtual local en .venv ...
    %PY% -m venv "%DIR%.venv"
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual. Revisa el mensaje anterior.
        pause
        exit /b 1
    )
) else (
    echo Entorno virtual .venv ya existe, se reutiliza.
)

set "VENV_PY=%DIR%.venv\Scripts\python.exe"

echo.
echo Instalando dependencias del worker local (pyserial, Pillow, requests, pywin32)...
"%VENV_PY%" -m pip install --upgrade pip >nul
"%VENV_PY%" -m pip install -r "%DIR%scripts_locales\requirements.txt"
if errorlevel 1 (
    echo.
    echo No se pudieron instalar las dependencias automaticamente.
    echo Puedes intentarlo manualmente con:
    echo   "%VENV_PY%" -m pip install -r "%DIR%scripts_locales\requirements.txt"
    pause
    exit /b 1
)

echo.
echo Dependencias instaladas correctamente.
echo.

rem --- 3. crear acceso directo en el Escritorio (idempotente: sobreescribe el mismo .lnk) ---
echo Creando acceso directo "INICIAR NEKO" en el Escritorio...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\"$([Environment]::GetFolderPath('Desktop'))\INICIAR NEKO.lnk\"); " ^
    "$s.TargetPath = '%DIR%INICIAR_NEKO.bat'; " ^
    "$s.WorkingDirectory = '%DIR%'; " ^
    "$s.WindowStyle = 7; " ^
    "$s.Description = 'Iniciar NekoPOS local (worker de cocina)'; " ^
    "$s.Save()"

if errorlevel 1 (
    echo No se pudo crear el acceso directo automaticamente.
    echo Puedes usar INICIAR_NEKO.bat directamente con doble clic.
) else (
    echo Acceso directo creado.
)

echo.
echo ==================================================
echo  Instalacion terminada.
echo ==================================================
echo No se empareja Bluetooth automaticamente: hazlo desde
echo Windows (Configuracion - Bluetooth y dispositivos) y
echo luego usa "CONFIGURAR IMPRESORA" dentro de Neko Local.
echo.

set /p ABRIR="Abrir Neko Local ahora? (S/N): "
if /i "!ABRIR!"=="S" start "" "%DIR%INICIAR_NEKO.bat"

endlocal
