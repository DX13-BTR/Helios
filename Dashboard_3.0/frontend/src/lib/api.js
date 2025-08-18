// lib/api.js

export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:3333";

async function handle(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

export async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`);
  return handle(res);
}

export async function postJSON(path, body, init = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    body: JSON.stringify(body),
    ...init,
  });
  return handle(res);
}

export async function postForBlob(path, body, init = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
    body: JSON.stringify(body),
    ...init,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
}

/* ------------------------- Helios Task APIs ------------------------- */

// Fixed-date tasks (uses backend COALESCE fallback so fixed_date is always set)
export async function fetchFixedDateTasks() {
  return getJSON("/api/fixed-date-tasks");
}

// (Optional) Upsert task metadata for a single task_id
export async function setTaskMeta(taskId, payload) {
  return postJSON(`/api/task-meta/${encodeURIComponent(taskId)}/set`, payload);
}
