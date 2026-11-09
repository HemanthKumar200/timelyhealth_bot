@echo off
setlocal
cd /d "%~dp0"

echo Timely Health chatbot installer
echo ===============================

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found on PATH.
  echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo ERROR: Python 3.10 or newer is required.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Virtual environment creation failed.
    pause
    exit /b 1
  )
)

echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: Dependency installation failed.
  pause
  exit /b 1
)

echo Installing Playwright Chromium for website sync...
set "PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\timelyhealth-playwright"
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
  echo WARNING: Playwright Chromium install failed. Website sync may not update JS pages.
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example.
)

where ollama >nul 2>nul
if errorlevel 1 (
  echo WARNING: Ollama was not found on PATH.
  echo Install Ollama from https://ollama.com/download, then run start.bat.
) else (
  echo Checking Ollama models...
  ollama list
  echo Required defaults: llama3.2:3b and nomic-embed-text
  echo If a model is missing, install it intentionally with:
  echo   ollama pull llama3.2:3b
  echo   ollama pull nomic-embed-text
  echo Models are not downloaded automatically by this installer.
)

if not exist "data\chroma_db\chroma.sqlite3" (
  echo WARNING: Existing ChromaDB index was not found.
  echo Run the site's synchronization command before using the chatbot, or restore data\chroma_db.
) else (
  echo Existing ChromaDB data will be preserved at data\chroma_db.
)

echo.
echo Installation complete.
echo Run start.bat to launch the application.
pause
