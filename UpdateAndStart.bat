@echo off
title SillyTavern - update and start
cd /d "%~dp0"

where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")
%PY% --version >nul 2>&1 || (
  echo Python is not installed, or not on PATH.
  echo Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause & exit /b 1
)

rem Update this repo first, so the installer that runs below is the current one.
if exist .git (
  where git >nul 2>&1 && (
    echo Updating tweaks...
    git pull --rebase --autostash
  )
)

rem --update  : pull SillyTavern + Extension-WebSearch, then npm install
rem --start   : launch SillyTavern when everything is in place
%PY% install.py --update --start %*

echo.
echo SillyTavern has stopped.
pause
