// src/components/TaskListPanel.jsx
import { useEffect, useState } from "react";
import TaskRow from "./TaskRow";

// === helper: normalize Todoist task for <TaskRow> ===
function mapTodoistToTaskRow(t) {
  const title = t.content || t.title || "Untitled";

  // Todoist due.date can be "YYYY-MM-DD" (all-day) or ISO; convert to ISO if possible
  let dueAt = null;
  if (t.due?.date) {
    const d = new Date(t.due.date);
    if (!isNaN(d.getTime())) dueAt = d.toISOString();
  }

  const estimateMins = typeof t.duration?.amount === "number" ? t.duration.amount : null;

  // Todoist priority: 4 highest → map to labels
  let priority = "low";
  if (t.priority >= 4) priority = "urgent";
  else if (t.priority === 3) priority = "high";
  else if (t.priority === 2) priority = "medium";

  return {
    id: t.id,
    title,
    dueAt,
    estimateMins,
    priority,
    assignee: t.assignee?.name || (t.responsible_uid ? `UID:${t.responsible_uid}` : null),
    listName: t.project?.name || (t.project_id ? `Project ${t.project_id}` : null),
    tags: Array.isArray(t.labels) ? t.labels : [],
    completed: Boolean(t.is_completed),
  };
}

// NEW: lightweight detector to show a small "Finance" chip (optional)
function isFinanceTask(t) {
  const s = (t.title || t.name || t.content || "").toLowerCase();
  return (
    s.includes("invoice") ||
    s.includes("reconcile") ||
    s.includes("payment") ||
    s.includes("payroll") ||
    s.includes("bill") ||
    s.includes("chase") ||
    s.includes("statement") ||
    s.includes("bank")
  );
}

export default function TaskListPanel({ tasks = [], panelType = "", onRefresh, financePriority = false }) {
  const [projects, setProjects] = useState([]);
  const [clients, setClients] = useState([]);
  const [selectedProjects, setSelectedProjects] = useState(() => {
    const saved = localStorage.getItem("selectedProjects");
    return saved ? JSON.parse(saved) : {};
  });
  const [activeTimer, setActiveTimer] = useState(null);
  const [elapsed, setElapsed] = useState("00:00:00");
  const [visibleTasks, setVisibleTasks] = useState(tasks);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const hasActiveTimer = Boolean(activeTimer?.description && activeTimer?.start);

  function isTaskActive(task) {
    if (!hasActiveTimer) return false;
    const taskName = (task.name || task.content || "").trim().toLowerCase();
    const timerDesc = (activeTimer.description || "").trim().toLowerCase();
    return taskName && timerDesc === taskName;
  }

  useEffect(() => {
    fetchProjects();
    fetchClients();
    fetchCurrentTimer();
    const interval = setInterval(fetchCurrentTimer, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
  // Sort only for Email panel here
  if (panelType === "email") {
    const sorted = [...tasks].sort((a, b) => {
      // handle number (epoch) or string dates; tasks without due_date go last
      const aHas = a?.due_date != null;
      const bHas = b?.due_date != null;
      if (!aHas && !bHas) return 0;
      if (!aHas) return 1;
      if (!bHas) return -1;

      const aTime = !isNaN(Number(a.due_date))
        ? Number(a.due_date)
        : new Date(a.due_date).getTime();
      const bTime = !isNaN(Number(b.due_date))
        ? Number(b.due_date)
        : new Date(b.due_date).getTime();

      return aTime - bTime; // earliest first (oldest → newest)
    });
    setVisibleTasks(sorted);
  } else {
    setVisibleTasks(tasks);
  }
}, [tasks, panelType]);


  useEffect(() => {
    localStorage.setItem("selectedProjects", JSON.stringify(selectedProjects));
  }, [selectedProjects]);

  async function fetchProjects() {
    try {
      const res = await fetch("http://localhost:3333/api/toggl/projects");
      const data = await res.json();
      setProjects(data.projects || []);
    } catch (err) {
      console.error("❌ Failed to fetch Toggl projects:", err);
    }
  }

  async function fetchClients() {
    try {
      const res = await fetch("http://localhost:3333/api/toggl/clients");
      const data = await res.json();
      setClients(data.clients || []);
    } catch (err) {
      console.error("❌ Failed to fetch Toggl clients:", err);
    }
  }

  async function fetchCurrentTimer() {
    try {
      const res = await fetch("http://localhost:3333/api/toggl/current-time-entry");
      const data = await res.json();
      if (data?.description && data?.start) {
        setActiveTimer(data);
      } else {
        setActiveTimer(null);
        setElapsed("00:00:00");
      }
    } catch (err) {
      console.error("❌ Failed to fetch current timer:", err);
    }
  }

  useEffect(() => {
    if (!activeTimer?.start) return;
    const start = new Date(activeTimer.start).getTime();
    const tick = () => {
      const diff = Math.floor((Date.now() - start) / 1000);
      updateElapsed(diff);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [activeTimer]);

  function updateElapsed(seconds) {
    const hrs = String(Math.floor(seconds / 3600)).padStart(2, "0");
    const mins = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
    const secs = String(seconds % 60).padStart(2, "0");
    setElapsed(`${hrs}:${mins}:${secs}`);
  }

  // Route completion by panel source:
  // - urgent (Primary) → Todoist close
  // - doNext/email/personal → ClickUp update-status complete
  async function completeTask(task) {
    const idStr = String(task.id);
    try {
      if (panelType === "urgent") {
        const res = await fetch(
          `http://localhost:3333/api/todoist/tasks/${encodeURIComponent(idStr)}/close`,
          { method: "POST" }
        );
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          console.error("❌ Todoist close failed:", data);
          return;
        }
      } else {
        const res = await fetch(
          `http://localhost:3333/api/tasks/${encodeURIComponent(idStr)}/update-status`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: "complete" }),
          }
        );
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          console.error("❌ ClickUp complete failed:", data);
          return;
        }
      }

      // Optimistic remove & optional refresh
      setVisibleTasks((prev) => prev.filter((t) => String(t.id) !== idStr));
      if ((panelType === "email" || panelType === "personal" || panelType === "doNext") && onRefresh) {
        try { await onRefresh(); } catch {}
      }
    } catch (err) {
      console.error("❌ Failed to complete task:", err);
    }
  }

  async function updateTaskStatus(taskId, status) {
    // Keep using generic endpoint for non-complete statuses
    if (status === "complete") {
      const task = visibleTasks.find((t) => String(t.id) === String(taskId));
      if (task) await completeTask(task);
      return;
    }

    try {
      await fetch(`http://localhost:3333/api/tasks/${taskId}/update-status`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });

      if (status === "in progress") {
        // no removal; timer start handles highlighting
      }
    } catch (err) {
      console.error("❌ Failed to update task status:", err);
    }
  }

  async function startTimer(taskId, taskName) {
    const projectId = selectedProjects[taskId];
    if (!projectId) return;

    const project = projects.find((p) => p.id === parseInt(projectId));
    const clientId = project?.client_id;

    try {
      await fetch("http://localhost:3333/api/toggl/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          description: taskName,
          projectId: parseInt(projectId),
          clientId,
        }),
      });

      await updateTaskStatus(taskId, "in progress");
      fetchCurrentTimer();
    } catch (err) {
      console.error("❌ Failed to start timer:", err);
    }
  }

  async function stopTimer() {
    if (!activeTimer?.id) return;

    try {
      await fetch("http://localhost:3333/api/toggl/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: activeTimer.id }),
      });
      fetchCurrentTimer();
    } catch (err) {
      console.error("❌ Failed to stop timer:", err);
    }
  }

  function getClientName(clientId) {
    return clients.find((c) => c.id === clientId)?.name || "Unknown";
  }

  if (!visibleTasks || visibleTasks.length === 0) {
    return <p className="text-sm text-gray-500">No tasks found.</p>;
  }

  return (
    <div className="max-h-[500px] overflow-y-auto pr-2">
      {onRefresh && (
        <button
          onClick={async () => {
            setIsRefreshing(true);
            try {
              await onRefresh();
            } catch (err) {
              console.error("❌ Panel refresh error:", err);
            } finally {
              setIsRefreshing(false);
            }
          }}
          className={`mb-2 px-3 py-1 rounded text-sm flex items-center gap-2 ${
            isRefreshing
              ? "bg-gray-200 text-gray-500 cursor-wait"
              : "bg-gray-100 text-gray-800 hover:bg-gray-200"
          }`}
        >
          {isRefreshing ? (
            <>
              <svg
                className="animate-spin h-4 w-4 text-purple-700"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"
                />
              </svg>
              Refreshing...
            </>
          ) : (
            <>🔄 Refresh</>
          )}
        </button>
      )}

      <ul className="space-y-4">
        {visibleTasks.map((task) => {
          const taskTitle = task.content || task.name || "Untitled";
          const taskUrl = task.url || `https://app.clickup.com/t/${task.id}`;
          const showFinanceChip = financePriority && isFinanceTask(task);

          return (
            <li
              key={task.id}
              className={`bg-white rounded-lg shadow p-4 relative ${
                isTaskActive(task) ? "border-l-4 border-purple-500" : ""
              }`}
            >
              {typeof task.score === "number" && (
                <div className="absolute top-2 right-2 bg-purple-100 text-purple-700 text-xs font-bold px-2 py-1 rounded-full">
                  {Math.round(task.score)}
                </div>
              )}

              {/* Header: TaskRow only for Todoist/Primary; otherwise keep your link */}
              {panelType === "urgent" ? (
                <TaskRow
                  task={mapTodoistToTaskRow(task)}
                  onOpen={() =>
                    window.open(task.url || "", "_blank", "noopener,noreferrer")
                  }
                  onQuickAction={() => {}}
                  className="mb-2"
                />
              ) : (
                <div className="flex items-center gap-2 flex-wrap">
                  <a
                    href={taskUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-700 font-semibold hover:underline"
                  >
                    {taskTitle}
                  </a>
                  {showFinanceChip && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full border border-emerald-300 bg-emerald-50 text-emerald-700">
                      £ Finance priority
                    </span>
                  )}
                </div>
              )}

              {task.agent_reason && (
                <div className="text-xs text-gray-500 italic mt-1">
                  🧑‍🦱 {task.agent_reason}
                </div>
              )}

              <div className="mt-2 flex flex-wrap gap-2 items-center text-sm text-gray-600">
                {task.due_date &&
                  (() => {
                    let due;
                    if (!isNaN(Number(task.due_date))) {
                      due = new Date(Number(task.due_date));
                    } else {
                      due = new Date(task.due_date);
                    }

                    const date = due.toLocaleDateString();
                    const time = due.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    });

                    return <span>🗓 {date} at {time}</span>;
                  })()}

                {panelType === "personal" &&
                  task.due_date &&
                  (() => {
                    let due;
                    if (!isNaN(Number(task.due_date))) {
                      due = new Date(Number(task.due_date));
                    } else {
                      due = new Date(task.due_date);
                    }
                    return due < new Date();
                  })() && (
                    <span className="ml-2 bg-red-100 text-red-700 text-xs font-semibold px-2 py-1 rounded">
                      Overdue
                    </span>
                  )}

                {task.status?.status && (
                  <span className="text-xs bg-gray-100 px-2 py-1 rounded">
                    {task.status.status}
                  </span>
                )}

                {isTaskActive(task) && (
                  <span className="text-purple-700 font-semibold">{elapsed}</span>
                )}
              </div>

              <div className="mt-3 flex flex-col sm:flex-row sm:items-center sm:gap-2 gap-2">
                <select
                  value={selectedProjects[task.id] || ""}
                  onChange={(e) =>
                    setSelectedProjects({
                      ...selectedProjects,
                      [task.id]: e.target.value,
                    })
                  }
                  className="border px-2 py-1 rounded max-w-[300px] w-full sm:w-auto"
                >
                  <option value="">Select project</option>
                  {projects
                    .sort((a, b) =>
                      `${getClientName(a.client_id)} – ${a.name}`.localeCompare(
                        `${getClientName(b.client_id)} – ${b.name}`
                      )
                    )
                    .map((project) => (
                      <option key={project.id} value={project.id}>
                        {getClientName(project.client_id)} – {project.name}
                      </option>
                    ))}
                </select>

                <div className="flex gap-2">
                  {isTaskActive(task) ? (
                    <button
                      onClick={stopTimer}
                      className="bg-yellow-100 text-yellow-800 px-3 py-1 rounded text-sm"
                    >
                      ⏹ Stop
                    </button>
                  ) : (
                    <button
                      onClick={() =>
                        startTimer(task.id, task.name || task.content)
                      }
                      className="bg-green-100 text-green-700 px-3 py-1 rounded text-sm"
                      disabled={!selectedProjects[task.id]}
                    >
                      ▶ Start
                    </button>
                  )}
                  <button
                    onClick={() => completeTask(task)}
                    className="bg-blue-100 text-blue-700 px-3 py-1 rounded text-sm"
                  >
                    ✅ Complete
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
