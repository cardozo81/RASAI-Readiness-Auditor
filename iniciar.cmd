@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title RASAi - Search & AI Readiness Auditor

set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "CONSOLE_EXE=%CD%\.venv\Scripts\rasai-console.exe"
set "STAMP_FILE=%CD%\.venv\.rasai-pyproject.sha256"
set "NEED_INSTALL=0"
set "OPTIONAL_EXTRAS="

echo [RASAi] Verificando ambiente local...

if exist "%VENV_DIR%" if not exist "%VENV_PY%" goto :bad_venv

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>&1
    if errorlevel 1 goto :bad_venv
)

if not exist "%VENV_PY%" (
    call :find_python
    if errorlevel 1 (
        call :install_python
        if errorlevel 1 goto :fail
        call :find_python
        if errorlevel 1 goto :python_not_found_after_install
    )

    echo [RASAi] Criando ambiente virtual .venv...
    "!PYTHON_EXE!" !PYTHON_ARG! -m venv "%VENV_DIR%"
    if errorlevel 1 goto :fail
)

if not exist "%VENV_PY%" goto :fail

for /f "usebackq delims=" %%E in (`"%VENV_PY%" -c "import pathlib,tomllib; data=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); extras=sorted((data.get('project',{}).get('optional-dependencies',{}) or {}).keys()); print(','.join(extras))"`) do set "OPTIONAL_EXTRAS=%%E"

if not exist "%CONSOLE_EXE%" set "NEED_INSTALL=1"

if "!NEED_INSTALL!"=="0" (
    "%VENV_PY%" -c "import importlib.metadata as m, pathlib, rasai, playwright, tzdata; root=(pathlib.Path.cwd()/'src').resolve(); src=pathlib.Path(rasai.__file__).resolve(); m.version('rasai-readiness-auditor'); raise SystemExit(0 if src.is_relative_to(root) else 1)" >nul 2>&1
    if errorlevel 1 set "NEED_INSTALL=1"
)

if "!NEED_INSTALL!"=="0" (
    "%VENV_PY%" -c "import hashlib,pathlib,sys; expected=hashlib.sha256(pathlib.Path('pyproject.toml').read_bytes()).hexdigest(); stamp=pathlib.Path(sys.argv[1]); raise SystemExit(0 if stamp.is_file() and stamp.read_text(encoding='ascii').strip()==expected else 1)" "%STAMP_FILE%" >nul 2>&1
    if errorlevel 1 set "NEED_INSTALL=1"
)

if "!NEED_INSTALL!"=="1" (
    if defined OPTIONAL_EXTRAS (
        echo [RASAi] Instalando ou atualizando dependencias obrigatorias e opcionais: !OPTIONAL_EXTRAS!...
        "%VENV_PY%" -m pip install --disable-pip-version-check -e ".[!OPTIONAL_EXTRAS!]"
    ) else (
        echo [RASAi] Instalando ou atualizando dependencias do projeto...
        "%VENV_PY%" -m pip install --disable-pip-version-check -e .
    )
    if errorlevel 1 goto :fail

    "%VENV_PY%" -c "import hashlib,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(hashlib.sha256(pathlib.Path('pyproject.toml').read_bytes()).hexdigest(), encoding='ascii')" "%STAMP_FILE%" >nul 2>&1
    if errorlevel 1 echo [RASAi] Aviso: nao foi possivel gravar o marcador local de dependencias.
)

if not exist "%CONSOLE_EXE%" goto :fail

"%VENV_PY%" -c "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); ok=Path(p.chromium.executable_path).is_file(); p.stop(); raise SystemExit(0 if ok else 1)" >nul 2>&1
if errorlevel 1 (
    echo [RASAi] Chromium do Playwright ausente. Instalando...
    "%VENV_PY%" -m playwright install chromium
    if errorlevel 1 goto :fail
)

cls
"%CONSOLE_EXE%"
set "EXIT_CODE=%ERRORLEVEL%"
endlocal & exit /b %EXIT_CODE%

:find_python
set "PYTHON_EXE="
set "PYTHON_ARG="

py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    set "PYTHON_ARG=-3.13"
    exit /b 0
)

if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
    "%LocalAppData%\Programs\Python\Python313\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python313\python.exe"
        exit /b 0
    )
)

if exist "%ProgramFiles%\Python313\python.exe" (
    "%ProgramFiles%\Python313\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=%ProgramFiles%\Python313\python.exe"
        exit /b 0
    )
)

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    exit /b 0
)

python3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python3.13"
    exit /b 0
)

exit /b 1

:install_python
echo [RASAi] CPython 3.13 nao encontrado.
where winget >nul 2>&1
if errorlevel 1 (
    echo [ERRO] WinGet nao esta disponivel para instalar Python 3.13 automaticamente.
    echo Instale CPython 3.13 e execute iniciar.cmd novamente.
    exit /b 1
)

echo [RASAi] Instalando CPython 3.13 via WinGet...
winget install --id Python.Python.3.13 --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [ERRO] A instalacao automatica do Python 3.13 falhou.
    exit /b 1
)
exit /b 0

:bad_venv
echo.
echo [ERRO] A pasta .venv existe, mas esta incompleta ou nao usa CPython 3.13.
echo Renomeie ou remova ".venv" e execute iniciar.cmd novamente.
goto :fail_pause

:python_not_found_after_install
echo.
echo [ERRO] Python 3.13 foi solicitado ao WinGet, mas nao ficou acessivel nesta sessao.
echo Feche esta janela e execute iniciar.cmd novamente.
goto :fail_pause

:fail
echo.
echo [ERRO] Nao foi possivel preparar ou iniciar o RASAi.

:fail_pause
pause
endlocal
exit /b 1