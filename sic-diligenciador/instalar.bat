@echo off
REM ============================================================
REM  instalar.bat - Instala SIC Diligenciador en este PC.
REM  Uso: doble clic, o desde terminal: instalar.bat
REM  Requiere: Windows 10/11 con winget (viene preinstalado).
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ================================================================
echo  SIC Diligenciador - Instalador automatico
echo ================================================================
echo.

REM --- Paso 1: verificar winget ---
where winget >NUL 2>&1
if errorlevel 1 (
  echo [ERROR] winget no esta disponible.
  echo Actualiza Windows o instala App Installer desde Microsoft Store.
  pause
  exit /b 1
)
echo [1/7] winget OK

REM --- Paso 2: instalar dependencias del sistema ---
echo.
echo [2/7] Instalando software base con winget (Python, Node, Git, Tesseract, Poppler)...
echo       Si ya estan instalados, winget los omite automaticamente.

winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --silent
winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements --silent
winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements --silent
winget install -e --id oschwartz10612.Poppler --accept-package-agreements --accept-source-agreements --silent

REM Refrescar PATH en esta sesion (para que python y npm queden disponibles)
call :refresh_path

REM --- Paso 3: Claude Code CLI ---
echo.
echo [3/7] Instalando Claude Code CLI...
where npm >NUL 2>&1
if errorlevel 1 (
  echo [WARN] npm no se detecto en PATH. Cierra esta ventana y abre instalar.bat de nuevo.
  pause
  exit /b 1
)
call npm install -g @anthropic-ai/claude-code

REM --- Paso 4: Dependencias Python ---
echo.
echo [4/7] Instalando dependencias Python (Flask, Whisper, pytesseract, etc.)...
where python >NUL 2>&1
if errorlevel 1 (
  echo [WARN] python no se detecto. Cierra esta ventana y abre instalar.bat de nuevo.
  pause
  exit /b 1
)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM --- Paso 5: Precachear modelo Whisper ---
echo.
echo [5/7] Pre-descargando modelo Whisper "small" (~480 MB, una sola vez)...
python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('Whisper listo.')"

REM --- Paso 6: Verificar entorno ---
echo.
echo [6/7] Verificando entorno OCR...
python -c "import pdf_ocr; import json; print(json.dumps(pdf_ocr.diagnosticar(), indent=2, ensure_ascii=False))"

REM --- Paso 7: Sesion Claude ---
echo.
echo [7/7] Activa tu sesion de Claude Code (si es la primera vez).
echo       Se abrira el navegador. Loguea con tu cuenta Pro/Max.
echo.
echo Pulsa una tecla para continuar...
pause >NUL
call claude

echo.
echo ================================================================
echo  Instalacion terminada.
echo.
echo  Para arrancar la aplicacion: doble clic a iniciar.vbs
echo  Para detenerla:              doble clic a detener.vbs
echo  La web abre en:              http://localhost:8000
echo ================================================================
echo.
pause
exit /b 0


REM ----- subrutina: refresh PATH -----
:refresh_path
for /f "tokens=2*" %%a in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul ^| findstr /i "Path"') do set "MACHPATH=%%b"
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul ^| findstr /i "Path"') do set "USERPATH=%%b"
set "PATH=%MACHPATH%;%USERPATH%"
exit /b 0
