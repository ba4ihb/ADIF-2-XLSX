@echo off
rem ---------------------------------------------------------------------------
rem Start the adif2xlsx web interface.
rem
rem The browser is the interface; this window is the little local service that
rem does the conversion.  Leave it open while you work and close it (or press
rem Ctrl+C) when you are done.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

set "PYEXE="
if exist "dist\adif2xlsx-web\adif2xlsx-web.exe" set "PYEXE=dist\adif2xlsx-web\adif2xlsx-web.exe"
if exist "dist\adif2xlsx-web.exe" set "PYEXE=dist\adif2xlsx-web.exe"

if defined PYEXE (
    echo Starting the packaged web interface...
    "%PYEXE%" %*
    goto :end
)

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo Python was not found on PATH.
    echo Either install Python 3.10+ and "pip install openpyxl",
    echo or run the packaged build:  dist\adif2xlsx-web.exe
    echo.
    pause
    goto :end
)

echo Starting the web interface from source...
python src\webapp.py %*

:end
endlocal
