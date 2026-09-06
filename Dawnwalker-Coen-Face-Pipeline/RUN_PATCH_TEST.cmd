@echo off
setlocal

REM ============================================================
REM Dawnwalker Coen - surgical position-buffer test
REM This file never edits the vanilla source in place.
REM ============================================================

set "ROOT=%~dp0"
set "PYTHON=python"

set "MANIFEST=%ROOT%manifest.local.json"
set "BASE=%ROOT%local\SK_HMA_Coen_Head_A_VANILLA.uexp"
set "VANILLA_CSV=%ROOT%local\vanilla_positions.csv"
set "EDITED_CSV=%ROOT%local\edited_positions.csv"
set "OUTDIR=%ROOT%out"
set "OUT=%OUTDIR%\SK_HMA_Coen_Head_A_TEST.uexp"
set "REPORT=%OUTDIR%\patch_report.json"

if not exist "%MANIFEST%" (
  echo [FAIL] Missing manifest.local.json
  echo Copy config\manifest.example.json to manifest.local.json and fill the real buffer values/hash.
  exit /b 1
)
if not exist "%BASE%" (
  echo [FAIL] Missing vanilla .uexp: %BASE%
  exit /b 1
)
if not exist "%VANILLA_CSV%" (
  echo [FAIL] Missing vanilla positions CSV: %VANILLA_CSV%
  exit /b 1
)
if not exist "%EDITED_CSV%" (
  echo [FAIL] Missing edited positions CSV: %EDITED_CSV%
  exit /b 1
)

if not exist "%OUTDIR%" mkdir "%OUTDIR%"

"%PYTHON%" "%ROOT%tools\patch_positions_surgical.py" ^
  --manifest "%MANIFEST%" ^
  --base "%BASE%" ^
  --vanilla-csv "%VANILLA_CSV%" ^
  --edited-csv "%EDITED_CSV%" ^
  --out "%OUT%" ^
  --report "%REPORT%"

if errorlevel 1 (
  echo.
  echo [FAIL] Patch was NOT accepted. Do not package this build.
  exit /b 1
)

echo.
echo [PASS] Surgical .uexp created:
echo %OUT%
echo.
echo Next: use the already validated local no-op packaging pipeline and replace ONLY this .uexp.
echo Report:
echo %REPORT%
exit /b 0
