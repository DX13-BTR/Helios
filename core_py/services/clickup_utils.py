import os
import requests
from functools import lru_cache

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")
HEADERS = {"Authorization": CLICKUP_API_KEY}

def get_space_name_for_task(task_id):
    """
    Fetch the space name for a given ClickUp task.
    This is used to categorise tasks by workspace (e.g. Personal, Clients).
    """

    # Step 1: Get task metadata
    task_url = f"https://api.clickup.com/api/v2/task/{task_id}"
    try:
        task_res = requests.get(task_url, headers=HEADERS)
        task_res.raise_for_status()
        list_id = task_res.json().get("list", {}).get("id")
    except Exception as e:
        print(f"[ClickUp] Failed to fetch task {task_id}: {e}")
        return None

    if not list_id:
        print(f"[ClickUp] No list ID found for task {task_id}")
        return None

    # Step 2: Get list metadata
    list_url = f"https://api.clickup.com/api/v2/list/{list_id}"
    try:
        list_res = requests.get(list_url, headers=HEADERS)
        list_res.raise_for_status()
        space_name = list_res.json().get("space", {}).get("name")
        return space_name.strip() if space_name else None
    except Exception as e:
        print(f"[ClickUp] Failed to fetch list {list_id} for task {task_id}: {e}")
        return None
