@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Virtual environment not found. Run install.bat first.
  pause
  exit /b 1
)

where ollama >nul 2>nul
if errorlevel 1 (
  echo ERROR: Ollama is not installed or is not on PATH.
  echo Install Ollama from https://ollama.com/download
  pause
  exit /b 1
)

set APP_HOST=127.0.0.1
set APP_PORT=8000
set OLLAMA_HOST=http://127.0.0.1:11434
set OLLAMA_LLM_MODEL=llama3.2:3b
set OLLAMA_EMBED_MODEL=nomic-embed-text
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "APP_HOST=" ".env"`) do set APP_HOST=%%B
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "APP_PORT=" ".env"`) do set APP_PORT=%%B
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "OLLAMA_HOST=" ".env"`) do set OLLAMA_HOST=%%B
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "OLLAMA_LLM_MODEL=" ".env"`) do set OLLAMA_LLM_MODEL=%%B
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "OLLAMA_EMBED_MODEL=" ".env"`) do set OLLAMA_EMBED_MODEL=%%B
)

curl -s --max-time 2 %OLLAMA_HOST%/api/tags >nul 2>nul
if errorlevel 1 (
  echo Starting Ollama service...
  start "" ollama serve
  timeout /t 3 /nobreak >nul
)

echo Checking required Ollama models...
ollama list
echo.
echo If %OLLAMA_LLM_MODEL% or %OLLAMA_EMBED_MODEL% is missing, stop and run:
echo   ollama pull %OLLAMA_LLM_MODEL%
echo   ollama pull %OLLAMA_EMBED_MODEL%

netstat -ano | findstr /r /c:"LISTENING.*:%APP_PORT% " >nul
if not errorlevel 1 (
  echo WARNING: Port %APP_PORT% is already in use.
  echo The application may already be running at http://%APP_HOST%:%APP_PORT%/
  pause
  exit /b 1
)

echo Starting FastAPI on http://%APP_HOST%:%APP_PORT%/
echo Press Ctrl+C to stop the application.
".venv\Scripts\python.exe" -m app
if errorlevel 1 (
  echo.
  echo ERROR: Application stopped unexpectedly. Review the message above.
  pause
)
