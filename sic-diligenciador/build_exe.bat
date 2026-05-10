@echo off
REM build_exe.bat - empaqueta la app en un unico iniciar.exe usando PyInstaller.
REM Requiere: pip install pyinstaller (la primera vez).
REM El exe se genera en dist\iniciar.exe (aprox. 200-300 MB).

setlocal
cd /d "%~dp0"

where pyinstaller >NUL 2>&1
if errorlevel 1 (
  echo Instalando PyInstaller...
  python -m pip install --upgrade pyinstaller
)

echo.
echo ================================================================
echo  Empaquetando SIC Diligenciador como iniciar.exe
echo  Esto puede tardar 5-15 minutos la primera vez.
echo ================================================================
echo.

REM --noconsole: no abre ventana negra
REM --onefile: un solo archivo .exe
REM --add-data: empaqueta carpetas de recursos (separador ; en Windows)
REM --collect-all: incluye TODO de paquetes con binarios (faster-whisper, ctranslate2)
REM --name: nombre del exe final

pyinstaller ^
  --noconsole ^
  --onefile ^
  --name iniciar ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "prompts;prompts" ^
  --add-data "knowledge;knowledge" ^
  --add-data "CLAUDE.md;." ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all tokenizers ^
  --collect-all onnxruntime ^
  --hidden-import=docx ^
  --hidden-import=jinja2 ^
  --hidden-import=flask ^
  launcher.py

echo.
if exist dist\iniciar.exe (
  echo OK - generado: dist\iniciar.exe
  echo Cópialo a esta carpeta y dale doble-clic para arrancar.
) else (
  echo ERROR: PyInstaller no produjo dist\iniciar.exe.
  echo Revisa el log de arriba.
)
pause
