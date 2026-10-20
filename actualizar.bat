@echo off
cd /d "%~dp0"
echo ========================================
echo   Actualizando Liga Biwenger Seg.Aux...
echo ========================================
python biwenger_admin.py
echo.
echo ========================================
echo   ¡Proceso finalizado con exito!
echo ========================================
pause