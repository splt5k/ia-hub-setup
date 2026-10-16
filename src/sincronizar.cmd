@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync.ps1"
echo Sincronizado. & timeout /t 3 >nul
