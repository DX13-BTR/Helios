import { useEffect, useMemo, useState } from "react";
// Local UI primitives (adjust paths if your files live elsewhere)
import Card from "./Card.jsx";
import Button from "./Button.jsx";

/** ---------- Types (keep minimal and permissive for mixed TS/JS codebases) ---------- */

type ISODate = string;      // e.g., "2025-08-21"
type ISODateTime = string;  // e.g., "2025-08-21T09:30:00.000Z"

type Task = {
  id: string;
  title: string;
  due_date?: ISODate | null;
  status?: "open" | "completed" | string;
  priority?: string | number | null;
  source?: string;
};

type TodayBlock = {
  id: string;
  label: string;
  context?: string;
  start: ISODateTime;
  end: ISODateTime;
  calendar_url?: string | null;
  tasks: Task[]; // currently empty; kept for future in-block task linking
};

type TodayPayload = {
  date: ISODate;
  timezone: string;
  blocks: TodayBlock[];
  // unallocated?: Task[]  // not used for now
};

type TriagedTaskRaw = {
  id: string;
  name: string;
  due_date?: number | string | null;
  priority?: any;
  status?: string;
};

type TriagedResponse = {
  doNext: TriagedTaskRaw[];
  email: TriagedTaskRaw[];
  personal: TriagedTaskRaw[];
};

type Routes = {
  /** Schedule blocks for today */
  schedule: string; // GET
  /** Triaged tasks from which we derive "today + overdue" */
  triagedTasks: string; // GET
  /** Build URL for task status update */
  updateStatus: (id: string) => string; // POST {status}
};

type Props = {
  routes?: Partial<Routes>;
  title?: string;
};

/** ---------- Route defaults using existing backend ---------- */

const defaultRoutes: Routes = {
  schedule: "/api/schedule/today",
  triagedTasks: "/api/triaged-tasks",
  updateStatus: (id: string) => `/api/tasks/${id}/update-status`,
};

/** ---------- Small utilities ---------- */

async function http<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(input, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    credentials: "include",
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText}${text ? ` – ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

// Accept numbers (secs/ms), strings, or ISO; normalize to YYYY-MM-DD
function toISODateOnly(input: any): ISODate | null {
  if (input == null) return null;
  const asNum = Number(input);
  if (!Number.isNaN(asNum) && asNum > 0) {
    // Heuristic: treat <1e12 as seconds, otherwise ms
    const ms = asNum < 1e12 ? asNum * 1000 : asNum;
    return new Date(ms).toISOString().slice(0, 10);
  }
  const s = String(input);
  // Accept already-ISO or YYYY-MM-DD-like
  if (s.includes("T") || s.includes("-")) return s.slice(0, 10);
  return null;
}

function fmtTimeRange(startISO: ISODateTime, endISO: ISODateTime): string {
  const s = new Date(startISO);
  const e = new Date(endISO);
  const opts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };
  return `${s.toLocaleTimeString([], opts)} – ${e.toLocaleTimeString([], opts)}`;
}

/** ---------- Data hooks ---------- */

function useTodayData(routes: Routes) {
  const [schedule, setSchedule] = useState<TodayPayload | null>(null);
  const [tasks, setTasks] = useState<Task[] | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        // 1) Schedule (map backend shape -> TodayPayload)
        const rawSched = await http<any>(routes.schedule);
        const blocks: TodayBlock[] = Array.isArray(rawSched?.blocks)
          ? rawSched.blocks.map((b: any, idx: number) => ({
              id: String(b.id ?? idx),
              label: String(b.label ?? b.title ?? "Block"),
              context: b.context ?? undefined,
              start: String(b.start),
              end: String(b.end),
              calendar_url: b.calendar_url ?? b.calendarUrl ?? null,
              tasks: Array.isArray(b.tasks) ? b.tasks : [],
            }))
          : [];
        const sched: TodayPayload = {
          date: String(rawSched?.date ?? new Date().toISOString().slice(0, 10)),
          timezone: String(rawSched?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC"),
          blocks,
        };

        // 2) Triaged tasks -> derive (today + overdue), exclude completed
        const triaged = await http<TriagedResponse>(routes.triagedTasks);
        const pool: TriagedTaskRaw[] = [
          ...(triaged?.doNext ?? []),
          ...(triaged?.email ?? []),
          ...(triaged?.personal ?? []),
        ];
        const normalized: Task[] = pool.map((t) => ({
          id: String(t.id),
          title: String(t.name ?? "Task"),
          due_date: toISODateOnly(t.due_date),
          status: (t.status as any) ?? "open",
          priority: t.priority ?? null,
          source: "Helios",
        }));

        const todayStr = new Date().toISOString().slice(0, 10);
        const visible = normalized.filter((t) => t.status !== "completed" && !!t.due_date);
        const todayAndOverdue = visible.filter((t) => (t.due_date as string) <= todayStr);

        if (!alive) return;
        setSchedule(sched);
        setTasks(todayAndOverdue);
      } catch (e: any) {
        if (!alive) return;
        setError(e?.message ?? "Failed to load today data");
      } finally {
        if (!alive) return;
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [routes.schedule, routes.triagedTasks]);

  return { schedule, tasks, setTasks, loading, error };
}

async function completeTask(routes: Routes, id: string) {
  await http(routes.updateStatus(id), {
    method: "POST",
    body: JSON.stringify({ status: "completed" }),
  });
}

/** ---------- Component ---------- */

export default function TodayPanel(props: Props) {
  const routes: Routes = { ...defaultRoutes, ...(props.routes || {}) };
  const { schedule, tasks, setTasks, loading, error } = useTodayData(routes);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const handleComplete = async (id: string) => {
    try {
      await completeTask(routes, id);
      // optimistic update
      setTasks((prev) => (prev ? prev.filter((t) => t.id !== id) : prev));
    } catch (e: any) {
      alert(`Failed to complete task: ${e?.message ?? e}`);
    }
  };

  if (loading) {
    return <div className="p-2 text-sm opacity-70">Loading today…</div>;
  }
  if (error) {
    return <div className="p-2 text-sm text-red-600">Today error: {error}</div>;
  }

  return (
    <div className="grid gap-4">
      {/* ---- Today’s Schedule ---- */}
      <Card title={props.title ?? "📅 Today"}>
        {!schedule?.blocks?.length ? (
          <div className="p-2 text-sm opacity-70">No blocks found for today.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {schedule.blocks.map((b) => (
              <div key={b.id} className="rounded-md border p-2">
                <div className="flex items-center justify-between">
                  <div className="font-medium">{b.label}</div>
                  <div className="text-xs opacity-70">{fmtTimeRange(b.start, b.end)}</div>
                </div>
                {b.context ? (
                  <div className="mt-1 text-sm opacity-80">{b.context}</div>
                ) : null}
                {b.calendar_url ? (
                  <div className="mt-1 text-xs">
                    <a
                      className="underline opacity-75 hover:opacity-100"
                      href={b.calendar_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open in Calendar
                    </a>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ---- Tasks Due Today (incl. overdue) ---- */}
      <Card title={`✅ Tasks (${today})`}>
        {!tasks?.length ? (
          <div className="p-2 text-sm opacity-70">No tasks due today (or overdue).</div>
        ) : (
          <div className="flex flex-col gap-2">
            {tasks.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-md border p-2">
                <div>
                  <div className="font-medium">{t.title}</div>
                  <div className="text-xs opacity-70">
                    Due {t.due_date}
                    {t.priority ? ` • Priority: ${String(t.priority)}` : ""}
                  </div>
                </div>
                <Button onClick={() => handleComplete(t.id)}>Complete</Button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ---- Optional future sections (hidden for now) ---- */}
      {/* <Card title="➕ Quick Add"> // requires POST /api/tasks
           ...
         </Card> */}

      {/* <Card title="👥 Clients"> // requires GET /api/clients
           ...
         </Card> */}
    </div>
  );
}
