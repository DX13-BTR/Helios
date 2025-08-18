// Helios — Today’s Schedule (block‑centric) — TSX version
// ------------------------------------------------------------
// Drop-in TypeScript React component + API contract.
// Save as: Dashboard_3.0/frontend/src/components/TodaysSchedule.tsx
// Requires: typescript, @types/react, @types/react-dom (see chat for steps)

import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Calendar, Clock, ExternalLink, CircleDot, AlertTriangle, Link2, Loader2, CheckCircle2, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

// --------------------------- Types
export type TaskStatus = "open" | "in_progress" | "done";
export type TaskSource = "ClickUp" | "Todoist" | "HeliosInternal";
export type BlockContext = "DeepWork" | "Admin" | "Comm" | "Meeting" | "Personal" | "Errand";

export interface HeliosTask {
  id: string;
  title: string;
  source: TaskSource;
  url?: string;
  estimateMinutes?: number | null;
  status: TaskStatus;
  priority?: 0 | 1 | 2 | 3 | null;
  blockId?: string | null;
}

export interface WorkBlock {
  id: string;
  title: string;
  context: BlockContext;
  calendarEventId?: string;
  calendarUrl?: string;
  start: string; // ISO
  end: string;   // ISO
  color?: string;
  assignedTaskIds?: string[];
  notes?: string;
  extended?: Record<string, unknown>;
}

export interface TodayPayload {
  date: string; // YYYY-MM-DD
  timezone: string;
  now: string; // ISO
  calendar_source: string;
  blocks: WorkBlock[];
  tasks: HeliosTask[];
  unallocatedTaskIds?: string[];
}

// --------------------------- Helpers
const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const minutesBetween = (startIso: string, endIso: string) => Math.max(0, Math.round((new Date(endIso).getTime() - new Date(startIso).getTime()) / 60000));
const clamp = (n: number, min = 0, max = 100) => Math.max(min, Math.min(max, n));

function contextStyle(ctx: BlockContext) {
  switch (ctx) {
    case "DeepWork": return "bg-blue-50 border-blue-200";
    case "Admin": return "bg-orange-50 border-orange-200";
    case "Comm": return "bg-emerald-50 border-emerald-200";
    case "Meeting": return "bg-purple-50 border-purple-200";
    case "Personal": return "bg-neutral-50 border-neutral-200";
    case "Errand": return "bg-amber-50 border-amber-200";
    default: return "bg-muted";
  }
}

function contextBadge(ctx: BlockContext) {
  const labelMap: Record<BlockContext, string> = {
    DeepWork: "Deep Work",
    Admin: "Admin",
    Comm: "Comms",
    Meeting: "Meeting",
    Personal: "Personal",
    Errand: "Errand",
  };
  return <Badge variant="secondary" className="rounded-full">{labelMap[ctx]}</Badge>;
}

function StatusIcon({ status }: { status: TaskStatus }) {
  if (status === "done") return <CheckCircle2 className="h-4 w-4" aria-hidden />;
  if (status === "in_progress") return <CircleDot className="h-4 w-4" aria-hidden />;
  return <CircleDot className="h-4 w-4 opacity-50" aria-hidden />;
}

// --------------------------- Main Component
export default function TodaysSchedule({ seed }: { seed?: TodayPayload }) {
  const [data, setData] = useState<TodayPayload | null>(seed ?? null);
  const [loading, setLoading] = useState<boolean>(!seed);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (seed) return;
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        const res = await fetch("/api/schedule/today", { headers: { Accept: "application/json" } });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json: TodayPayload = await res.json();
        if (alive) setData(json);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "Failed to load schedule";
        if (alive) setError(msg);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [seed]);

  const now = useMemo(() => new Date(data?.now ?? Date.now()), [data?.now]);

  const blocks = useMemo(() => {
    if (!data) return [] as Array<WorkBlock & { tasks: HeliosTask[]; durationMin: number; allocationMin: number; overBy: number; livePct: number; isLive: boolean; overlaps: boolean }>;

    const taskById = Object.fromEntries(data.tasks.map(t => [t.id, t] as const));

    const enriched = data.blocks
      .map(b => {
        const tasks = (b.assignedTaskIds ?? []).map(id => taskById[id]).filter(Boolean) as HeliosTask[];
        const durationMin = minutesBetween(b.start, b.end);
        const allocationMin = tasks.reduce((acc, t) => acc + (t.estimateMinutes ?? 0), 0);
        const overBy = Math.max(0, allocationMin - durationMin);
        const isLive = now >= new Date(b.start) && now <= new Date(b.end);
        const livePct = isLive ? clamp(((now.getTime() - new Date(b.start).getTime()) / (new Date(b.end).getTime() - new Date(b.start).getTime())) * 100) : 0;
        return { ...b, tasks, durationMin, allocationMin, overBy, livePct, isLive, overlaps: false };
      })
      .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());

    // simple overlap pass
    for (let i = 0; i < enriched.length - 1; i++) {
      const a = enriched[i];
      const b = enriched[i + 1];
      if (new Date(a.end) > new Date(b.start)) {
        a.overlaps = b.overlaps = true;
      }
    }
    return enriched;
  }, [data, now]);

  const unallocated = useMemo(() => {
    if (!data) return [] as HeliosTask[];
    const setIds = new Set((data.unallocatedTaskIds ?? []));
    return data.tasks.filter(t => setIds.has(t.id));
  }, [data]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 mr-2 animate-spin" /> Loading today’s schedule…
      </div>
    );
  }
  if (error) {
    return (
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive"><AlertTriangle className="h-5 w-5" /> Failed to load</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{error}</p>
          <div className="mt-3">
            <Button onClick={() => location.reload()} variant="outline" size="sm">Retry</Button>
          </div>
        </CardContent>
      </Card>
    );
  }
  if (!data || blocks.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Calendar className="h-5 w-5" /> Today’s Schedule</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No work blocks found for today.</p>
          <div className="mt-3 flex gap-2">
            <Button asChild size="sm"><a href="/planner">Create a focus block</a></Button>
            <Button variant="outline" size="sm" asChild>
              <a href="https://calendar.google.com/" target="_blank" rel="noreferrer">Open Google Calendar <ExternalLink className="ml-1 h-4 w-4" /></a>
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5" />
          <h2 className="text-xl font-semibold">Today’s Schedule</h2>
          <Separator orientation="vertical" className="mx-2 h-5" />
          <div className="text-sm text-muted-foreground">{new Date(data.date + "T00:00:00").toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}</div>
        </div>
        <div className="text-xs text-muted-foreground">{data.timezone}</div>
      </header>

      {blocks.map((b) => (
        <motion.div key={b.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
          <Card className={cn("border", contextStyle(b.context), b.overlaps && "border-dashed")} style={{ borderLeftWidth: 6, borderLeftColor: b.color ?? undefined }}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  {contextBadge(b.context)}
                  <CardTitle className="text-base font-semibold">{b.title}</CardTitle>
                  {b.overlaps && (
                    <Badge variant="outline" className="text-xs"><AlertTriangle className="h-3 w-3 mr-1" /> Overlap</Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock className="h-4 w-4" /> {fmtTime(b.start)}–{fmtTime(b.end)}
                  <Separator orientation="vertical" className="h-4" />
                  <span>{minutesBetween(b.start, b.end)} min</span>
                  {b.calendarUrl && (
                    <Button asChild variant="ghost" size="sm" className="h-7 px-2">
                      <a href={b.calendarUrl} target="_blank" rel="noreferrer" aria-label="Open in Calendar"><Link2 className="h-4 w-4" /></a>
                    </Button>
                  )}
                </div>
              </div>

              {b as any && (() => { /* live progress computed earlier */ return null; })()}
            </CardHeader>

            <CardContent className="pt-0">
              {/* Task list */}
              <ul className="mt-2 space-y-2">
                {(b as any).tasks?.length === 0 ? (
                  <li className="text-sm text-muted-foreground">No tasks assigned. Drop a task here or use the allocator.</li>
                ) : (
                  (b as any).tasks.map((t: HeliosTask) => (
                    <li key={t.id} className="flex items-center justify-between rounded-xl border bg-white/60 px-3 py-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <StatusIcon status={t.status} />
                        <a href={t.url} target="_blank" rel="noreferrer" className="truncate hover:underline" title={t.title}>{t.title}</a>
                        {typeof t.priority === "number" && (
                          <Badge variant="outline" className="ml-1 text-[10px]">P{t.priority}</Badge>
                        )}
                      </div>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{t.estimateMinutes != null ? `${t.estimateMinutes} min` : "— min"}</span>
                        <Badge variant="secondary" className="rounded-full">{t.source}</Badge>
                      </div>
                    </li>
                  ))
                )}
              </ul>

              {/* Capacity & overage */}
              <div className="mt-3 flex items-center justify-between text-xs">
                <div className="text-muted-foreground">
                  Allocated {(b as any).tasks?.reduce((acc: number, t: HeliosTask) => acc + (t.estimateMinutes ?? 0), 0) ?? 0} / {minutesBetween(b.start, b.end)} min
                </div>
                {(() => {
                  const allocationMin = (b as any).tasks?.reduce((acc: number, t: HeliosTask) => acc + (t.estimateMinutes ?? 0), 0) ?? 0;
                  const overBy = Math.max(0, allocationMin - minutesBetween(b.start, b.end));
                  return overBy > 0 ? <Badge variant="destructive">Over by {overBy} min</Badge> : null;
                })()}
              </div>

              {/* Notes & locks for Personal blocks */}
              <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                {b.context === "Personal" && <Lock className="h-3.5 w-3.5" />}
                {b.notes && <span className="line-clamp-2">{b.notes}</span>}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      ))}

      {/* Unallocated bucket */}
      {unallocated.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Unallocated for Today</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {unallocated.map(t => (
                <li key={t.id} className="flex items-center justify-between rounded-xl border bg-white/60 px-3 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <StatusIcon status={t.status} />
                    <a href={t.url} target="_blank" rel="noreferrer" className="truncate hover:underline" title={t.title}>{t.title}</a>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{t.estimateMinutes != null ? `${t.estimateMinutes} min` : "— min"}</span>
                    <Badge variant="secondary" className="rounded-full">{t.source}</Badge>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// --------------------------- Minimal FastAPI stub reminder
// Backend endpoint expected: GET /api/schedule/today → TodayPayload JSON.
// Use the mock in earlier spec, then bind to GCal & ClickUp/Todoist later.
