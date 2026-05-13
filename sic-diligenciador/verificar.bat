@echo off
REM ============================================================
REM  verificar.bat - Chequea que la instalacion este completa.
REM ============================================================
cd /d "%~dp0"

echo.
echo ================================================================
echo  Verificando instalacion de SIC Diligenciador
echo ================================================================
echo.

echo [Python]
python --version 2>&1
echo.

echo [Node / npm]
node --version 2>&1
npm --version 2>&1
echo.

echo [Claude Code CLI]
call claude --version 2>&1
echo.

echo [Tesseract]
"C:\Program Files\Tesseract-OCR\tesseract.exe" --version 2>&1 | findstr /R "tesseract"
echo.

echo [Diagnostico OCR completo]
python -c "import pdf_ocr; import json; d = pdf_ocr.diagnosticar(); print(json.dumps(d, indent=2, ensure_ascii=False)); print(); print('OCR disponible:', pdf_ocr.disponible())"
echo.

echo [Paquetes Python clave]
python -c "import flask, docx, pypdf, faster_whisper, pytesseract, pdf2image, jinja2; print('Todas las dependencias OK')"
echo.

echo ================================================================
echo  Si algun componente dice ERROR o no se encuentra, corre:
echo     instalar.bat
echo ================================================================
pause
