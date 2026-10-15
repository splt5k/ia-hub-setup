@echo off
chcp 65001 >nul
title IA-Hub - Instalador
echo Instalando IA-Hub a partir de %~dp0 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
set "result=%errorlevel%"
if not "%result%"=="0" (echo. & echo INCOMPLETO - veja os erros acima e execute novamente.) else (echo. & echo Pronto. Pode fechar esta janela.)
pause
exit /b %result%
