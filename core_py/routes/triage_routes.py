from fastapi import APIRouter
import subprocess

router = APIRouter()   # <-- this must exist before you decorate

@router.post("/reload")
async def reload_triaged_tasks():
    try:
        result = subprocess.run(
            ["python", "core_py/triage_tasks.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )
        out = (result.stdout or "").strip()
        return {"status": "success", "output": out}
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "details": ((e.stderr or "").strip()) or str(e)
        }
