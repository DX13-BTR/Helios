@echo off
cd /d C:\Helios
call venv\Scripts\activate.bat
uvicorn core_py.main:app --host 127.0.0.1 --port 3333
pause
