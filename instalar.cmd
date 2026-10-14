@echo off
chcp 65001 >nul
title IA-Hub - Instalador
echo Instalando IA-Hub a partir de %~dp0 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (echo. & echo FALHOU - veja a mensagem acima.) else (echo. & echo Pronto. Pode fechar esta janela.)
pause
