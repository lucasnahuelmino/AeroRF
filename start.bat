@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
SET MODE=%1
IF "%MODE%"=="" SET MODE=dev

echo [SIARI] Modo: %MODE%

:: Activar venv si existe
IF EXIST "%~dp0.venv\Scripts\activate" (
  call "%~dp0.venv\Scripts\activate"
) ELSE (
  echo No se encontró .venv; asegúrate de activar tu entorno Python manualmente.
)

IF /I "%MODE%"=="dev" (
  echo Iniciando backend (uvicorn) en segundo plano...
  start "siari-backend" cmd /c "uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > %~dp0backend.log 2>&1"
  echo Backend iniciado.
  echo Abriendo frontend (Vite)...
  pushd "%~dp0frontend"
  call npm run dev
  popd
  goto :eof
)

IF /I "%MODE%"=="prod" (
  echo Iniciando backend (uvicorn)...
  start "siari-backend" cmd /c "uvicorn app.main:app --host 0.0.0.0 --port 8000 > %~dp0backend.log 2>&1"
  echo Construyendo/serviendo frontend...
  pushd "%~dp0frontend"
  if not exist dist (
    echo Building frontend...
    call npm run build
  )
  popd
  if exist "%~dp0\node_modules\.bin\serve.cmd" (
    start "siari-frontend" cmd /c "npx serve -s dist -l 5173"
  ) ELSE (
    echo npx/serve no encontrado. Abriendo Python HTTP server (no es SPA-friendly)...
    pushd "%~dp0frontend\dist"
    start "siari-frontend" cmd /c "python -m http.server 5173"
    popd
  )
  goto :eof
)

IF /I "%MODE%"=="stop" (
  echo Deteniendo backend (buscando procesos uvicorn)...
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    echo Matando PID %%a
    taskkill /PID %%a /F
  )
  goto :eof
)

echo Uso: start.bat [dev|prod|stop]
ENDLOCAL
