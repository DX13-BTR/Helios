@echo off

:: Kill ngrok
taskkill /f /im ngrok.exe >nul 2>&1

:: Kill frontend (Vite — also runs on node)
taskkill /f /im node.exe >nul 2>&1

:: Kill FastAPI backend (Python)
taskkill /f /im python.exe >nul 2>&1


exit
