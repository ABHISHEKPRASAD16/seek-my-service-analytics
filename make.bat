@echo off
setlocal EnableDelayedExpansion

REM ===========================================================================
REM Seek My Service - Windows build script
REM
REM Usage:  make <target>
REM
REM Targets:
REM   setup      create .venv on Python 3.12 and install pinned dependencies
REM   generate   build the CSVs in data\
REM   validate   run the 16 integrity checks
REM   train      train and persist all three models
REM   serve      start the three FastAPI services in separate windows
REM   test       run the pytest suite
REM   measures   regenerate measures.dax and the Tabular Editor script
REM   all        setup, generate, validate, train, test
REM   clean      delete generated data and model artefacts
REM
REM Python 3.12 specifically: 3.13 and 3.14 wheels for LightGBM still lag, and
REM this machine defaults to 3.14.
REM ===========================================================================

set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "TARGET=%~1"

if "%TARGET%"=="" set "TARGET=help"

if /I "%TARGET%"=="setup"     goto :setup
if /I "%TARGET%"=="generate"  goto :generate
if /I "%TARGET%"=="validate"  goto :validate
if /I "%TARGET%"=="train"     goto :train
if /I "%TARGET%"=="serve"     goto :serve
if /I "%TARGET%"=="dashboard" goto :dashboard
if /I "%TARGET%"=="test"      goto :test
if /I "%TARGET%"=="measures"  goto :measures
if /I "%TARGET%"=="all"       goto :all
if /I "%TARGET%"=="clean"     goto :clean
if /I "%TARGET%"=="help"      goto :help

echo Unknown target "%TARGET%".
echo.
goto :help

REM ---------------------------------------------------------------------------
:setup
echo [setup] locating Python 3.12
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python 3.12 not found.
    echo   Install it from python.org and tick "Add python.exe to PATH",
    echo   or run:  winget install Python.Python.3.12
    exit /b 1
)
if not exist "%VPY%" (
    echo [setup] creating virtual environment in %VENV%
    py -3.12 -m venv "%VENV%"
    if errorlevel 1 exit /b 1
)
echo [setup] installing pinned dependencies
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 exit /b 1
echo [setup] done
"%VPY%" --version
goto :eof

REM ---------------------------------------------------------------------------
:generate
call :require_venv || exit /b 1
echo [generate] building CSVs into data\
"%VPY%" generator\generate.py
exit /b %errorlevel%

REM ---------------------------------------------------------------------------
:validate
call :require_venv || exit /b 1
echo [validate] running integrity checks
"%VPY%" validate.py
exit /b %errorlevel%

REM ---------------------------------------------------------------------------
:train
call :require_venv || exit /b 1
echo [train] training all models
"%VPY%" ml\train_all.py
exit /b %errorlevel%

REM ---------------------------------------------------------------------------
:test
call :require_venv || exit /b 1
echo [test] running pytest
"%VPY%" -m pytest tests -q
exit /b %errorlevel%

REM ---------------------------------------------------------------------------
:measures
call :require_venv || exit /b 1
echo [measures] regenerating the DAX library and Tabular Editor script
"%VPY%" powerbi\build_measures.py
exit /b %errorlevel%

REM ---------------------------------------------------------------------------
:dashboard
call :require_venv || exit /b 1
echo [dashboard] starting the Streamlit dashboard
echo.
echo   Opening http://localhost:8501 in your browser.
echo   Press Ctrl+C in this window to stop it.
echo.
"%VPY%" -m streamlit run streamlit_app.py --server.port 8501
exit /b %errorlevel%

REM ---------------------------------------------------------------------------
:serve
call :require_venv || exit /b 1
echo [serve] starting three services in separate windows
echo   forecast  http://127.0.0.1:8001/docs
echo   match     http://127.0.0.1:8002/docs
echo   pricing   http://127.0.0.1:8003/docs
echo.
echo Close the three windows to stop them.
start "SMS forecast_service" cmd /k ""%VPY%" -m uvicorn ml.forecast_service:app --port 8001"
start "SMS match_service"    cmd /k ""%VPY%" -m uvicorn ml.match_service:app --port 8002"
start "SMS pricing_service"  cmd /k ""%VPY%" -m uvicorn ml.pricing_service:app --port 8003"
goto :eof

REM ---------------------------------------------------------------------------
:all
call :setup    || exit /b 1
call "%~f0" generate || exit /b 1
call "%~f0" validate || exit /b 1
call "%~f0" train    || exit /b 1
call "%~f0" test     || exit /b 1
echo.
echo [all] complete. Next: open Power BI Desktop and follow powerbi\BUILD_GUIDE.md
goto :eof

REM ---------------------------------------------------------------------------
:clean
echo [clean] removing generated data and model artefacts
if exist data      del /q data\*.csv 2>nul
if exist ml\models del /q ml\models\*.joblib ml\models\*.json 2>nul
for /d /r %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
if exist .pytest_cache rd /s /q .pytest_cache 2>nul
echo [clean] done. The virtual environment was left alone; use "make setup" to rebuild it.
goto :eof

REM ---------------------------------------------------------------------------
:require_venv
if not exist "%VPY%" (
    echo ERROR: no virtual environment found at %VPY%
    echo Run:  make setup
    exit /b 1
)
exit /b 0

REM ---------------------------------------------------------------------------
:help
echo.
echo Seek My Service - build targets
echo.
echo   make setup      create .venv (Python 3.12) and install dependencies
echo   make generate   build the CSVs in data\
echo   make validate   run the 16 data integrity checks
echo   make train      train and persist all three models
echo   make dashboard  open the Streamlit dashboard in your browser
echo   make serve      start the three FastAPI services
echo   make test       run the pytest suite
echo   make measures   regenerate the DAX measure library
echo   make all        setup, generate, validate, train, test
echo   make clean      delete generated data and model artefacts
echo.
echo Typical first run:
echo   make all
echo   make dashboard
echo.
goto :eof
