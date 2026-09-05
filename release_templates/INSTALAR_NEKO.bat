@echo off
setlocal

set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\NekoWok\App"

echo ==================================================
echo  Instalando Neko Local
echo ==================================================
echo.
echo No requiere Python, Git ni ningun otro programa.
echo No modifica NekoPOS ni ningun dato de tus ventas.
echo.

if not exist "%LOCALAPPDATA%\NekoWok" mkdir "%LOCALAPPDATA%\NekoWok"

echo Copiando archivos de la aplicacion a:
echo   %DEST%
robocopy "%SRC%." "%DEST%" /E /XF INSTALAR_NEKO.bat DESINSTALAR_NEKO.bat LEEME_PRIMERO.txt /NFL /NDL /NJH /NJS >nul
if %errorlevel% GEQ 8 (
    echo Hubo un problema copiando los archivos ^(codigo %errorlevel%^).
    pause
    exit /b 1
)

echo Creando acceso directo "INICIAR NEKO" en el Escritorio...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\"$([Environment]::GetFolderPath('Desktop'))\INICIAR NEKO.lnk\"); " ^
    "$s.TargetPath = '%DEST%\NekoLocal.exe'; " ^
    "$s.WorkingDirectory = '%DEST%'; " ^
    "$s.Description = 'Iniciar Neko Local (cocina + recibos)'; " ^
    "$s.Save()"

if errorlevel 1 (
    echo No se pudo crear el acceso directo automaticamente.
    echo Puedes abrir Neko Local directamente desde:
    echo   %DEST%\NekoLocal.exe
) else (
    echo Acceso directo creado.
)

echo.
echo ==================================================
echo  Instalacion terminada.
echo ==================================================
echo Ya puedes cerrar esta ventana y usar el acceso directo
echo "INICIAR NEKO" del Escritorio.
echo.
echo Si la POS58 nunca se emparejo con esta computadora, hazlo
echo desde Windows (Configuracion - Bluetooth y dispositivos)
echo y luego usa "CONFIGURAR IMPRESORA AUTOMATICAMENTE" dentro
echo de Neko Local. Lee LEEME_PRIMERO.txt para el paso a paso.
echo.
pause
endlocal
