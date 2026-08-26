@echo off
title Install SillyTavern local search
cd /d "%~dp0"

where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>&1 || (
  echo Python is not installed, or not on PATH.
  echo Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause & exit /b 1
)

%PY% install.py %*
echo.
pause
