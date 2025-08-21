// src/components/PersonalTasks.jsx
import React, { useEffect, useState } from "react";

/* === helpers === */
const emojiMap = [
  { keyword: "Loki", emoji: "🐾" },
  { keyword: "Medications", emoji: "💊" },
  { keyword: "BSL", emoji: "💊" },
  { keyword: "School", emoji: "🎒" },
  { keyword: "Walk", emoji: "🚶‍♂️" },
  { keyword: "Stroll", emoji: "🚶‍♂️" },
  { keyword: "Breakfast", emoji: "🍽️" },
  { keyword: "Pudding", emoji: "🍮" },
];

const getEmoji = (taskTitle = "") => {
  const match = emojiMap.find((e) => taskTitle.includes(e.keyword));
  return match ? match.emoji + " " : "";
};

const getTimeBadge = (taskTitle = "") => {
  const s = taskTitle.toLowerCase();
  if (s.includes("morning")) return "☀️";
  if (s.includes("evening")) return "🌙";
  return null;
};

// ClickUp due_date can be a ms timestamp (string/number) or ISO string
const parseClickUpDue = (t) => {
  if (!t) return null;
  const raw = t.due_date ?? t.dueDate;
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isNaN(n) && String(raw).length >= 10) {
    // ms epoch or seconds; assume ms if >= 10 digits
    const ms = String(raw).length >= 13 ? n : n * 1000;
    return new Date(ms);
  }
  const d = new Date(raw);
  return isNaN(d.getTime()) ? null : d;
};

const isOverdue = (task) => {
  const d = parseClickUpDue(task);
  return d ? d.getTime() < Date.now() : false;
};

const formatDueDate = (task) => {
  const d = parseClickUpDue(task);
  return d ? d.toLocaleDateString() : "";
};

const formatDueTime = (task) => {
  const d = parseClickUpDue(task);
  return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
};

/* === component === */
export default function PersonalTasks({ tasks = [], onCompleteTask, onRefresh }) {
  const [updatedTasks, setUpdatedTasks] = useState(tasks);
  const [isRefreshing, setIsRefreshing] = useState(false);
  // remember what we hid locally to avoid flicker if props are stale
  const [locallyCompletedIds, setLocallyCompletedIds] = useState(() => new Set());

  // Complete a ClickUp task + optimistic remove
  async function completeClickUpTask(task) {
    const idStr = String(task.id);
    try {
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
        console.error("❌ Failed to complete ClickUp task:", data);
        return;
      }
      // Optimistically remove from UI
      setUpdatedTasks((prev) => prev.filter((t) => String(t.id) !== idStr));
      // Remember removal so it won't flash back in from parent props
      setLocallyCompletedIds((prev) => {
        const next = new Set(prev);
        next.add(idStr);
        return next;
      });
      if (typeof onCompleteTask === "function") onCompleteTask(idStr);
    } catch (err) {
      console.error("❌ Failed to complete ClickUp task:", err);
    }
  }

  // Manual refresh (Personal → ClickUp via triage)
  const refreshTasks = async () => {
    setIsRefreshing(true);
    try {
      if (typeof onRefresh === "function") {
        await onRefresh(); // parent will re-supply tasks prop
        return;
      }
      // Fallback: fetch triaged-tasks and pull personal slice
      const res = await fetch("http://localhost:3333/api/triaged-tasks");
      const data = await res.json();
      const list = Array.isArray(data?.personal) ? data.personal : [];
      setUpdatedTasks(list.filter((t) => !locallyCompletedIds.has(String(t.id))));
    } catch (err) {
      console.error("❌ Failed to refresh personal tasks:", err);
    } finally {
      setIsRefreshing(false);
    }
  };

  // Sync from parent when prop changes, but keep locally-completed hidden
  useEffect(() => {
    const filtered = (tasks || []).filter((t) => !locallyCompletedIds.has(String(t.id)));
    setUpdatedTasks((prev) => {
      const sameLen = prev.length === filtered.length;
      const sameIds = sameLen && prev.every((p, i) => String(p.id) === String(filtered[i]?.id));
      return sameIds ? prev : filtered;
    });
  }, [tasks, locallyCompletedIds]);

  return (
    <section className="w-full" id="personal-tasks-anchor">
      <div className="bg-purple-50 rounded-xl shadow p-4">
        {/* Refresh */}
        <div className="flex justify-between items-center mb-4">
          <button
            onClick={refreshTasks}
            disabled={isRefreshing}
            className={`text-sm px-3 py-1 rounded ${
              isRefreshing
                ? "bg-gray-200 text-gray-500 cursor-wait"
                : "text-purple-700 bg-purple-100 hover:bg-purple-200"
            }`}
          >
            {isRefreshing ? "Refreshing..." : "🔄 Refresh tasks"}
          </button>
        </div>

        {/* Scrollable task list */}
        {updatedTasks?.length ? (
          <div className="max-h-72 overflow-y-auto pr-2">
            <ul className="space-y-4">
              {updatedTasks.map((task) => {
                const title = task.name || task.content || "[No Title]";
                const emoji = getEmoji(title);
                const timeBadge = getTimeBadge(title);
                const overdue = isOverdue(task);
                const dueDateStr = formatDueDate(task);
                const dueTimeStr = formatDueTime(task);
                const taskUrl = task.url || `https://app.clickup.com/t/${task.id}`;

                return (
                  <li
                    key={task.id}
                    className={`bg-white rounded-lg shadow p-4 ${
                      overdue ? "border-l-4 border-red-500" : ""
                    }`}
                  >
                    <div>
                      <div className="text-blue-700 font-semibold hover:underline">
                        <a href={taskUrl} target="_blank" rel="noopener noreferrer">
                          {emoji}
                          {title}
                        </a>
                        {timeBadge && <span> {timeBadge}</span>}
                      </div>

                      {parseClickUpDue(task) && (
                        <div className="text-sm text-gray-500 flex items-center gap-3 mt-1">
                          {dueDateStr && <span>📅 Due {dueDateStr}</span>}
                          {dueTimeStr && <span>🕒 {dueTimeStr}</span>}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 mt-3">
                      <button
                        onClick={async () => {
                          await completeClickUpTask(task);
                        }}
                        disabled={locallyCompletedIds.has(String(task.id))}
                        className={`bg-green-100 text-green-700 hover:bg-green-200 px-2 py-1 rounded text-xs ${
                          locallyCompletedIds.has(String(task.id))
                            ? "cursor-not-allowed bg-gray-300"
                            : ""
                        }`}
                      >
                        ✅ Complete
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-gray-500">No personal tasks available.</p>
        )}
      </div>
    </section>
  );
}
