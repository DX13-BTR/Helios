from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import os
import base64
from datetime import datetime

router = APIRouter(tags=["Toggl"])

WORKSPACE_ID = int(os.getenv("TOGGL_WORKSPACE_ID"))
TOGGL_API_KEY = os.getenv("TOGGL_API_KEY")
AUTH_HEADER = {
    "Authorization": "Basic " + base64.b64encode(f"{TOGGL_API_KEY}:api_token".encode()).decode()
}

class StartTimerRequest(BaseModel):
    description: str
    clientId: str
    projectId: str

class PauseRequest(BaseModel):
    entryId: str

class ResumeRequest(BaseModel):
    description: str
    clientId: str

@router.get("/current-time-entry")
def get_current_time_entry():
    try:
        response = requests.get(
            "https://api.track.toggl.com/api/v9/me/time_entries/current",
            headers=AUTH_HEADER
        )
        response.raise_for_status()  # <-- CRUCIAL

        try:
            return response.json()
        except ValueError:
            raise HTTPException(status_code=502, detail="Toggl returned invalid JSON.")

    except requests.exceptions.HTTPError as http_err:
        print("❌ HTTP error:", http_err)
        return {"error": str(http_err), "status_code": response.status_code}

    except Exception as e:
        print("❌ Unexpected error:", e)
        raise HTTPException(status_code=500, detail="Internal error fetching Toggl timer.")


@router.get("/projects")
def get_toggl_projects():
    try:
        response = requests.get(
            f"https://api.track.toggl.com/api/v9/workspaces/{WORKSPACE_ID}/projects",
            headers=AUTH_HEADER
        )
        response.raise_for_status()
        projects = response.json()
        return {
            "projects": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "client_id": p.get("client_id")  # <-- Add this line
                }
                for p in projects
            ]
        }
    except Exception as e:
        print("❌ Failed to fetch Toggl projects:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch Toggl projects")


@router.get("/clients")
def get_toggl_clients():
    try:
        response = requests.get(
            f"https://api.track.toggl.com/api/v9/workspaces/{WORKSPACE_ID}/clients",
            headers=AUTH_HEADER
        )
        response.raise_for_status()
        clients = response.json()
        return {"clients": [{"id": c["id"], "name": c["name"]} for c in clients]}
    except Exception as e:
        print("❌ Failed to fetch Toggl clients:", e)
        raise HTTPException(status_code=500, detail="Failed to fetch Toggl clients")

@router.post("/pause-time-entry")
def pause_time_entry(payload: PauseRequest):
    try:
        url = f"https://api.track.toggl.com/api/v9/workspaces/{WORKSPACE_ID}/time_entries/{payload.entryId}/stop"
        response = requests.put(url, headers=AUTH_HEADER)
        return response.json()
    except Exception as e:
        print("❌ Pause error:", e)
        raise HTTPException(status_code=500, detail="Failed to pause time entry")

@router.post("/resume-time-entry")
def resume_time_entry(payload: ResumeRequest):
    try:
        url = f"https://api.track.toggl.com/api/v9/workspaces/{WORKSPACE_ID}/time_entries"
        data = {
            "created_with": "Helios",
            "description": payload.description,
            "tags": [],
            "start": datetime.utcnow().isoformat() + "Z",
            "duration": -1,
            "workspace_id": WORKSPACE_ID,
            "project_id": None,
            "client_id": payload.clientId
        }
        response = requests.post(url, headers=AUTH_HEADER, json=data)
        return response.json()
    except Exception as e:
        print("❌ Resume error:", e)
        raise HTTPException(status_code=500, detail="Failed to resume time entry")

@router.post("/start")
def start_timer(payload: StartTimerRequest):
    print("🔥 Incoming payload to /start:")
    print("description:", payload.description)
    print("projectId:", payload.projectId)
    print("clientId:", payload.clientId)
    try:
        url = f"https://api.track.toggl.com/api/v9/workspaces/{WORKSPACE_ID}/time_entries"
        data = {
            "created_with": "Helios",
            "description": payload.description,
            "tags": [],
            "start": datetime.utcnow().isoformat() + "Z",
            "duration": -1,
            "workspace_id": WORKSPACE_ID,
            "project_id": int(payload.projectId),  # ← fix here
            "client_id": int(payload.clientId),  
        }
        print("🟢 Start timer payload:", data)

        response = requests.post(url, headers=AUTH_HEADER, json=data)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as http_err:
        print("❌ HTTP error occurred:", http_err)
        if http_err.response is not None:
            print("🔍 Response:", http_err.response.text)
        raise HTTPException(status_code=500, detail="Failed to start timer: HTTP error")

@router.post("/stop")
def stop_timer():
    # Step 1: Get current entry
    current_url = "https://api.track.toggl.com/api/v9/me/time_entries/current"
    current_response = requests.get(current_url, headers=AUTH_HEADER)
    try:
        current_response.raise_for_status()
        current_data = current_response.json()
        time_entry_id = current_data.get("id")
        if not time_entry_id:
            raise ValueError("No active timer found.")
    except Exception as e:
        print("❌ Error retrieving current time entry:", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve current timer")

    # Step 2: Stop the entry
    stop_url = f"https://api.track.toggl.com/api/v9/workspaces/{WORKSPACE_ID}/time_entries/{time_entry_id}/stop"
    stop_response = requests.patch(stop_url, headers=AUTH_HEADER)
    try:
        stop_response.raise_for_status()
        return stop_response.json()
    except requests.exceptions.HTTPError as http_err:
        print("❌ HTTP error during stop:", http_err)
        if http_err.response is not None:
            print("🔍 Response:", http_err.response.text)
        raise HTTPException(status_code=500, detail="Failed to stop timer: HTTP error")
