@echo off
REM ---------------------------------------------------------------------------
REM PhyCo-Sim single-object scenario launcher (Windows)
REM
REM Usage:
REM   run_scenario.cmd circular [extra args...]
REM   run_scenario.cmd damped   [extra args...]
REM
REM All arguments after the mode are forwarded verbatim to the scenario script.
REM ---------------------------------------------------------------------------
setlocal

set "PROJECT_ROOT=%~dp0.."
set "BLENDER=%PROJECT_ROOT%\tools\runtime\blender-3.4.1-windows-x64\blender.exe"
set "SCRIPT=%PROJECT_ROOT%\code\scenarios\run_single_object.py"

if not exist "%BLENDER%" (
  echo [ERROR] Blender runtime not found at "%BLENDER%"
  exit /b 1
)
if not exist "%SCRIPT%" (
  echo [ERROR] scenario script not found at "%SCRIPT%"
  exit /b 1
)

set "MODE=%~1"
if "%MODE%"=="" (
  echo Usage: run_scenario.cmd ^<circular^|damped^> [args...]
  exit /b 1
)
shift

"%BLENDER%" --background --factory-startup --python "%SCRIPT%" -- --motion %MODE% %*

endlocal
