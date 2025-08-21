# shutdown.py
import os
import subprocess
import signal
from fastapi import APIRouter

shutdown_router = APIRouter()

@shutdown_router.get("/exit")
def shutdown_helios():
    try:
        # Step up to Helios root
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        script_path = os.path.join(base_dir, "Dashboard_3.0", "frontend", "shutdown.bat")

        subprocess.Popen([script_path], shell=True)

        return {"status": "shutdown triggered"}
    except Exception as e:
        return {"error": str(e)}
