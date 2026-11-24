@echo off
setlocal

:: 1. Verifica se ja esta rodando como Administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -WindowStyle Hidden -Command "Start-Process cmd.exe -ArgumentList '/k title Claude CLI [Admin] & call """"%~f0"""" """"%~1""""' -Verb RunAs"
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

:: 3. Configura ambiente do Claude
set "CLAUDE_CODE_SUBAGENT_MODEL=haiku"
title Claude CLI [Admin]

:: 4. Localiza executavel do Claude
set "CLAUDE_CMD=claude"
if exist "%APPDATA%\npm\claude.cmd" set "CLAUDE_CMD=%APPDATA%\npm\claude.cmd"

:: 5. Inicia sessao
call "%CLAUDE_CMD%" --dangerously-skip-permissions --model sonnet --advisor opus --chrome
