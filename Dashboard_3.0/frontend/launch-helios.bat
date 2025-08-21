@echo off
title Helios Dev Launcher

REM ─── Start backend server ────────────────────────────────
cd /d C:\Helios\
start "" /min cmd /c "uvicorn core_py.main:app --reload --port 3333"

REM ─── Start frontend dev server ───────────────────────────
cd /d C:\Helios\Dashboard_3.0\frontend\
start "" /min cmd /c "npm run dev"

REM ─── Wait for servers to boot ────────────────────────────
timeout /t 4 >nul

REM ─── Launch ngrok tunnel ─────────────────────────────────
start "" /min cmd /c "C:\ProgramData\chocolatey\bin\ngrok.exe http --domain=helios.ngrok.dev 5173"

REM ─── Wait for ngrok to stabilise ─────────────────────────
timeout /t 4 >nul

REM ─── Launch Helios PWA in Chrome ─────────────────────────
start "" "C:\Users\MikeHards\AppData\Local\Google\Chrome\User Data\Default\Web Applications\_crx_idemibpphagihbobmgmaojhjfidlfpdl\Helios PWA.lnk"
