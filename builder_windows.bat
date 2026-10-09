@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 (
  echo Projektordner nicht erreichbar.
  pause
  exit /b 1
)

if not exist "data\DE.txt" (
  echo Es fehlt data\DE.txt. Bitte erst die oeffentliche GeoNames-Datei dort ablegen.
  goto :failure
)

if not exist ".venv\Scripts\python.exe" (
  call "%~dp0einrichten_windows.bat"
  if errorlevel 1 goto :failure
)
".venv\Scripts\python.exe" -c "import PySide6.QtWidgets" >nul 2>&1
if errorlevel 1 (
  call "%~dp0einrichten_windows.bat"
  if errorlevel 1 goto :failure
)

echo Installiere das Paketwerkzeug nur in der lokalen .venv ...
".venv\Scripts\python.exe" -m pip install --only-binary=:all: --disable-pip-version-check -r requirements_build.txt
if errorlevel 1 goto :failure

if not exist "build_windows\spec" mkdir "build_windows\spec"
if errorlevel 1 goto :failure
if not exist "build_windows\work" mkdir "build_windows\work"
if errorlevel 1 goto :failure
echo Erstelle die Windows-App ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name PyKundenkarte --distpath "release" --workpath "build_windows\work" --specpath "build_windows\spec" "app.py"
if errorlevel 1 goto :failure
if not exist "release\PyKundenkarte\PyKundenkarte.exe" goto :failure

if not exist "release\PyKundenkarte\data" mkdir "release\PyKundenkarte\data"
if errorlevel 1 goto :failure
copy /Y "data\DE.txt" "release\PyKundenkarte\data\DE.txt" >nul
if errorlevel 1 goto :failure
if exist "data\bundeslaender.geojson" (
  copy /Y "data\bundeslaender.geojson" "release\PyKundenkarte\data\bundeslaender.geojson" >nul
  if errorlevel 1 goto :failure
)
copy /Y "START_HIER_OHNE_PYTHON.txt" "release\PyKundenkarte\START_HIER.txt" >nul
if errorlevel 1 goto :failure
copy /Y "README.md" "release\PyKundenkarte\README.md" >nul
if errorlevel 1 goto :failure

echo.
echo Fertig: release\PyKundenkarte\PyKundenkarte.exe
echo Zum Weitergeben den GESAMTEN Ordner release\PyKundenkarte kopieren.
echo Vorher die EXE auf diesem Windows-Rechner testen.
pause
popd
exit /b 0

:failure
echo.
echo Paket konnte nicht erstellt werden. Ausgabe oben pruefen.
pause
popd
exit /b 1
