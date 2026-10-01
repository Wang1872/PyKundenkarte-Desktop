@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Projektordner nicht erreichbar. Bitte ZIP vollstaendig lokal entpacken.
  pause
  exit /b 1
)

set "PYTHON_COMMAND="
py -3.14 -c "import sys; sys.exit(sys.version_info < (3, 10) or sys.maxsize <= 2**32)" >nul 2>&1
if not errorlevel 1 set "PYTHON_COMMAND=py -3.14"
if not defined PYTHON_COMMAND (
  py -3 -c "import sys; sys.exit(sys.version_info < (3, 10) or sys.maxsize <= 2**32)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_COMMAND=py -3"
)
if not defined PYTHON_COMMAND (
  python -c "import sys; sys.exit(sys.version_info < (3, 10) or sys.maxsize <= 2**32)" >nul 2>&1
  if not errorlevel 1 set "PYTHON_COMMAND=python"
)
if not defined PYTHON_COMMAND (
  where scoop >nul 2>&1
  if not errorlevel 1 (
    echo Python fehlt. Installiere Python fuer diesen Benutzer mit Scoop ...
    call scoop install python
    if not errorlevel 1 (
      python -c "import sys; sys.exit(sys.version_info < (3, 10) or sys.maxsize <= 2**32)" >nul 2>&1
      if not errorlevel 1 set "PYTHON_COMMAND=python"
    )
  )
)
if not defined PYTHON_COMMAND (
  echo Python 3.10 oder neuer in 64 Bit wurde nicht gefunden.
  echo Falls Scoop installiert ist: PowerShell oeffnen, scoop install python ausfuehren,
  echo danach start_windows.bat erneut doppelklicken.
  echo Ohne Scoop bitte Python fuer den aktuellen Benutzer installieren oder die IT fragen.
  pause
  popd
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Erstelle nur fuer dieses Projekt eine Python-Umgebung ...
  %PYTHON_COMMAND% -m venv .venv
  if errorlevel 1 (
    echo Einrichtung fehlgeschlagen. Bitte Schreibrechte pruefen.
    pause
    popd
    exit /b 1
  )
)
echo Installiere PySide6 lokal in .venv. Nur dieser erste Schritt braucht Paket-Zugang.
".venv\Scripts\python.exe" -m pip install --only-binary=:all: --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Paket nicht verfuegbar. Bitte Firmen-Paketquelle oder IT kontaktieren.
  pause
  popd
  exit /b 1
)
echo Einrichtung abgeschlossen.
popd
exit /b 0
