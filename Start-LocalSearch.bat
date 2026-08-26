@echo off
title SillyTavern local search (DuckDuckGo, keyless)
cd /d "%~dp0"

rem Prefer the py launcher so this survives a Python reinstall on another path.
where py >nul 2>&1 && (set "PY=py -3") || (set "PY=python")

%PY% -c "import ddgs" >nul 2>&1 || (
  echo Installing the one dependency ^(ddgs^)...
  %PY% -m pip install ddgs || (echo FAILED to install ddgs & pause & exit /b 1)
)

echo.
echo Leave this window open while you use SillyTavern's Web Search.
echo Close it to stop.  Ctrl+C also works.
echo.
%PY% local_search.py --port 18888
pause
