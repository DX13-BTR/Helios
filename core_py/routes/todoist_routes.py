import json
import os
from datetime import date

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

# --- Token helper ---
def load_todoist_token() -> str:
    with open("core_py/routes/todoist_token.json", "r") as f:
        return f.read().strip()

# --- GET urgent tasks (Primary feed) ---
@router.get("/api/todoist/urgent_tasks")
async def get_urgent_tasks():
    token = load_todoist_token()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.todoist.com/rest/v2/tasks",
            headers={"Authorization": f"Bearer {token}"}
        )

    if resp.status_code != 200:
        return JSONResponse(status_code=resp.status_code, content={"error": resp.text})

    tasks = resp.json()
    today = date.today().isoformat()

    # Filter logic: priority 4 OR due today/overdue
    urgent_tasks = []
    for task in tasks:
        is_priority_urgent = task.get("priority") == 4
        due = task.get("due")
        is_due_today = bool(due and due.get("date") == today)
        is_overdue = bool(due and due.get("is_overdue", False))

        if is_priority_urgent or is_due_today or is_overdue:
            urgent_tasks.append({
                "id": task["id"],
                "content": task.get("content") or "[No Content]",
                "due_date": (due or {}).get("date"),
                "due_time": (due or {}).get("datetime"),
                "priority": task.get("priority"),
                "project_id": task.get("project_id"),
                "url": task.get("url"),
                "source": "todoist",  # helpful for the UI to branch logic
            })

    return {"tasks": urgent_tasks}

# --- POST close task (used by Primary "Complete") ---
@router.post("/api/todoist/tasks/{task_id}/close")
async def close_todoist_task(task_id: str):
    token = load_todoist_token()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.todoist.com/rest/v2/tasks/{task_id}/close",
            headers={"Authorization": f"Bearer {token}"}
        )
    if resp.status_code in (200, 204):
        return {"ok": True}
    return JSONResponse(status_code=resp.status_code, content={"error": resp.text})

# --- OAuth callback (unchanged, just tidied) ---
@router.get("/integrations/todoist/callback")
async def todoist_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return HTMLResponse("❌ Missing code in callback", status_code=400)

    payload = {
        "client_id": os.getenv("TODOIST_CLIENT_ID"),
        "client_secret": os.getenv("TODOIST_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": os.getenv("TODOIST_REDIRECT_URI"),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post("https://todoist.com/oauth/access_token", data=payload)

    if resp.status_code != 200:
        return HTMLResponse(f"❌ Token exchange failed: {resp.text}", status_code=500)

    token = resp.json().get("access_token")
    if not token:
        return HTMLResponse("❌ No access token in response", status_code=500)

    with open("core_py/routes/todoist_token.json", "w") as f:
        f.write(token)

    return HTMLResponse("✅ Todoist connected successfully. You can close this window.")
