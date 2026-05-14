@echo off
setlocal
title AutoEdit-Lite
color 0B

echo.
echo ============================================================
echo   AutoEdit-Lite - AI Video Editor
echo ============================================================
echo.

:: ── Activate venv created by install_all_windows.ps1 ──────────────────────
:: Without this, "python main.py" below would use whichever Python is on
:: system PATH and miss every pip dep installed into the venv. This was the
:: #1 cause of "ModuleNotFoundError: faster_whisper" on fresh installs.
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
) else (
    echo   [WARN] venv not found at %~dp0venv. Using system Python.
    echo          Run install_all_windows.bat to create the virtual environment.
    echo.
)

:: ── Quick sanity checks ───────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python not found. Please run install_all_windows.bat first.
    pause & exit /b 1
)
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] FFmpeg not found. Please run setup_windows.bat first.
    pause & exit /b 1
)
if not exist .env (
    echo   [ERROR] .env file not found. Please run setup_windows.bat first.
    pause & exit /b 1
)
python -c "import faster_whisper" >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python packages not installed. Please run setup_windows.bat first.
    pause & exit /b 1
)

:: ── Choose video file ─────────────────────────────────────────────────────
echo   Drag your video file into this window and press Enter,
echo   OR type the full path to your video file.
echo.
echo   Example:  C:\Users\YourName\Videos\interview.mp4
echo.
set /p INPUT="  Video path: "

if "%INPUT%"=="" (
    echo.
    echo   [ERROR] No file entered. Please run again and enter a path.
    pause & exit /b 1
)

:: Strip surrounding quotes if user dragged a file
set INPUT=%INPUT:"=%

if not exist "%INPUT%" (
    echo.
    echo   [ERROR] File not found: %INPUT%
    echo   Check the path and try again.
    pause & exit /b 1
)

:: ── Choose quality mode ───────────────────────────────────────────────────
echo.
echo   Choose editing quality:
echo     1 = light      (removes obvious mistakes only)
echo     2 = balanced   (removes mistakes + filler words) [RECOMMENDED]
echo     3 = aggressive (tightest possible edit)
echo.
set /p QCHOICE="  Enter 1, 2, or 3 (press Enter for default 'balanced'): "

if "%QCHOICE%"=="1" set QUALITY=light
if "%QCHOICE%"=="3" set QUALITY=aggressive
if not defined QUALITY set QUALITY=balanced
if "%QUALITY%"=="" set QUALITY=balanced

:: ── Choose Whisper model ──────────────────────────────────────────────────
echo.
echo   Choose transcription speed:
echo     1 = base    (faster, good enough for clear audio)
echo     2 = medium  (slower, more accurate)            [RECOMMENDED]
echo     3 = large   (slowest, most accurate, needs 8GB+ RAM)
echo.
set /p MCHOICE="  Enter 1, 2, or 3 (press Enter for 'medium'): "

if "%MCHOICE%"=="1" set MODEL=base
if "%MCHOICE%"=="3" set MODEL=large
if not defined MODEL set MODEL=medium
if "%MODEL%"=="" set MODEL=medium

:: ── Confirm and run ───────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Settings
echo   File    : %INPUT%
echo   Quality : %QUALITY%
echo   Model   : %MODEL%
echo   Output  : output\edited.mp4
echo ============================================================
echo.
echo   Press any key to start editing...
echo   (Press Ctrl+C to cancel)
pause >nul

:: Force CPU-only mode — prevents cublas64_12.dll error on machines without CUDA 12
set CUDA_VISIBLE_DEVICES=-1

echo.
python main.py --input "%INPUT%" --model %MODEL% --quality %QUALITY% --output output\edited.mp4

echo.
if %errorlevel% equ 0 (
    echo   Finished! Your edited video is in the  output\  folder.
    echo   Open File Explorer and look for:  output\edited.mp4
) else (
    echo   Something went wrong. Check the messages above for details.
    echo   You can also check the  logs\  folder for debug information.
)

echo.
pause
