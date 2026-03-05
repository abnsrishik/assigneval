@echo off
title AssignEval Server
color 0A
echo.
echo  ============================================
echo   AssignEval - AI Assignment Evaluator
echo  ============================================
echo.
echo  Starting server...
cd /d "%~dp0"
python app.py
echo.
echo  Server stopped. Press any key to exit.
pause > nul
