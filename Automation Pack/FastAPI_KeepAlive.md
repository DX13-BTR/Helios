# Keeping FastAPI (Helios) Server Alive

To keep the Helios FastAPI server running on port 3333:

## Option 1: Manual (dev)
```bash
cd C:\Helios
call venv\Scripts\activate.bat
uvicorn main:app --host 127.0.0.1 --port 3333
```

## Option 2: Scheduled Task (recommended)
Create a `.bat` script:
```bat
cd /d C:\Helios
call venv\Scripts\activate.bat
uvicorn main:app --host 127.0.0.1 --port 3333
```

Then use Task Scheduler to run this script **on login** or **at startup**, and set it to **Run whether user is logged on or not**.

Ensure firewall exceptions are added if needed.
