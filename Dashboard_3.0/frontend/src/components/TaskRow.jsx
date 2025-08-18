// src/components/TaskRow.jsx
import React from "react";
import clsx from "clsx";

/**
 * TaskRow
 * - Compact, single-line row with stable regions.
 * - Props:
 *   task: {
 *     id, title, dueAt (ISO), estimateMins, priority, assignee, listName, tags: string[], completed
 *   }
 *   onToggle(taskId), onOpen(taskId), onQuickAction(taskId, action)
 *   className
 */
export default function TaskRow({ task, onToggle, onOpen, onQuickAction, className }) {
  const {
    id, title, dueAt, estimateMins, priority, assignee, listName, tags = [], completed,
  } = task || {};

  const due = dueAt ? new Date(dueAt) : null;
  const isOverdue = due && due.getTime() < Date.now();
  const dueLabel = due ? due.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" }) : null;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen?.(id)}
      onKeyDown={(e) => { if (e.key === "Enter") onOpen?.(id); }}
      className={clsx(
        "group grid grid-cols-[auto,1fr,auto] items-center gap-3 px-2 py-1.5 rounded-md",
        "hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-indigo-500",
        className
      )}
    >
      {/* left: checkbox */}
      <input
        type="checkbox"
        checked={!!completed}
        onChange={(e) => { e.stopPropagation(); onToggle?.(id); }}
        onClick={(e) => e.stopPropagation()}
        className="h-4 w-4 accent-indigo-600"
        aria-label="Complete task"
      />

      {/* middle: title + tags + badges */}
      <div className="min-w-0 flex items-center">
        <div className={clsx("truncate", completed && "line-through text-gray-400")}>
          {title}
        </div>

        {/* inline tags (lightweight, no wrap) */}
        {tags.length > 0 && (
          <div className="ml-2 hidden sm:flex gap-1 overflow-hidden">
            {tags.slice(0, 3).map((t) => (
              <span key={t} className="shrink-0 text-[11px] px-1 py-0.5 bg-gray-100 rounded">
                {t}
              </span>
            ))}
            {tags.length > 3 && <span className="text-[11px] text-gray-500">+{tags.length - 3}</span>}
          </div>
        )}

        {/* badges */}
        <div className="ml-3 flex items-center gap-2 shrink-0">
          {due && (
            <span
              className={clsx(
                "text-[11px] px-1.5 py-0.5 rounded border",
                isOverdue ? "border-red-200 text-red-700 bg-red-50" : "border-gray-200 text-gray-700 bg-white"
              )}
              title={due.toLocaleString()}
            >
              {isOverdue ? "Overdue • " : ""}{dueLabel}
            </span>
          )}
          {typeof estimateMins === "number" && estimateMins > 0 && (
            <span className="text-[11px] px-1.5 py-0.5 rounded border border-gray-200 text-gray-700 bg-white" title="Estimated duration">
              {Math.round(estimateMins)}m
            </span>
          )}
          {priority && (
            <span
              className={clsx(
                "text-[11px] px-1.5 py-0.5 rounded border",
                priority === "urgent" ? "border-orange-300 bg-orange-50 text-orange-800"
                  : priority === "high" ? "border-amber-300 bg-amber-50 text-amber-800"
                  : "border-gray-200 bg-white text-gray-700"
              )}
            >
              {priority}
            </span>
          )}
        </div>
      </div>

      {/* right: context + actions (icon buttons shown on hover/focus) */}
      <div className="flex items-center gap-2 shrink-0">
        {(assignee || listName) && (
          <div className="hidden md:flex items-center gap-2 text-xs text-gray-500">
            {assignee && <span className="truncate max-w-[100px]">{assignee}</span>}
            {assignee && listName && <span>•</span>}
            {listName && <span className="truncate max-w-[120px]">{listName}</span>}
          </div>
        )}
        <div className="opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity flex gap-1">
          <IconBtn label="Edit" onClick={(e) => { e.stopPropagation(); onQuickAction?.(id, "edit"); }} />
          <IconBtn label="Schedule" onClick={(e) => { e.stopPropagation(); onQuickAction?.(id, "schedule"); }} />
          <IconBtn label="Delete" onClick={(e) => { e.stopPropagation(); onQuickAction?.(id, "delete"); }} />
        </div>
      </div>
    </div>
  );
}

function IconBtn({ label, onClick }) {
  return (
    <button
      aria-label={label}
      title={label}
      onClick={onClick}
      className="p-1.5 rounded hover:bg-gray-100 active:bg-gray-200"
    >
      {/* simple dot icon; swap with your icon set */}
      <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="2" />
      </svg>
    </button>
  );
}
