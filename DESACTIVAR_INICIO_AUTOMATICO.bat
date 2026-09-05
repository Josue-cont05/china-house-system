@echo off
setlocal

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "ACCESO=%STARTUP%\Neko Local.lnk"

if exist "%ACCESO%" (
    del "%ACCESO%"
    echo Inicio automatico desactivado.
) else (
    echo El inicio automatico ya estaba desactivado (no habia acceso directo).
)

pause
endlocal
