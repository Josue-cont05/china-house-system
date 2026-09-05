@echo off
setlocal

set "DIR=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo Creando acceso directo en la carpeta de inicio de Windows...
echo (%STARTUP%)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\"%STARTUP%\Neko Local.lnk\"); " ^
    "$s.TargetPath = '%DIR%INICIAR_NEKO.bat'; " ^
    "$s.WorkingDirectory = '%DIR%'; " ^
    "$s.WindowStyle = 7; " ^
    "$s.Description = 'Inicio automatico de Neko Local'; " ^
    "$s.Save()"

if errorlevel 1 (
    echo No se pudo crear el acceso directo de inicio automatico.
) else (
    echo Listo: Neko Local se abrira automaticamente al iniciar sesion en Windows.
    echo Para desactivarlo, ejecuta DESACTIVAR_INICIO_AUTOMATICO.bat
)

pause
endlocal
