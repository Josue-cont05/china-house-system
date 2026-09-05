@echo off
setlocal

set "APP_DIR=%LOCALAPPDATA%\NekoWok\App"
set "ACCESO=%USERPROFILE%\Desktop\INICIAR NEKO.lnk"

echo ==================================================
echo  Desinstalar Neko Local
echo ==================================================
echo.
echo Esto elimina el programa y el acceso directo del Escritorio.
echo.
echo Tu configuracion de impresora, el historial de comandas y
echo recibos ya impresos, y los logs de diagnostico NO se borran:
echo quedan en %LOCALAPPDATA%\NekoWok\
echo.
set /p CONFIRMAR="Escribe SI para continuar: "
if /i not "%CONFIRMAR%"=="SI" (
    echo Cancelado. No se elimino nada.
    pause
    exit /b 0
)

if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"
if exist "%ACCESO%" del "%ACCESO%"

echo.
echo Neko Local desinstalado.
echo Tu configuracion e historial de impresion siguen disponibles en:
echo   %LOCALAPPDATA%\NekoWok\
echo.
echo Si en algun momento quieres borrar TAMBIEN la configuracion y el
echo historial (por ejemplo, para dejar la PC completamente limpia),
echo elimina manualmente esa carpeta completa desde el Explorador de
echo archivos. Esto es opcional y no se hace automaticamente.
echo.
pause
endlocal
