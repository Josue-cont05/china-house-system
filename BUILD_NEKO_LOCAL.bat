@echo off
setlocal enabledelayedexpansion

set "DIR=%~dp0"
cd /d "%DIR%"

echo ==================================================
echo  Build de Neko Local (NekoLocal.exe)
echo ==================================================
echo Esto NO toca NekoPOS/Render ni backend/datos del proyecto.
echo Solo empaqueta scripts_locales/ en release\NekoLocal-vX.X.X\
echo.

rem --- 1. localizar Python del entorno de desarrollo ---
set "PY="
if exist "%DIR%.venv\Scripts\python.exe" set "PY=%DIR%.venv\Scripts\python.exe"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo No se encontro Python. Ejecuta primero INSTALAR_NEKO_LOCAL.bat
    pause
    exit /b 1
)

echo Python de build:
"%PY%" --version
echo.

rem --- 2. version desde neko_version.py (una sola fuente de verdad) ---
rem     Se escribe a un archivo temporal en vez de usar `comando` dentro
rem     de for /f: las comillas anidadas de esa forma se rompen cuando la
rem     ruta de Python (o del proyecto) contiene espacios, como suele
rem     pasar con el nombre de usuario de Windows.
set "VERSION_TMP=%TEMP%\neko_local_version.txt"
"%PY%" -c "import sys; sys.path.insert(0, r'%DIR%scripts_locales'); import neko_version; print(neko_version.APP_VERSION)" > "%VERSION_TMP%"
set "VERSION="
set /p VERSION=<"%VERSION_TMP%"
del "%VERSION_TMP%" >nul 2>nul
if not defined VERSION (
    echo No se pudo leer la version desde scripts_locales\neko_version.py
    pause
    exit /b 1
)
echo Version detectada: %VERSION%
echo.

rem --- 3. instalar/verificar PyInstaller (solo entorno de build, no runtime) ---
"%PY%" -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Instalando PyInstaller en el entorno de build...
    "%PY%" -m pip install pyinstaller
    if errorlevel 1 (
        echo No se pudo instalar PyInstaller.
        pause
        exit /b 1
    )
)

rem --- 4. limpiar SOLO artefactos de build propios (nunca codigo/datos) ---
echo Limpiando build\ y dist\ de ejecuciones anteriores...
if exist "%DIR%build" rmdir /s /q "%DIR%build"
if exist "%DIR%dist" rmdir /s /q "%DIR%dist"

rem --- 5. generar distribucion (onedir) ---
echo.
echo Compilando NekoLocal.exe (onedir, puede tardar 1-2 minutos)...
"%PY%" -m PyInstaller --clean --noconfirm NekoLocal.spec
if errorlevel 1 (
    echo El build de PyInstaller fallo. Revisa el mensaje anterior.
    pause
    exit /b 1
)

rem --- 6. comprobar archivos esperados ---
set "DIST=%DIR%dist\NekoLocal"
if not exist "%DIST%\NekoLocal.exe" (
    echo No se genero NekoLocal.exe. Build fallido.
    pause
    exit /b 1
)
echo.
echo NekoLocal.exe generado: %DIST%\NekoLocal.exe

rem --- 7. smoke tests reales (sin hardware, sin red, sin GUI) ---
echo.
echo Ejecutando smoke tests del ejecutable...
"%DIST%\NekoLocal.exe" --version
if errorlevel 1 (
    echo FALLO: NekoLocal.exe --version no respondio correctamente.
    pause
    exit /b 1
)
"%DIST%\NekoLocal.exe" --help >nul
if errorlevel 1 (
    echo FALLO: NekoLocal.exe --help no respondio correctamente.
    pause
    exit /b 1
)
"%DIST%\NekoLocal.exe" --diagnostics
if errorlevel 1 (
    echo FALLO: NekoLocal.exe --diagnostics no respondio correctamente.
    pause
    exit /b 1
)
echo Smoke tests OK: --version / --help / --diagnostics respondieron sin abrir hardware ni GUI.

rem --- 8. validar que el release no contenga archivos prohibidos ---
echo.
echo Validando contenido del build contra la lista de archivos prohibidos...
"%PY%" -c "import sys; sys.path.insert(0,'scripts_locales'); import release_check; problemas = release_check.validar_carpeta(r'%DIST%'); sys.exit(1 if problemas else (print('Validacion OK: sin archivos prohibidos') or 0))"
if errorlevel 1 (
    echo FALLO: el build contiene archivos que no deberian ir en el release.
    pause
    exit /b 1
)

rem --- 9. armar la carpeta de release ---
set "RELEASE_DIR=%DIR%release\NekoLocal-v%VERSION%"
echo.
echo Preparando carpeta de release: %RELEASE_DIR%
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

xcopy "%DIST%\*" "%RELEASE_DIR%\" /e /i /y >nul
copy "%DIR%release_templates\INSTALAR_NEKO.bat" "%RELEASE_DIR%\INSTALAR_NEKO.bat" >nul
copy "%DIR%release_templates\DESINSTALAR_NEKO.bat" "%RELEASE_DIR%\DESINSTALAR_NEKO.bat" >nul
copy "%DIR%release_templates\LEEME_PRIMERO.txt" "%RELEASE_DIR%\LEEME_PRIMERO.txt" >nul

echo.
echo Validando la carpeta de release final...
"%PY%" -c "import sys; sys.path.insert(0,'scripts_locales'); import release_check; problemas = release_check.validar_carpeta(r'%RELEASE_DIR%'); sys.exit(1 if problemas else (print('Release final OK') or 0))"
if errorlevel 1 (
    echo FALLO: la carpeta de release final contiene archivos prohibidos.
    pause
    exit /b 1
)

rem --- 10. ZIP final (con reintentos y verificacion de integridad) ---
rem     No se usa PowerShell Compress-Archive: si un archivo esta bloqueado
rem     un instante (ej. antivirus escaneando el .exe recien copiado),
rem     Compress-Archive puede emitir solo una advertencia y de todas
rem     formas devolver exit code 0, dejando un ZIP incompleto sin que
rem     este script lo note. build_zip.py reintenta y verifica que el
rem     ZIP tenga exactamente los mismos archivos que la carpeta release.
echo.
echo Generando ZIP...
set "ZIP_PATH=%DIR%release\NekoLocal-v%VERSION%.zip"
"%PY%" "%DIR%build_zip.py" "%RELEASE_DIR%" "%ZIP_PATH%"
if errorlevel 1 (
    echo FALLO: no se pudo generar un ZIP completo del release tras varios intentos.
    echo Puede que un antivirus este bloqueando temporalmente algun archivo.
    echo La carpeta de release sigue disponible sin comprimir en:
    echo   %RELEASE_DIR%
    pause
    exit /b 1
)
echo ZIP generado: %ZIP_PATH%

echo.
echo ==================================================
echo  Build completado.
echo ==================================================
echo Carpeta:  %RELEASE_DIR%
echo ZIP:      %ZIP_PATH%
echo.
pause
endlocal
