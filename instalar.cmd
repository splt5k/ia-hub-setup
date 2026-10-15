@echo off
chcp 65001 >nul
title IA-Hub - Instalador
if /I "%~1"=="--cli" goto cli
if /I "%~1"=="--preview" goto preview
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-ui.ps1"
goto finish
:preview
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-ui.ps1" -Preview
goto finish
:cli
echo Instalando IA-Hub a partir de %~dp0 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
:finish
set "result=%errorlevel%"
if not "%result%"=="0" (echo. & echo INCOMPLETO - veja os erros acima e execute novamente.) else (echo. & echo Pronto. Pode fechar esta janela.)
pause
exit /b %result%
