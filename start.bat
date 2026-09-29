@echo off
REM ===========================================================================
REM  AeroRF - backend + frontend con un solo comando
REM
REM    start.bat            backend + frontend   (doble clic o comando)
REM    start.bat test       suite de pruebas
REM    start.bat build      construye frontend\dist
REM    start.bat stop       detiene lo que dejo este script
REM
REM  Los modos _backend y _frontend son internos: los abre `start` para correr
REM  cada servidor en su propia ventana. No se usan a mano.
REM ===========================================================================

setlocal EnableDelayedExpansion
chcp 65001 >nul
title AeroRF

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=dev"

REM ── Modos internos: arrancan un servidor y se quedan en primer plano ───────
if /I "%MODE%"=="_backend"  goto :run_backend
if /I "%MODE%"=="_frontend" goto :run_frontend

echo.
echo   AeroRF - modo: %MODE%
echo   ------------------------------------------------------------
echo.

REM ===========================================================================
REM  1. Configuracion
REM ===========================================================================
REM  Se lee solo lo que el lanzador necesita, y no el .env entero.
REM
REM  Una version anterior volcaba todas las claves al entorno. Con solo eso,
REM  un trazado de depuracion (@echo on) imprimia el OPENSKY_CLIENT_SECRET de
REM  cleartext, y cualquier proceso hijo lo heredaba. Una lista blanca no
REM  puede filtrar lo que no nombra: aqui estan PORT, VITE_PORT y HOST, y
REM  nada mas. uvicorn lee el .env el mismo, asi que no le faltan datos.
if exist "%ROOT%.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ROOT%.env") do (
    if /I "%%A"=="PORT"       set "PORT=%%B"
    if /I "%%A"=="VITE_PORT"  set "VITE_PORT=%%B"
    if /I "%%A"=="HOST"       set "HOST=%%B"
  )
  echo   [1/5] Configuracion leida desde .env
) else (
  echo   [1/5] No hay .env. Se usan los valores por defecto.
)

REM  El backend NO debe caer en 8000: ese puerto lo tiene el proyecto hermano
REM  rni-app-4.0 en esta maquina, y el frontend terminaria speaking con el.
if "%PORT%"=="" set "PORT=8010"
if "%VITE_PORT%"=="" set "VITE_PORT=5199"
set "VITE_API_TARGET=http://127.0.0.1:%PORT%"

REM  La flecha va escapada. Sin el ^, cmd lee ">" como una redireccion e
REM  intenta crear un archivo llamado "http://127.0.0.1:8010", que no es un
REM  nombre valido: el error sale en pantalla y la linea no se imprime.
echo         Backend  ^>  %VITE_API_TARGET%
echo         Frontend ^>  http://localhost:%VITE_PORT%
echo.

REM ===========================================================================
REM  2. Logs en logs/ para no ensuciar la raiz
REM ===========================================================================
if not exist "%ROOT%logs" mkdir "%ROOT%logs" >nul 2>&1

REM ===========================================================================
REM  3. Python
REM ===========================================================================
set "PY=%ROOT%.venv\Scripts\python.exe"
if exist "%PY%" (
  echo   [2/5] Entorno virtual: .venv
) else (
  echo   [2/5] No hay .venv. Creandolo...
  where python >nul 2>&1
  if errorlevel 1 goto :nopython
  python -m venv "%ROOT%.venv"
  if not exist "%PY%" goto :nopython
  echo         Instalando dependencias, puede tardar...
  "%PY%" -m pip install --quiet --upgrade pip
  "%PY%" -m pip install --quiet -r "%ROOT%requirements.txt"
  if errorlevel 1 goto :nodeps
  echo         Listo.
)

if not exist "%ROOT%frontend\node_modules" (
  echo         Instalando paquetes de npm, puede tardar...
  pushd "%ROOT%frontend"
  call npm install --silent
  popd
)
echo.

REM ===========================================================================
REM  Despacho de modos
REM ===========================================================================
if /I "%MODE%"=="stop"  goto :stop
if /I "%MODE%"=="test"  goto :test
if /I "%MODE%"=="build" goto :build
if /I "%MODE%"=="dev"   goto :dev
goto :usage

REM ===========================================================================
REM  dev  (por defecto)
REM ===========================================================================
:dev
echo   [3/5] Comprobando puertos...

REM  Si el puerto ya esta ocupado no se sigue adelante. Antes se hacia solo un
REM  aviso y se continuaba, y la comprobacion de /health podia responder el
REM  proceso que ya estaba escuchando: el script anunciaba "listo" mientras la
REM  ventana nueva habia fallado al tomar el puerto. Un fallo silencioso asi
REM  es peor que negarse a arrancar.
call :isbusy %PORT%
if "%ISBUSY%"=="1" goto :busy_backend

call :isbusy %VITE_PORT%
if "%ISBUSY%"=="1" goto :busy_frontend

echo         libres.
echo.

echo   [4/5] Iniciando backend...
start "AeroRF backend" /min "%~f0" _backend
echo         Esperando a que /health responda...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$u='http://127.0.0.1:%PORT%/health';for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 2;if($r.StatusCode -eq 200){exit 0}}catch{};Start-Sleep -Milliseconds 500};exit 1" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   El backend NO respondio en el puerto %PORT%.
  echo   Ultimas lineas de logs\backend.log:
  echo   ------------------------------------------------------------
  if exist "%ROOT%logs\backend.log" powershell -NoProfile -Command "Get-Content -Tail 25 '%ROOT%logs\backend.log'"
  echo   ------------------------------------------------------------
  goto :fail
)
echo         Backend listo.

echo   [5/5] Iniciando frontend...
start "AeroRF frontend" "%~f0" _frontend
echo         Esperando a Vite...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:%VITE_PORT%/' -TimeoutSec 2;exit 0}catch{};Start-Sleep -Milliseconds 500};exit 1" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Vite no respondio en http://localhost:%VITE_PORT%
  echo   Revise logs\frontend.log
  echo.
  goto :fail
)

echo.
echo   ------------------------------------------------------------
echo   AeroRF en marcha
echo.
echo     Frontend:  http://localhost:%VITE_PORT%
echo     API:       %VITE_API_TARGET%   ^(puerto %PORT%^)
echo     Salud:     %VITE_API_TARGET%/health
echo     Logs:      logs\backend.log    logs\frontend.log
echo.
echo   Para detener:  start.bat stop
echo   ------------------------------------------------------------
echo.
start "" "http://localhost:%VITE_PORT%"
goto :eof

REM ===========================================================================
REM  Servidores en primer plano (modos internos)
REM ===========================================================================
:run_backend
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload > "%ROOT%logs\backend.log" 2>&1
goto :eof

:run_frontend
pushd "%ROOT%frontend"
set "VITE_API_TARGET=%VITE_API_TARGET%"
set "VITE_PORT=%VITE_PORT%"
call npm run dev > "%ROOT%logs\frontend.log" 2>&1
popd
goto :eof

REM ===========================================================================
REM  test
REM ===========================================================================
:test
echo   Ejecutando pruebas...
echo.
pushd "%ROOT%"
"%PY%" -m pytest -m "not integration" -q
if errorlevel 1 set "RC=1"
popd
echo.
if exist "%ROOT%frontend\node_modules" (
  pushd "%ROOT%frontend"
  call npm test --silent
  if errorlevel 1 set "RC=1"
  popd
)
REM  El archivo vive en tests/ del proyecto, no en frontend/tests/. Con la
REM  ruta equivocada el if no se cumplia y la paridad geodesica no se
REM  ejecutaba nunca, en silencio.
if exist "%ROOT%tests\geo_parity.mjs" (
  pushd "%ROOT%frontend"
  node ..\tests\geo_parity.mjs
  if errorlevel 1 set "RC=1"
  popd
)
echo.
if not defined RC (echo   Todo verde.) else (echo   Hubo fallos.)
if defined RC goto :fail
goto :eof

REM ===========================================================================
REM  build
REM ===========================================================================
:build
echo   Construyendo frontend...
pushd "%ROOT%frontend"
call npm run build
if errorlevel 1 (
  set "RC=1"
  popd
  echo.
  echo   La construccion fallo.
  goto :fail
)
popd
echo.
echo   Frontend construido en frontend\dist
echo   Para servirlo con fallback SPA:  npx serve -s dist -l %VITE_PORT%
echo.
goto :eof

REM ===========================================================================
REM  stop
REM ===========================================================================
:stop
echo   Deteniendo AeroRF...
REM  Se mata por linea de comandos, no solo por puerto.
REM
REM  Uvicorn con --reload lanza un supervisor y un hijo, y el hijo hereda el
REM  socket de escucha. Matar el PID que netstat muestra deja a los dos
REM  python.exe vivos y el puerto sigue ocupado: el proceso que netstat
REM  reporta es el que creo el socket, no necesariamente quien lo escucha.
call :kill_port %PORT%
call :kill_port %VITE_PORT%
call :kill_cmd uvicorn
echo   Listo.
goto :eof

REM ===========================================================================
REM  Subrutinas
REM ===========================================================================

REM  isbusy <port>  ->  deja ISBUSY=1 si el puerto esta ocupado, 0 si esta libre
REM
REM  findstr devuelve 0 cuando ENCUENTRA la linea y 1 cuando no. Ese 0 es
REM  justamente el que significa "el puerto esta ocupado". Una version
REM  anterior de esta routine leia los dos codigos al reves, y por eso daba
REM  los puertos libres por ocupados y los ocupados por libres.
:isbusy
netstat -ano | findstr "LISTENING" | findstr ":%~1 " >nul 2>&1
if errorlevel 1 (set "ISBUSY=0") else (set "ISBUSY=1")
exit /b 0

REM  kill_port <port>  -  mata lo que escucha en ese puerto
:kill_port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%~1 " 2^>nul') do (
  echo     matando PID %%a en el puerto %~1
  taskkill /PID %%a /T /F >nul 2>&1
)
exit /b 0

REM  kill_cmd <texto>  -  mata procesos cuya linea de comandos contenga <texto>
REM  Solo se invoca con "uvicorn": los procesos de este proyecto se distinguen
REM  por el puerto que ocupan. Buscar "vite" mataria el Vite de cualquier otro
REM  proyecto que este corriendo en la misma maquina.
:kill_cmd
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*%~1*' } | ForEach-Object { Write-Host ('     matando PID ' + $_.ProcessId + '  uvicorn'); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" 2>nul
exit /b 0

:usage
echo   Uso:  start.bat [dev^|test^|build^|stop]
echo.
echo     dev    (por defecto)  backend + frontend
echo     test                 suite de pruebas
echo     build                construye frontend\dist
echo     stop                 detiene lo que dejo este script
echo.
goto :eof

:busy_backend
echo.
echo   El puerto %PORT% ya esta ocupado, asi que AeroRF no arranca.
echo.
echo   Puede ser una copia anterior de AeroRF todavia en marcha.
echo   Pruebe:  start.bat stop
echo.
echo   Si lo que lo ocupa es otro proyecto, elija otro puerto:
echo     set PORT=8011 ^& start.bat
echo.
goto :eof

:busy_frontend
echo.
echo   El puerto %VITE_PORT% ya esta ocupado, asi que AeroRF no arranca.
echo.
echo   Pruebe:  start.bat stop
echo.
echo   Si lo que lo ocupa es otro proyecto, elija otro puerto:
echo     set VITE_PORT=5200 ^& start.bat
echo.
goto :eof

:nopython
echo   ERROR: no se encontro Python en el PATH.
echo   Instale Python 3.11 o superior y vuelva a ejecutar este archivo.
echo.
goto :fail

:nodeps
echo   ERROR: fallo la instalacion de dependencias de Python.
echo   Revise la conexion a internet y que requirements.txt sea valido.
echo.
goto :fail

:fail
echo.
pause
exit /b 1
