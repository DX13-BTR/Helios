from fastapi import APIRouter, Request, HTTPException
import os
import requests
from core_py.triage_tasks import score_task
from dotenv import load_dotenv
from core_py.db.database import insert_or_replace_task

load_dotenv()

CLICKUP_TOKEN = os.getenv("CLICKUP_API_KEY")
router = APIRouter()

@router.post("/webhook")
async def handle_clickup_webhook(request: Request):
    try:
        payload = await request.json()
        print("🔍 Raw webhook payload received:")
        print(payload)

        # Look for task_id at the top level or nested
        task_id = payload.get("task_id") or payload.get("task", {}).get("id")
        if not task_id:
            raise HTTPException(status_code=400, detail="Missing task_id")

        # Step 1: Fetch full task details
        headers = {"Authorization": CLICKUP_TOKEN}
        task_url = f"https://api.clickup.com/api/v2/task/{task_id}"
        response = requests.get(task_url, headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to fetch task details")

        task = response.json()

        # Inject space name
        task["space_name"] = task.get("space", {}).get("name", "")

        # Step 2 & 3: Score task and Update DB
        scored = score_task(task)
        insert_or_replace_task(scored)

        return {"success": True, "task_id": task_id}

    except KeyError as e:
        print(f"[score_task] Key error: '{e}' — skipping task update.")
        raise HTTPException(status_code=500, detail=f"Missing expected field: {e}")

    except Exception as e:
        print(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
