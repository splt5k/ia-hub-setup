@echo off
setlocal

:: 1. Verifica se ja esta rodando como Administrador
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -WindowStyle Hidden -Command "Start-Process cmd.exe -ArgumentList '/k title Codex CLI [Admin] & call """"%~f0"""" """"%~1""""' -Verb RunAs"
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

title Codex CLI [Admin]

:: 3. Localiza executavel do Codex
set "CODEX_CMD=codex"
if exist "%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe" set "CODEX_CMD=%LOCALAPPDATA%\Programs\OpenAI\Codex\bin\codex.exe"

:: 4. Inicia sessao
call "%CODEX_CMD%" --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust -c model="gpt-6.2-sol" -c model_reasoning_effort="medium" --search
