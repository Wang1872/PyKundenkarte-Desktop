@echo off
setlocal
pushd "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Erst start_windows.bat ausfuehren.
  pause
  popd
  exit /b 1
)
".venv\Scripts\python.exe" "app.py"
pause
popd
