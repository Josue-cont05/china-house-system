@echo off
setlocal

set "DIR=%~dp0"
set "SCRIPTS=%DIR%scripts_locales"
set "PYW="

if exist "%DIR%.venv\Scripts\pythonw.exe" set "PYW=%DIR%.venv\Scripts\pythonw.exe"
if not defined PYW if exist "%DIR%.venv\Scripts\python.exe" set "PYW=%DIR%.venv\Scripts\python.exe"

if not defined PYW (
    where pythonw >nul 2>nul
    if not errorlevel 1 for /f "delims=" %%P in ('where pythonw') do if not defined PYW set "PYW=%%P"
)

if not defined PYW (
    where py >nul 2>nul
    if not errorlevel 1 set "PYW=py"
)

if not defined PYW (
    where python >nul 2>nul
    if not errorlevel 1 set "PYW=python"
)

if not defined PYW (
    echo No se encontro Python instalado en esta computadora.
    echo Instala Python 3 desde https://www.python.org/downloads/ y vuelve a intentar.
    echo O ejecuta primero INSTALAR_NEKO_LOCAL.bat
    pause
    exit /b 1
)

start "" "%PYW%" "%SCRIPTS%\neko_local.py"
endlocal
