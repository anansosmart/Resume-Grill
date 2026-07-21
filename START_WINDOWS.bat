@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

title AI Resume Grill V2
set "LOG=%CD%\启动日志.txt"
set "PYTHON_EXE="
set "VENV_PY=%CD%\.venv\Scripts\python.exe"

echo ==================================================
echo   AI Resume Grill V2 - Windows Launcher
echo ==================================================
echo Project: %CD%
echo Log: %LOG%
echo.

> "%LOG%" echo [START] %date% %time%
>> "%LOG%" echo [ROOT] %CD%

rem Do not run directly inside a ZIP preview.
if not exist "%CD%\app.py" (
  echo [ERROR] app.py was not found.
  echo Please fully extract the ZIP before running this file.
  >> "%LOG%" echo [ERROR] app.py missing. ZIP may not be extracted.
  goto :fail
)

rem Locate a real Python executable. Prefer the Windows py launcher.
for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"
if not defined PYTHON_EXE (
  for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%I"
)

if not defined PYTHON_EXE (
  echo [ERROR] Python 3 was not found.
  echo Install Python 3.10 or newer, and enable "Add Python to PATH".
  echo Download: https://www.python.org/downloads/windows/
  >> "%LOG%" echo [ERROR] Python not found.
  goto :fail
)

echo Python: %PYTHON_EXE%
>> "%LOG%" echo [PYTHON] %PYTHON_EXE%

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo [ERROR] Python 3.10 or newer is required.
  "%PYTHON_EXE%" --version
  >> "%LOG%" echo [ERROR] Python version is below 3.10.
  goto :fail
)

if not exist "%VENV_PY%" (
  echo.
  echo [1/3] Creating local virtual environment...
  "%PYTHON_EXE%" -m venv "%CD%\.venv"
  if errorlevel 1 (
    echo [ERROR] Failed to create .venv.
    >> "%LOG%" echo [ERROR] venv creation failed.
    goto :fail
  )
) else (
  echo.
  echo [1/3] Existing virtual environment found.
)

echo [2/3] Installing or checking dependencies...
"%VENV_PY%" -m pip install --disable-pip-version-check --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [ERROR] Failed to prepare pip.
  >> "%LOG%" echo [ERROR] pip bootstrap failed.
  goto :fail
)

"%VENV_PY%" -m pip install --disable-pip-version-check -r "%CD%\requirements.txt"
if errorlevel 1 (
  echo [ERROR] Dependency installation failed.
  echo Check your internet connection, proxy, or antivirus settings.
  >> "%LOG%" echo [ERROR] requirements installation failed.
  goto :fail
)

for /f "delims=" %%P in ('"%VENV_PY%" "%CD%\scripts\find_free_port.py"') do set "APP_PORT=%%P"
if not defined APP_PORT set "APP_PORT=8501"

set "APP_URL=http://127.0.0.1:%APP_PORT%"
echo [3/3] Starting application: %APP_URL%
>> "%LOG%" echo [URL] %APP_URL%

timeout /t 1 /nobreak >nul
start "" "%APP_URL%"

"%VENV_PY%" -m streamlit run "%CD%\app.py" --server.address 127.0.0.1 --server.port %APP_PORT% --server.headless true --browser.gatherUsageStats false
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [ERROR] The web application stopped with exit code %EXIT_CODE%.
  >> "%LOG%" echo [ERROR] Streamlit exit code %EXIT_CODE%.
  goto :fail
)

echo.
echo Application stopped normally.
pause
exit /b 0

:fail
echo.
echo The launcher did not close. Read the error above.
echo A diagnostic file was saved to:
echo %LOG%
echo.
pause
exit /b 1
