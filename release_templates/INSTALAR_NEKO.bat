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

echo Creando acceso directo "NekoWok Printer" en el Escritorio...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$shell = New-Object -ComObject WScript.Shell; " ^
    "$escritorio = [Environment]::GetFolderPath('Desktop'); " ^
    "$destino = '%DEST%\NekoLocal.exe'; " ^
    "$viejo = Join-Path $escritorio 'INICIAR NEKO.lnk'; " ^
    "if (Test-Path $viejo) { try { $atajoViejo = $shell.CreateShortcut($viejo); if ($atajoViejo.TargetPath -eq $destino) { Remove-Item $viejo -Force } } catch {} }; " ^
    "$nuevo = Join-Path $escritorio 'NekoWok Printer.lnk'; " ^
    "$s = $shell.CreateShortcut($nuevo); " ^
    "$s.TargetPath = $destino; " ^
    "$s.WorkingDirectory = '%DEST%'; " ^
    "$s.IconLocation = \"$destino,0\"; " ^
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
echo "NekoWok Printer" del Escritorio.
echo.
echo Si la POS58 nunca se emparejo con esta computadora, hazlo
echo desde Windows (Configuracion - Bluetooth y dispositivos)
echo y luego usa "CONFIGURAR IMPRESORA AUTOMATICAMENTE" dentro
echo de Neko Local. Lee LEEME_PRIMERO.txt para el paso a paso.
echo.
pause
endlocal
