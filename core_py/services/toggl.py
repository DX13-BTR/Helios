import os
import requests

TOGGL_API_KEY = os.getenv("TOGGL_API_KEY")
AUTH_HEADER = {
    "Authorization": f"Basic {TOGGL_API_KEY}"
}

BASE_URL = "https://api.track.toggl.com/api/v9"


def get_all_clients():
    response = requests.get(f"{BASE_URL}/clients", headers=AUTH_HEADER)
    response.raise_for_status()
    return response.json()


def get_all_projects():
    response = requests.get(f"{BASE_URL}/me/projects", headers=AUTH_HEADER)
    response.raise_for_status()
    return response.json()


def get_current_time_entry():
    response = requests.get(f"{BASE_URL}/me/time_entries/current", headers=AUTH_HEADER)
    response.raise_for_status()
    return response.json()
