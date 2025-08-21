import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CalendarDays, Clock, CheckCircle2, Plus, Loader2, AlertTriangle, ChevronDown, ChevronUp, Link as LinkIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

/**
 * TodayPanel.tsx
 *
 * Single-panel TSX that AMALGAMATES your existing "TodaysSchedule" (block-centric view)
 * and "HeliosTodayView" (task intake + completion) into one clean panel.
 *
 * Endpoints (override with props if different):
 *  - GET  /api/schedule/today                   -> TodayPayload (date, timezone, blocks[], unallocated[])
 *  - GET  /api/tasks/search?due=today&include_overdue=1  -> Task[]
 *  - POST /api/tasks                            -> Task (create)
 *  - PATCH /api/tasks/:id                       -> Task (status updates)
 *  - GET  /api/clients                          -> Client[] (for quick add)
 *
 * Styling: shadcn/ui + Tailwind, mobile-first.
 */

// ---- Types ----
export type Priority = "low" | "normal" | "high" | "urgent";
export type TaskStatus = "open" | "in_progress" | "completed";

export interface Task {
  id: string | number;
  title: string;
  client_id?: string | number | null;
  client_name?: string | null;
  due_date?: string | null; // YYYY-MM-DD
  status: TaskStatus;
  priority?: Priority;
  estimate_mins?: number | null;
  source?: "ClickUp" | "Todoist" | "Helios" | string;
  source_label?: string | null; // e.g., email label
}

export interface Client { id: string | number; name: string }

export interface TodayBlock {
  id: string;
  label: string;            // e.g., Deep Work / Admin / Meeting
  context?: string;         // e.g., Client, Area, etc.
  start: string;            // ISO datetime or HH:MM
  end: string;              // ISO datetime or HH:MM
  calendar_url?: string;    // deep link to calendar
  tasks: Task[];            // tasks allocated to this block
}

export interface TodayPayload {
  date: string;              // YYYY-MM-DD
  timezone: string;          // Europe/London
  blocks: TodayBlock[];
  unallocated?: Task[];      // tasks due today but not placed in any block
}

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

function isoDateOnly(d: Date): string { return d.toISOString().slice(0,10); }

const priorityRank: Record<Priority, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
function byPriority(a?: Priority, b?: Priority) {
  return (priorityRank[a || "normal"] ?? 9) - (priorityRank[b || "normal"] ?? 9);
}

// ---- Quick Add Drawer ----
function QuickAddTask({ onCreated, clientsPath = "/api/clients", createPath = "/api/tasks" }: {
  onCreated(task: Task): void;
  clientsPath?: string;
  createPath?: string;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [clientId, setClientId] = useState<string | number | "">("");
  const [dueDate, setDueDate] = useState<string>(isoDateOnly(new Date()));
  const [priority, setPriority] = useState<Priority>("normal");
  const [clients, setClients] = useState<Client[]>([]);
  const [loadingClients, setLoadingClients] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setLoadingClients(true);
    http<Client[]>(clientsPath)
      .then(setClients)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingClients(false));
  }, [open, clientsPath]);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => inputRef.current?.focus(), 50);
    return () => clearTimeout(t);
  }, [open]);

  async function submit() {
    if (!title.trim()) { setError("Title is required"); inputRef.current?.focus(); return; }
    setSubmitting(true); setError("");
    try {
      const payload = { title: title.trim(), client_id: clientId || null, due_date: dueDate || null, priority } as any;
      const t = await http<Task>(createPath, { method: "POST", body: JSON.stringify(payload) });
      onCreated(t);
      setTitle(""); setClientId(""); setDueDate(isoDateOnly(new Date())); setPriority("normal");
      inputRef.current?.focus();
    } catch (e:any) { setError(e.message); }
    finally { setSubmitting(false); }
  }

  return (
    <>
      <Button className="fixed bottom-6 right-6 z-40 rounded-full shadow-lg" onClick={() => setOpen(true)}>
        <Plus className="w-5 h-5 mr-2"/> Quick Add
      </Button>

      <AnimatePresence>
        {open && (
          <motion.div initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} className="fixed inset-0 z-40 bg-black/40" onClick={() => setOpen(false)} />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.div initial={{x:"100%"}} animate={{x:0}} exit={{x:"100%"}} transition={{type:"spring", stiffness:260, damping:30}}
            className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-md bg-white shadow-2xl p-5 flex flex-col gap-4 overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold">Quick Add Task</h3>
              <Button variant="ghost" size="icon" onClick={() => setOpen(false)} aria-label="Close">
                ✕
              </Button>
            </div>
            {error && (
              <div className="text-red-700 bg-red-50 border border-red-200 rounded-xl p-3 text-sm flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            <label className="text-sm font-medium">Title</label>
            <input ref={inputRef} value={title} onChange={(e)=>setTitle(e.target.value)} placeholder="What needs doing?"
              className="w-full rounded-2xl border border-neutral-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-black"/>

            <label className="text-sm font-medium">Client</label>
            <select value={String(clientId)} onChange={(e)=>setClientId(e.target.value||"")}
              className="w-full rounded-2xl border border-neutral-300 px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-black">
              <option value="">— None —</option>
              {loadingClients ? <option>Loading…</option> : clients.map(c=> <option key={c.id} value={String(c.id)}>{c.name}</option>)}
            </select>

            <label className="text-sm font-medium">Due date</label>
            <input type="date" value={dueDate} onChange={(e)=>setDueDate(e.target.value)}
              className="w-full rounded-2xl border border-neutral-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-black"/>

            <label className="text-sm font-medium">Priority</label>
            <div className="grid grid-cols-4 gap-2">
              {["low","normal","high","urgent"].map(p => (
                <button key={p} onClick={()=>setPriority(p as Priority)}
                  className={cn("rounded-2xl border px-3 py-2 text-sm", priority===p?"border-black bg-black text-white":"border-neutral-300 hover:border-black")}>{p}</button>
              ))}
            </div>

            <div className="mt-2 flex gap-2">
              <Button onClick={submit} disabled={submitting}>
                {submitting ? <Loader2 className="w-4 h-4 animate-spin"/> : <Plus className="w-4 h-4 mr-2"/>}
                Add task
              </Button>
              <Button variant="outline" onClick={()=>setOpen(false)}>Close</Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

// ---- Main Today Panel ----
export default function TodayPanel({ routes }: {
  routes?: {
    schedule?: string; // default /api/schedule/today
    tasksSearch?: string; // default /api/tasks/search?due=today&include_overdue=1
    patchTask?: (id: Task["id"]) => string; // default /api/tasks/:id
    createTask?: string; // default /api/tasks
    clients?: string; // default /api/clients
  };
}) {
  // endpoints
  const schedulePath = routes?.schedule ?? "/api/schedule/today";
  const tasksPath = routes?.tasksSearch ?? "/api/tasks/search?due=today&include_overdue=1";
  const patchPath = (id: Task["id"]) => routes?.patchTask?.(id) ?? `/api/tasks/${id}`;
  const createPath = routes?.createTask ?? "/api/tasks";
  const clientsPath = routes?.clients ?? "/api/clients";

  // state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [schedule, setSchedule] = useState<TodayPayload | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showBlocks, setShowBlocks] = useState(true);
  const [showTasks, setShowTasks] = useState(true);

  async function loadAll() {
    setLoading(true); setError("");
    try {
      const [sched, todayTasks] = await Promise.all([
        http<TodayPayload>(schedulePath),
        http<Task[]>(tasksPath),
      ]);
      setSchedule(sched);
      setTasks(todayTasks);
    } catch (e:any) { setError(e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadAll(); }, [schedulePath, tasksPath]);

  const todayISO = isoDateOnly(new Date());
  function isOverdue(t: Task) { return !!t.due_date && t.status !== "completed" && t.due_date < todayISO; }
  function isDueToday(t: Task) { return !!t.due_date && t.status !== "completed" && t.due_date === todayISO; }

  const visibleTasks = useMemo(() => {
    return tasks.filter(t => t.status !== "completed").sort((a,b)=> byPriority(a.priority, b.priority));
  }, [tasks]);

  async function completeTask(id: Task["id"]) {
    const prev = tasks;
    setTasks(prev => prev.map(t => t.id === id ? { ...t, status: "completed" } : t));
    try { await http<Task>(patchPath(id), { method: "PATCH", body: JSON.stringify({ status: "completed" }) }); }
    catch (e) { setTasks(prev); alert((e as Error).message); }
  }

  return (
    <Card className="w-full">
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-xl">
          <CalendarDays className="w-5 h-5"/>
          Today
        </CardTitle>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadAll}>
            <Loader2 className="w-4 h-4 mr-2 animate-spin"/> Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-3 text-red-700 bg-red-50 border border-red-200 rounded-xl p-3 text-sm flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {loading && (
          <div className="flex items-center gap-2 text-neutral-600"><Loader2 className="w-4 h-4 animate-spin"/> Loading…</div>
        )}

        {!loading && (
          <div className="space-y-6">
            {/* Blocks section */}
            <section>
              <header className="flex items-center justify-between mb-2">
                <h3 className="text-base font-semibold">Schedule blocks</h3>
                <Button variant="ghost" size="sm" onClick={()=>setShowBlocks(v=>!v)}>
                  {showBlocks ? <><ChevronUp className="w-4 h-4 mr-1"/>Hide</> : <><ChevronDown className="w-4 h-4 mr-1"/>Show</>}
                </Button>
              </header>
              <div className={cn("space-y-3", !showBlocks && "hidden")}> 
                {schedule?.blocks?.length ? schedule.blocks.map(block => {
                  const start = new Date(block.start); const end = new Date(block.end);
                  const mins = Math.max(0, Math.round((+end - +start)/60000));
                  const est = (block.tasks || []).reduce((s,t)=> s + (t.estimate_mins||0), 0);
                  const over = est > mins;
                  return (
                    <div key={block.id} className={cn("rounded-2xl border p-3", over && "border-red-300 bg-red-50")}> 
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium flex items-center gap-2">
                            {block.label}
                            {block.context && <Badge variant="secondary">{block.context}</Badge>}
                          </div>
                          <div className="text-xs text-neutral-600 flex items-center gap-2">
                            <Clock className="w-3 h-3"/> {start.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} – {end.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                            <span>• {mins}m capacity</span>
                            {typeof est === 'number' && <span>• {est}m allocated</span>}
                            {over && <Badge variant="destructive">Over</Badge>}
                          </div>
                        </div>
                        {block.calendar_url && (
                          <a className="text-sm inline-flex items-center gap-1 px-2 py-1 rounded-full border border-neutral-300 hover:border-black"
                             href={block.calendar_url} target="_blank" rel="noreferrer">
                            <LinkIcon className="w-3 h-3"/> Calendar
                          </a>
                        )}
                      </div>

                      {(block.tasks?.length ?? 0) > 0 && (
                        <ul className="mt-2 space-y-2">
                          {block.tasks!.sort((a,b)=>byPriority(a.priority,b.priority)).map(t => (
                            <li key={t.id} className="flex items-start gap-3">
                              <button onClick={()=>completeTask(t.id)} className="mt-0.5 p-1 rounded-full border border-neutral-300 hover:border-black" aria-label="Mark complete">
                                <CheckCircle2 className="w-5 h-5"/>
                              </button>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-2">
                                  <div className="truncate font-medium">{t.title}</div>
                                  {t.priority && <Badge variant={t.priority === 'urgent' || t.priority === 'high' ? 'default' : 'secondary'}>{t.priority}</Badge>}
                                </div>
                                <div className="mt-1 text-xs text-neutral-600 flex items-center gap-2">
                                  {t.client_name && <span className="truncate">{t.client_name}</span>}
                                  {typeof t.estimate_mins === 'number' && <span>{t.estimate_mins}m</span>}
                                  {t.source_label && <span>• {t.source_label}</span>}
                                </div>
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                }) : (
                  <div className="rounded-2xl border border-dashed p-4 text-neutral-500 text-sm">No blocks today.</div>
                )}

                {schedule?.unallocated?.length ? (
                  <div className="rounded-2xl border p-3">
                    <div className="text-sm font-medium mb-2">Unallocated</div>
                    <ul className="space-y-2">
                      {schedule.unallocated.sort((a,b)=>byPriority(a.priority,b.priority)).map(t => (
                        <li key={t.id} className={cn("flex items-start gap-3", (isOverdue(t)) && "text-red-700")}> 
                          <button onClick={()=>completeTask(t.id)} className="mt-0.5 p-1 rounded-full border border-neutral-300 hover:border-black" aria-label="Mark complete">
                            <CheckCircle2 className="w-5 h-5"/>
                          </button>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <div className="truncate font-medium">{t.title}</div>
                              {t.priority && <Badge variant={t.priority === 'urgent' || t.priority === 'high' ? 'default' : 'secondary'}>{t.priority}</Badge>}
                            </div>
                            <div className="mt-1 text-xs text-neutral-600 flex items-center gap-2">
                              {t.client_name && <span className="truncate">{t.client_name}</span>}
                              {t.due_date && <span>{t.due_date}</span>}
                              {t.source && <span>{t.source}</span>}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            </section>

            <Separator />

            {/* Tasks section (intake + completion) */}
            <section>
              <header className="flex items-center justify-between mb-2">
                <h3 className="text-base font-semibold">Actionable tasks</h3>
                <Button variant="ghost" size="sm" onClick={()=>setShowTasks(v=>!v)}>
                  {showTasks ? <><ChevronUp className="w-4 h-4 mr-1"/>Hide</> : <><ChevronDown className="w-4 h-4 mr-1"/>Show</>}
                </Button>
              </header>

              <div className={cn("space-y-3", !showTasks && "hidden")}> 
                {visibleTasks.length ? (
                  <ul className="space-y-2">
                    {visibleTasks.map(t => (
                      <li key={t.id} className={cn("rounded-2xl border p-3 bg-white", isOverdue(t) && "border-red-300 bg-red-50")}> 
                        <div className="flex items-start gap-3">
                          <button onClick={()=>completeTask(t.id)} className="mt-0.5 p-1 rounded-full border border-neutral-300 hover:border-black" aria-label="Mark complete">
                            <CheckCircle2 className="w-5 h-5"/>
                          </button>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                              <div className="truncate font-medium">{t.title}</div>
                              {t.priority && <Badge variant={t.priority === 'urgent' || t.priority === 'high' ? 'default' : 'secondary'}>{t.priority}</Badge>}
                            </div>
                            <div className="mt-1 text-xs text-neutral-600 flex items-center gap-2">
                              {t.client_name && <span className="truncate">{t.client_name}</span>}
                              {t.due_date && <span className="inline-flex items-center gap-1"><Clock className="w-3 h-3"/> {t.due_date}</span>}
                              {t.source_label && <span className="inline-flex items-center gap-1">• {t.source_label}</span>}
                            </div>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="rounded-2xl border border-dashed p-4 text-neutral-500 text-sm">Nothing due right now. Add something below.</div>
                )}

                {/* QuickAdd floating button and drawer */}
                <QuickAddTask onCreated={(t)=> setTasks(prev => [t, ...prev])} clientsPath={clientsPath} createPath={createPath} />
              </div>
            </section>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
