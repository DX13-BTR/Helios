# core_py/integrations/clickup_client.py
from __future__ import annotations

import os
import time
import typing as t
import json
import requests


class ClickUpError(RuntimeError):
    pass


def _env(name: str, required: bool = False, default: t.Optional[str] = None) -> t.Optional[str]:
    v = os.getenv(name, default)
    if required and not v:
        raise RuntimeError(f"Missing {name} in environment.")
    return v


def _headers(api_key: str) -> dict:
    return {"Authorization": api_key, "Content-Type": "application/json"}


def _retry_request(
    method: str,
    url: str,
    headers: dict,
    params: dict | None = None,
    json_body: dict | None = None
) -> requests.Response:
    # 429-aware retry with backoff
    backoff = 1.0
    for attempt in range(6):
        try:
            resp = requests.request(method, url, headers=headers, params=params, json=json_body, timeout=30)
        except requests.RequestException as e:
            if attempt >= 5:
                raise ClickUpError(f"Network error calling {url}: {e}") from e
            time.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", backoff))
            time.sleep(max(0.5, retry_after))
            backoff *= 2
            continue

        if resp.status_code >= 400:
            try:
                payload = resp.json()
            except Exception:
                payload = resp.text
            raise ClickUpError(f"{method} {url} -> {resp.status_code}: {payload}")
        return resp
    raise ClickUpError(f"Failed after retries: {method} {url}")


def _flatten_task_fields(tk: dict) -> dict:
    """Return a small, scheduler-friendly dict (plain Python types only)."""

    def _ms(v):
        # ClickUp sends milliseconds already. DO NOT multiply by 1000.
        try:
            return int(v or 0)
        except Exception:
            return 0

    time_estimate = _ms(tk.get("time_estimate"))
    time_spent = _ms(tk.get("time_spent") or 0)

    try:
        remaining_minutes = max(0, int((time_estimate - time_spent) / 60000))
    except Exception:
        remaining_minutes = None

    # priority object can be None or {"priority": 1..4}
    prio_num = None
    prio_obj = tk.get("priority")
    if isinstance(prio_obj, dict):
        try:
            prio_num = int(prio_obj.get("priority"))
        except Exception:
            prio_num = None

    due_ms = _ms(tk.get("due_date") or tk.get("due"))

    # collect tag names
    tag_names: list[str] = []
    for tg in (tk.get("tags") or []):
        if isinstance(tg, dict) and "name" in tg:
            tag_names.append(str(tg["name"]).lower())
        elif isinstance(tg, str):
            tag_names.append(tg.lower())

    def _id_from(x, key):
        return x.get(key) if isinstance(x, dict) else None

    return {
        "id": str(tk.get("id") or tk.get("task_id") or ""),
        "name": tk.get("name") or tk.get("title") or "(Untitled)",
        "due_date": due_ms,
        "priority": prio_num,
        "time_estimate": time_estimate,
        "time_spent": time_spent,
        "remaining_minutes": remaining_minutes,
        "status": (tk.get("status") or {}).get("status") if isinstance(tk.get("status"), dict) else tk.get("status"),
        "space": _id_from(tk.get("space") or {}, "id") or tk.get("space_id"),
        "list": _id_from(tk.get("list") or {}, "id") or tk.get("list_id"),
        "folder": _id_from(tk.get("folder") or {}, "id") or tk.get("folder_id"),
        "assignees": [str(a.get("id")) for a in (tk.get("assignees") or []) if isinstance(a, dict) and a.get("id")],
        "tags": tag_names,
        "_raw": tk,
    }


class ClickUpClient:
    """
    Standalone HTTP client used by both FastAPI routes and the scheduler.

    Env:
      CLICKUP_API_KEY (req)
      CLICKUP_TEAM_ID (req)
      CLICKUP_ME_UID (opt; falls back to CLICKUP_USER_ID)
      CLICKUP_EMAIL_LIST_ID (opt)
      CLICKUP_PERSONAL_SPACE_ID (opt)
      CLICKUP_SPACE_ID_CLIENTS (opt)
      CLICKUP_SPACE_ID_MARKETING (opt)
      CLICKUP_SPACE_ID_EFKARISTO (opt)

    Tag→bucket mapping overrides (optional):
      CU_TAG_CLIENT, CU_TAG_SYSTEMS, CU_TAG_MARKETING, CU_TAG_ADMIN, CU_TAG_PERSONAL
    """

    API_BASE = "https://api.clickup.com/api/v2"

    def __init__(self) -> None:
        self.api_key = _env("CLICKUP_API_KEY", required=True)
        self.team_id = _env("CLICKUP_TEAM_ID", required=True)
        self.me_uid = _env("CLICKUP_ME_UID") or _env("CLICKUP_USER_ID")

        # Optional scoping ids
        self.email_list_id = _env("CLICKUP_EMAIL_LIST_ID")
        self.personal_space_id = _env("CLICKUP_PERSONAL_SPACE_ID")
        self.space_clients = _env("CLICKUP_SPACE_ID_CLIENTS")
        self.space_marketing = _env("CLICKUP_SPACE_ID_MARKETING")
        self.space_efkaristo = _env("CLICKUP_SPACE_ID_EFKARISTO")

        # Optional tag names for grouping
        self.tag_client = (_env("CU_TAG_CLIENT") or "client").lower()
        self.tag_systems = (_env("CU_TAG_SYSTEMS") or "systems").lower()
        self.tag_marketing = (_env("CU_TAG_MARKETING") or "marketing").lower()
        self.tag_admin = (_env("CU_TAG_ADMIN") or "admin").lower()
        self.tag_personal = (_env("CU_TAG_PERSONAL") or "personal").lower()

        self.h = _headers(self.api_key)

    # ----------------
    # Low-level list APIs
    # ----------------

    def list_team_tasks(
        self,
        space_ids: list[str] | None = None,
        list_ids: list[str] | None = None,
        include_closed: bool = False,
        page_limit: int = 100,
    ) -> list[dict]:
        url = f"{self.API_BASE}/team/{self.team_id}/task"
        params: dict[str, t.Any] = {
            "page": 0,
            "order_by": "due_date",
            "reverse": False,
            "subtasks": True,
            "include_subtasks": True,
            "page_size": page_limit,
        }
        if list_ids:
            for i, lid in enumerate(list_ids):
                params[f"list_ids[{i}]"] = lid
        if space_ids:
            for i, sid in enumerate(space_ids):
                params[f"space_ids[{i}]"] = sid
        if self.me_uid:
            params["assignees[]"] = [self.me_uid]
        if not include_closed:
            params["statuses[]"] = ["to do", "in progress", "review"]

        tasks: list[dict] = []
        page = 0
        while True:
            params["page"] = page
            resp = _retry_request("GET", url, self.h, params=params)
            data = resp.json() or {}
            items = data.get("tasks") or []
            if not items:
                break
            tasks.extend(items)
            if len(items) < page_limit:
                break
            page += 1
            if page > 50:
                break  # safety
        return tasks

    # ----------------
    # High-level helpers
    # ----------------

    def get_email_tasks(self) -> list[dict]:
        if not self.email_list_id:
            return []
        url = f"{self.API_BASE}/list/{self.email_list_id}/task"
        params: dict[str, t.Any] = {
            "subtasks": True,
            "include_subtasks": True,
            "order_by": "due_date",
            "reverse": False,
        }
        if self.me_uid:
            params["assignees[]"] = [self.me_uid]
        resp = _retry_request("GET", url, self.h, params=params)
        data = resp.json() or {}
        return [_flatten_task_fields(tk) for tk in (data.get("tasks") or [])]

    def get_personal_space_tasks(self) -> list[dict]:
        if not self.personal_space_id:
            return []
        raw = self.list_team_tasks(space_ids=[self.personal_space_id])
        return [_flatten_task_fields(tk) for tk in raw]

    # ----------------
    # Scheduling helpers
    # ----------------

    def refresh_triaged_view_source(self) -> list[dict]:
        """
        Pull fresh tasks for scheduling:
          - include_open_only (default True)
          - optionally include Personal space if CLICKUP_INCLUDE_PERSONAL=1
          - skip Email list if CLICKUP_EMAIL_LIST_ID is set
          - if CLICKUP_ME_UID is set, keep only tasks assigned to me; else include all
        """
        include_personal = (os.getenv("CLICKUP_INCLUDE_PERSONAL", "0").lower() in ("1", "true", "yes"))
        me_uid = (os.getenv("CLICKUP_ME_UID") or os.getenv("CLICKUP_USER_ID") or "").strip()
        email_list_id = str(self.email_list_id) if self.email_list_id else None
        personal_space_id = str(self.personal_space_id) if self.personal_space_id else None

        items = self.list_team_tasks(include_closed=False)
        out: list[dict] = []

        for tk in items:
            list_id = str((tk.get("list") or {}).get("id") or tk.get("list_id") or "")
            space_id = str((tk.get("space") or {}).get("id") or tk.get("space_id") or "")

            # 1) exclude the Email list
            if email_list_id and list_id == email_list_id:
                continue

            # 2) exclude Personal unless explicitly included
            if (not include_personal) and personal_space_id and space_id == personal_space_id:
                continue

            # 3) optional assignee filter
            if me_uid:
                assignees = [str(a.get("id")) for a in (tk.get("assignees") or []) if isinstance(a, dict)]
                if me_uid not in assignees:
                    continue

            out.append(_flatten_task_fields(tk))

        return out

    def fetch_tasks_grouped(self) -> dict[str, list[dict]]:
        """
        Group by tags first; fall back to space ids; final fallback admin.
        Recognized tags (lowercase): client, systems, marketing, admin, personal
        Returns keys the scheduler expects, including 'personal'.
        """
        all_tasks = self.refresh_triaged_view_source()

        grouped: dict[str, list[dict]] = {
            "client_deep_work": [],
            "systems_development": [],
            "marketing_creative": [],
            "admin_processing": [],
            "personal": [],
        }

        def _bucket(tsk: dict) -> str:
            tags = [str(x).lower() for x in (tsk.get("tags") or [])]
            sid = str(tsk.get("space") or "")

            # 1) tag-based
            if self.tag_client in tags:   return "client_deep_work"
            if self.tag_systems in tags:  return "systems_development"
            if self.tag_marketing in tags:return "marketing_creative"
            if self.tag_admin in tags:    return "admin_processing"
            if self.tag_personal in tags: return "personal"

            # 2) space fallbacks
            if self.space_clients and sid == str(self.space_clients):         return "client_deep_work"
            if self.space_marketing and sid == str(self.space_marketing):     return "marketing_creative"
            if self.space_efkaristo and sid == str(self.space_efkaristo):     return "systems_development"
            if self.personal_space_id and sid == str(self.personal_space_id): return "personal"

            # 3) default
            return "admin_processing"

        # ensure remaining_minutes and push into buckets
        for tsk in all_tasks:
            if tsk.get("remaining_minutes") is None:
                est = tsk.get("time_estimate") or 0
                spent = tsk.get("time_spent") or 0
                try:
                    tsk["remaining_minutes"] = max(0, int((int(est) - int(spent)) / 60000))
                except Exception:
                    tsk["remaining_minutes"] = 30
            grouped[_bucket(tsk)].append(tsk)

        def _due_val(d):
            try:
                return int(d.get("due_date") or 0)
            except Exception:
                return 0

        for k, arr in grouped.items():
            arr.sort(key=lambda d: ((d.get("priority") or 99), _due_val(d)))
        return grouped
