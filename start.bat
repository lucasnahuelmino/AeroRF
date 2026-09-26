@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
SET MODE=%1
IF "%MODE%"=="" SET MODE=dev

echo.
echo  [AeroRF] Modo: %MODE%
echo.

:: ── Load .env (simple KEY=VALUE reader) ────────────────────────────────────
IF EXIST "%~dp0.env" (
  FOR /F "usebackq eol=# tokens=1,2 delims==" %%A in ("%~dp0.env") DO (
    IF NOT "%%B"=="" SET "%%A=%%B"
  )
  echo  Configuracion cargada desde .env
) ELSE (
  echo  No se encontro .env. Copie .env.example a .env (opcional para el mapa).
)

:: ── Port ───────────────────────────────────────────────────────────────────
IF "%PORT%"=="" SET PORT=8000
IF "%VITE_PORT%"=="" SET VITE_PORT=5173
IF "%VITE_API_TARGET%"=="" SET VITE_API_TARGET=http://127.0.0.1:%PORT%

echo  Backend:  %VITE_API_TARGET%
echo  Frontend: http://localhost:%VITE_PORT%
echo.

:: ── Virtualenv ─────────────────────────────────────────────────────────────
IF EXIST "%~dp0.venv\Scripts\activate" (
  call "%~dp0.venv\Scripts\activate"
) ELSE (
  echo  AVISO: no se encontro .venv
  echo  Cree uno con:  python -m venv .venv
  echo  Y luego:       .venv\Scripts\pip install -r requirements.txt
  echo.
)

IF /I "%MODE%"=="stop" (
  echo  Deteniendo AeroRF...
  FOR /F "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr LISTENING') DO (
    echo    matando PID %%a
    taskkill /PID %%a /F >nul 2>&1
  )
  goto :eof
)

IF /I "%MODE%"=="test" (
  echo  Ejecutando pruebas...
  python -m pytest tests app\rf_engine -q
  node tests\geo_parity.mjs
  goto :eof
)

IF /I "%MODE%"=="dev" (
  echo  Iniciando backend (uvicorn)...
  start "aerorf-backend" cmd /c "python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload > %~dp0backend.log 2>&1"
  timeout /t 3 /nobreak >nul
  echo  Iniciando frontend (Vite)...
  pushd "%~dp0frontend"
  if not exist node_modules call npm install
  set VITE_API_TARGET=%VITE_API_TARGET%
  set VITE_PORT=%VITE_PORT%
  call npm run dev
  popd
  goto :eof
)

IF /I "%MODE%"=="prod" (
  echo  Iniciando backend (uvicorn, sin recarga)...
  start "aerorf-backend" cmd /c "python -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% > %~dp0backend.log 2>&1"
  pushd "%~dp0frontend"
  echo  Construyendo frontend...
  call npm run build
  popd
  echo.
  echo  Para servir dist\ use un servidor con fallback SPA, por ejemplo:
  echo    npx serve -s dist -l %VITE_PORT%
  goto :eof
)

echo  Uso: start.bat [dev^|prod^|stop^|test]
ENDLOCAL
