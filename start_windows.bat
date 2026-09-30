@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Projektordner nicht erreichbar. Bitte ZIP vollstaendig lokal entpacken.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\pythonw.exe" (
  call "%~dp0einrichten_windows.bat"
  if errorlevel 1 (
    popd
    exit /b 1
  )
)
".venv\Scripts\python.exe" -c "from PySide6.QtWidgets import QApplication, QGraphicsView" >nul 2>&1
if errorlevel 1 (
  call "%~dp0einrichten_windows.bat"
  if errorlevel 1 (
    popd
    exit /b 1
  )
)
start "" ".venv\Scripts\pythonw.exe" "app.py"
if errorlevel 1 (
  echo Start fehlgeschlagen. Zum Test start_debug_windows.bat ausfuehren.
  pause
)
popd
