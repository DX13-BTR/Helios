import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, CheckCircle2, Loader2, CalendarDays, X, AlertTriangle, Clock, ChevronRight, Filter } from "lucide-react";

/**
 * HeliosTodayView.tsx
 *
 * Drop into your Vite React app (e.g., src/components/HeliosTodayView.tsx), then render <HeliosTodayView />.
 *
 * Assumptions / endpoints (override with props if your API differs):
 * - GET  /api/tasks/search?due=today&include_overdue=1  -> Task[]
 * - POST /api/tasks            { title, client_id, due_date, priority } -> Task
 * - PATCH /api/tasks/:id       { status: "completed" } -> Task
 * - GET  /api/clients          -> { id, name }[]  (used for dropdown)
 *
 * You can change routes via component props.
 * Uses Tailwind CSS; mobile-first; keyboard-friendly.
 */

// ---- Types ----
export type Priority = "low" | "normal" | "high" | "urgent";
export type TaskStatus = "open" | "in_progress" | "completed";

export interface Task {
  id: string | number;
  title: string;
  client_id?: string | number | null;
  client_name?: string | null;
  due_date?: string | null; // ISO (date or datetime)
  status: TaskStatus;
  priority?: Priority;
  // Optional extra fields we display if present
  created_at?: string;
  updated_at?: string;
  source_label?: string; // for email-sourced tasks
}

export interface Client { id: string | number; name: string }

// ---- Helpers ----
const API_BASE = import.meta.env.VITE_HELIOS_API ?? "http://127.0.0.1:3333";

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path.startsWith("http") ? path : `${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status} on ${path}: ${text}`);
  }
  return res.json();
}

function isoDateOnly(d: Date): string {
  // yyyy-mm-dd
  return d.toISOString().slice(0, 10);
}

// ---- QuickAddTask ----
interface QuickAddTaskProps {
  onCreated(task: Task): void;
  routes?: {
    createTask?: string; // default: /api/tasks
    clients?: string;    // default: /api/clients
  };
}

function classNames(...xs: (string | false | undefined)[]) { return xs.filter(Boolean).join(" "); }

const priorities: {label: string; value: Priority}[] = [
  { label: "Low", value: "low" },
  { label: "Normal", value: "normal" },
  { label: "High", value: "high" },
  { label: "Urgent", value: "urgent" },
];

export function QuickAddTask({ onCreated, routes }: QuickAddTaskProps) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [clientId, setClientId] = useState<string | number | "">("");
  const [dueDate, setDueDate] = useState<string>(isoDateOnly(new Date()));
  const [priority, setPriority] = useState<Priority>("normal");
  const [submitting, setSubmitting] = useState(false);
  const [clients, setClients] = useState<Client[]>([]);
  const [loadingClients, setLoadingClients] = useState(false);
  const [error, setError] = useState<string>("");
  const inputRef = useRef<HTMLInputElement>(null);

  const clientsPath = routes?.clients ?? "/api/clients";
  const createPath = routes?.createTask ?? "/api/tasks";

  useEffect(() => {
    if (!open) return;
    setLoadingClients(true);
    http<Client[]>(clientsPath)
      .then((xs) => setClients(xs))
      .catch((e) => setError(e.message))
      .finally(() => setLoadingClients(false));
  }, [open, clientsPath]);

  useEffect(() => {
    if (open) {
      const t = setTimeout(() => inputRef.current?.focus(), 50);
      return () => clearTimeout(t);
    }
  }, [open]);

  async function submit() {
    if (!title.trim()) { setError("Title is required"); inputRef.current?.focus(); return; }
    setSubmitting(true);
    setError("");
    try {
      const payload = { title: title.trim(), client_id: clientId || null, due_date: dueDate || null, priority };
      const task = await http<Task>(createPath, { method: "POST", body: JSON.stringify(payload) });
      onCreated(task);
      // Reset but keep drawer open for batching
      setTitle("");
      setClientId("");
      setDueDate(isoDateOnly(new Date()));
      setPriority("normal");
      inputRef.current?.focus();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
  }

  return (
    <>
      <button
        className="fixed bottom-6 right-6 z-40 shadow-lg rounded-full p-4 bg-black/90 text-white hover:bg-black focus:outline-none"
        onClick={() => setOpen(true)}
        aria-label="Quick add task"
      >
        <Plus className="w-6 h-6" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/40"
            onClick={() => setOpen(false)}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 260, damping: 30 }}
            className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-white shadow-2xl p-5 flex flex-col gap-4 overflow-y-auto"
            role="dialog"
            aria-modal
          >
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">Quick Add Task</h2>
              <button onClick={() => setOpen(false)} aria-label="Close" className="p-2 hover:bg-neutral-100 rounded-xl">
                <X className="w-5 h-5" />
              </button>
            </div>

            {error && (
              <div className="text-red-700 bg-red-50 border border-red-200 rounded-xl p-3 text-sm flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <label className="text-sm font-medium">Title</label>
            <input
              ref={inputRef}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={onKey}
              placeholder="What needs doing?"
              className="w-full rounded-2xl border border-neutral-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-black"
            />

            <label className="text-sm font-medium">Client</label>
            <select
              value={String(clientId)}
              onChange={(e) => setClientId(e.target.value || "")}
              className="w-full rounded-2xl border border-neutral-300 px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-black"
            >
              <option value="">— None —</option>
              {loadingClients ? <option>Loading…</option> : clients.map(c => (
                <option key={c.id} value={String(c.id)}>{c.name}</option>
              ))}
            </select>

            <label className="text-sm font-medium">Due date</label>
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="w-full rounded-2xl border border-neutral-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-black"
            />

            <label className="text-sm font-medium">Priority</label>
            <div className="grid grid-cols-4 gap-2">
              {priorities.map(p => (
                <button
                  key={p.value}
                  onClick={() => setPriority(p.value)}
                  className={classNames(
                    "rounded-2xl border px-3 py-2 text-sm",
                    priority === p.value ? "border-black bg-black text-white" : "border-neutral-300 hover:border-black"
                  )}
                >{p.label}</button>
              ))}
            </div>

            <div className="mt-2 flex gap-2">
              <button
                onClick={submit}
                disabled={submitting}
                className="flex items-center gap-2 rounded-2xl px-4 py-2 bg-black text-white hover:bg-black/90 disabled:opacity-50"
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin"/> : <Plus className="w-4 h-4"/>}
                <span>Add task</span>
              </button>
              <button onClick={() => setOpen(false)} className="rounded-2xl px-4 py-2 border border-neutral-300 hover:border-black">Close</button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

// ---- TodayView ----
interface TodayViewProps {
  routes?: {
    search?: string;      // default: /api/tasks/search?due=today&include_overdue=1
    patchTask?: (id: Task["id"]) => string; // default: (id)=>`/api/tasks/${id}`
  };
}

function byPriority(a?: Priority, b?: Priority): number {
  const rank: Record<Priority, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
  return (rank[a || "normal"] ?? 9) - (rank[b || "normal"] ?? 9);
}

export default function HeliosTodayView({ routes }: TodayViewProps) {
  const searchPath = routes?.search ?? "/api/tasks/search?due=today&include_overdue=1";
  const patchPath = (id: Task["id"]) => routes?.patchTask?.(id) ?? `/api/tasks/${id}`;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [filter, setFilter] = useState<"all"|"overdue"|"today">("all");

  async function load() {
    setLoading(true); setError("");
    try {
      const xs = await http<Task[]>(searchPath, { method: "GET" });
      setTasks(xs);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [searchPath]);

  // Derived buckets
  const now = new Date();
  const todayISO = isoDateOnly(now);

  function isOverdue(t: Task) {
    if (!t.due_date) return false;
    return t.status !== "completed" && t.due_date < todayISO;
  }

  function isDueToday(t: Task) {
    if (!t.due_date) return false;
    return t.status !== "completed" && t.due_date === todayISO;
  }

  const visible = useMemo(() => {
    const base = tasks.filter(t => t.status !== "completed");
    let xs = base;
    if (filter === "overdue") xs = base.filter(isOverdue);
    if (filter === "today") xs = base.filter(isDueToday);
    return xs.sort((a,b) => byPriority(a.priority, b.priority));
  }, [tasks, filter]);

  async function completeTask(id: Task["id"]) {
    // Optimistic UI
    const prev = tasks;
    setTasks(prev => prev.map(t => t.id === id ? { ...t, status: "completed" } : t));
    try {
      await http<Task>(patchPath(id), { method: "PATCH", body: JSON.stringify({ status: "completed" }) });
    } catch (e) {
      // revert on error
      setTasks(prev);
      alert((e as Error).message);
    }
  }

  return (
    <div className="mx-auto max-w-2xl p-4 sm:p-6">
      <header className="flex items-center gap-2 mb-4">
        <CalendarDays className="w-5 h-5" />
        <h1 className="text-2xl font-semibold">Today</h1>
      </header>

      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm">
          <button onClick={() => setFilter("all")} className={classNames("px-3 py-1.5 rounded-full border", filter==="all"?"bg-black text-white border-black":"border-neutral-300 hover:border-black")}>All</button>
          <button onClick={() => setFilter("today")} className={classNames("px-3 py-1.5 rounded-full border", filter==="today"?"bg-black text-white border-black":"border-neutral-300 hover:border-black")}>Due Today</button>
          <button onClick={() => setFilter("overdue")} className={classNames("px-3 py-1.5 rounded-full border", filter==="overdue"?"bg-black text-white border-black":"border-neutral-300 hover:border-black")}>Overdue</button>
        </div>
        <button onClick={load} className="text-sm inline-flex items-center gap-1 px-3 py-1.5 rounded-full border border-neutral-300 hover:border-black">
          <Loader2 className="w-4 h-4 animate-spin mr-1" /> Refresh
        </button>
      </div>

      {error && (
        <div className="text-red-700 bg-red-50 border border-red-200 rounded-xl p-3 text-sm flex items-start gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-neutral-600"><Loader2 className="w-4 h-4 animate-spin"/> Loading…</div>
      ) : (
        <ul className="flex flex-col gap-2">
          {visible.map(t => (
            <li key={t.id} className={classNames("rounded-2xl border p-3 bg-white", isOverdue(t) && "border-red-300 bg-red-50")}> 
              <div className="flex items-start gap-3">
                <button
                  onClick={() => completeTask(t.id)}
                  className="mt-0.5 p-1 rounded-full border border-neutral-300 hover:border-black"
                  aria-label="Mark complete"
                >
                  <CheckCircle2 className="w-5 h-5" />
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate font-medium">{t.title}</div>
                    {t.priority && (
                      <span className={classNames("text-xs px-2 py-0.5 rounded-full border", t.priority==="urgent"||t.priority==="high"?"border-black":"border-neutral-300")}>{t.priority}</span>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-neutral-600 flex items-center gap-2">
                    {t.client_name && <span className="truncate">{t.client_name}</span>}
                    {t.due_date && (
                      <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3"/> {t.due_date}</span>
                    )}
                    {t.source_label && (
                      <span className="inline-flex items-center gap-1"><ChevronRight className="w-3 h-3"/> {t.source_label}</span>
                    )}
                  </div>
                </div>
              </div>
            </li>
          ))}
          {visible.length === 0 && (
            <li className="rounded-2xl border border-dashed p-6 text-center text-neutral-500">
              Nothing due right now. Add something below.
            </li>
          )}
        </ul>
      )}

      {/* FAB / Drawer for quick add */}
      <QuickAddTask onCreated={(t) => setTasks(prev => [t, ...prev])} />
    </div>
  );
}
