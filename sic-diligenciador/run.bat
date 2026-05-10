@echo off
REM Inicia la app web local en http://localhost:8000
cd /d "%~dp0"
echo.
echo ==============================================
echo  SIC Diligenciador
echo  Abriendo http://localhost:8000 en tu navegador
echo  Para detener, cierra esta ventana o pulsa Ctrl+C
echo ==============================================
echo.
start "" http://localhost:8000
python app.py
pause
