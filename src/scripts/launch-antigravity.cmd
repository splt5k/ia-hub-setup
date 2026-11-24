@echo off
setlocal

:: 1. Verifica se ja esta rodando como Administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -WindowStyle Hidden -Command "Start-Process cmd.exe -ArgumentList '/k title Antigravity CLI [Admin] & call """"%~f0"""" """"%~1""""' -Verb RunAs"
    exit /b
)

:: 2. Navega para a pasta alvo
if not "%~1"=="" (
    if exist "%~1\" (
        cd /d "%~1"
    ) else if exist "%~1" (
        cd /d "%~dp1"
    )
)

title Antigravity CLI [Admin]

:: 3. Localiza executavel do Antigravity
set "AGY_CMD=agy"
if exist "%LOCALAPPDATA%\agy\bin\agy.exe" set "AGY_CMD=%LOCALAPPDATA%\agy\bin\agy.exe"

:: 4. Inicia sessao
call "%AGY_CMD%" --dangerously-skip-permissions --model gemini-3.8-flash-medium
