// src/pages/dashboard/HeliosDashboard.jsx
import React, { useEffect, useRef, useState } from "react";
import "../../styles/helios.css";

import DashboardLayout from "../../components/DashboardLayout.jsx";
import TaskListPanel from "../../components/TaskListPanel.jsx";
import PersonalTasks from "../../components/PersonalTasks.jsx";
import AIAdvicePanel from "../../components/AIAdvicePanel.jsx";
import TodaysSchedule from "../../components/TodaysSchedule.jsx";
import ShutdownComplete from "../../components/ShutdownComplete.jsx";
import Card from "../../components/Card.jsx";
import Button from "../../components/Button.jsx";
import Skeleton from "../../components/Skeleton.jsx";
import RealtimeProvider, { useRealtime } from "../../context/RealtimeProvider.jsx";
import { getJSON, postJSON } from "../../lib/api.js";
import TodayPanel from "../../components/TodayPanel";

// NEW: Fixed Deadlines panel
import FixedDeadlinesCard from "../../components/FixedDeadlinesCard.jsx"; // uses your uploaded component

// HOTKEYS: adjust path if your hook lives elsewhere
import useHotkeys from "../../hooks/useHotkeys.js";

export default function HeliosDashboard() {
  return (
    <RealtimeProvider>
      <HeliosDashboardBody />
    </RealtimeProvider>
  );
}

function HeliosDashboardBody() {
  const [showSplash, setShowSplash] = useState(true);
  const [shutdownTriggered, setShutdownTriggered] = useState(false);

  const [urgentTasks, setUrgentTasks] = useState([]);
  const [doNextTasks, setDoNextTasks] = useState([]);
  const [emailTasks, setEmailTasks] = useState([]);
  const [personalTasks, setPersonalTasks] = useState([]);

  // NEW: FSS snapshot for finance signal
  const [fssSnapshot, setFssSnapshot] = useState(null);

  // NEW: global loading flag for skeletons
  const [loading, setLoading] = useState(true);

  // track which panel we last navigated to (for `r` to refresh)
  const [activePanel, setActivePanel] = useState(null); // "urgent" | "doNext" | "fixed" | "email" | "personal"

  // overdue state + audio
  const [personalHasOverdue, setPersonalHasOverdue] = useState(false);
  const lastOverdueRef = useRef(false);
  const audioUnlockedRef = useRef(false);
  const chimeRef = useRef(null);

  // panel refs for hotkey + anchor scroll
  const urgentRef = useRef(null);
  const doNextRef = useRef(null);
  const fixedRef = useRef(null);     // NEW
  const emailRef = useRef(null);
  const personalRef = useRef(null);

  // NEW: Fixed deadlines state
  const [fixedDeadlines, setFixedDeadlines] = useState([]);
  const [fixedDeadlinesLoading, setFixedDeadlinesLoading] = useState(false);
  const [fixedDeadlinesError, setFixedDeadlinesError] = useState(null);

  async function loadFixedDeadlines() {
    try {
      setFixedDeadlinesLoading(true);
      setFixedDeadlinesError(null);
      const data = await getJSON("/api/fixed-date-tasks");
      // defensive sort by fixed_date ascending if backend order ever changes
      data.sort((a, b) => new Date(a.fixed_date) - new Date(b.fixed_date));
      setFixedDeadlines(data);
    } catch (e) {
      console.error("❌ fixed-date-tasks fetch failed", e);
      setFixedDeadlinesError("Failed to load fixed deadlines.");
    } finally {
      setFixedDeadlinesLoading(false);
    }
  }

  function ensureAudioUnlockedOnce() {
    if (audioUnlockedRef.current) return;
    try {
      const el = new Audio();
      el.muted = true;
      el.play().catch(() => {});
      el.pause();
      audioUnlockedRef.current = true;
    } catch {}
  }
  function getChime() {
    if (!chimeRef.current) chimeRef.current = new Audio("/sounds/overdue_chime.mp3");
    return chimeRef.current;
  }
  async function playOverdueChime() {
    ensureAudioUnlockedOnce();
    try { await getChime().play(); } catch {}
  }
  function recomputeOverdue() {
    const now = Date.now();
    const has = personalTasks.some((t) => {
      const completed = Boolean(t?.completed) || t?.status?.status === "complete";
      const due = t?.due_date
        ? (isNaN(Number(t.due_date)) ? new Date(t.due_date).getTime() : Number(t.due_date))
        : null;
      return due && !completed && due < now;
    });
    setPersonalHasOverdue(has);
    if (has && !lastOverdueRef.current) playOverdueChime(); // 0 → >0 only
    lastOverdueRef.current = has;
  }

  // realtime ticks via provider (no refetch; just recompute)
  const rt = useRealtime();
  useEffect(() => {
    const off = rt.on("ticks", () => recomputeOverdue());
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rt, personalTasks]);

  // API helpers
  async function fetchTriagedTasks(runTriage = false) {
    try {
      if (runTriage) await postJSON("/api/triage/reload", {});
      const data = await getJSON("/api/triaged-tasks");
      const doNext = data.doNext || [];
      const email = data.email || [];
      const personal = data.personal || [];
      setDoNextTasks(doNext);
      setEmailTasks(email);
      setPersonalTasks(personal);
      return { doNext, email, personal };
    } catch (e) {
      console.error("❌ triaged-tasks fetch failed", e);
      return { doNext: [], email: [], personal: [] };
    }
  }

  async function fetchUrgentTasks() {
    try {
      const data = await getJSON("/api/todoist/urgent_tasks");
      const tasks = (data && data.tasks) || [];
      setUrgentTasks(tasks);
      return tasks;
    } catch (e) {
      console.error("❌ urgent_tasks fetch failed", e);
      return [];
    }
  }

  async function handleShutdown() {
    try {
      await getJSON("/api/exit");
      setShutdownTriggered(true);
    } catch (e) {
      console.error("❌ shutdown failed", e);
    }
  }

  // NEW: fetch minimal finance snapshot once on load
  useEffect(() => {
    (async () => {
      try {
        const snap = await getJSON("/api/fss/snapshot");
        setFssSnapshot(snap);
      } catch (e) {
        console.error("❌ fss snapshot fetch failed", e);
        setFssSnapshot({ available: false });
      }
    })();
  }, []);

  // load → advise → hide splash & skeletons
  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const [triaged, urgent] = await Promise.all([fetchTriagedTasks(), fetchUrgentTasks()]);
        // NEW: load fixed deadlines alongside initial data
        await loadFixedDeadlines();
        setShowSplash(false);
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { recomputeOverdue(); }, [personalTasks]);

  // unlock audio once
  useEffect(() => {
    const onFirst = () => { ensureAudioUnlockedOnce(); document.removeEventListener("click", onFirst); };
    document.addEventListener("click", onFirst);
    return () => document.removeEventListener("click", onFirst);
  }, []);

  // === HOTKEYS ===
  function scrollToPanel(key) {
    const map = {
      urgent: urgentRef,
      doNext: doNextRef,
      fixed: fixedRef,       // NEW
      email: emailRef,
      personal: personalRef,
    };
    const ref = map[key];
    if (ref?.current) {
      setActivePanel(key);
      ref.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  async function refreshActive() {
    if (activePanel === "urgent") await fetchUrgentTasks();
    else if (activePanel === "doNext") await fetchTriagedTasks(true);
    else if (activePanel === "fixed") await loadFixedDeadlines();  // NEW
    else if (activePanel === "email") await fetchTriagedTasks();
    else if (activePanel === "personal") await fetchTriagedTasks();
  }

  // NEW: remove a completed personal task in parent immediately so overdue bar updates instantly
  function handlePersonalComplete(taskId) {
    setPersonalTasks(prev => prev.filter(t => String(t.id) !== String(taskId)));
    // recomputeOverdue() will run via the existing useEffect([personalTasks])
  }

  useHotkeys([
    { combo: "1", handler: () => scrollToPanel("urgent") },
    { combo: "2", handler: () => scrollToPanel("doNext") },
    { combo: "3", handler: () => scrollToPanel("email") },
    { combo: "4", handler: () => scrollToPanel("personal") },
    { combo: "5", handler: () => scrollToPanel("fixed") },     // NEW hotkey
    { combo: "r", handler: () => refreshActive() },
    // add "/" to focus AI input once AIAdvicePanel exposes a ref
  ]);

  // === Join Next handler (new window) ===
  function openMeetingWindow(evt) {
    if (!evt) return;
    const url =
      evt?.conferenceData?.entryPoints?.find(p => p.entryPointType === "video")?.uri ||
      evt?.hangoutLink ||
      evt?.location ||
      evt?.htmlLink;

    if (!url) return;

    window.open(
      url,
      "", // unnamed = new window
      "noopener,noreferrer,toolbar=0,location=0,status=0,menubar=0,scrollbars=1,resizable=1,width=1200,height=800"
    );
  }

  if (shutdownTriggered) {
    return (
      <div className="min-h-screen bg-purple-900 text-white flex items-center justify-center px-4">
        <ShutdownComplete />
      </div>
    );
  }
  if (showSplash) {
    return (
      <div className="min-h-screen bg-purple-900 text-white flex items-center justify-center px-4">
        Loading Helios…
      </div>
    );
  }

  // === Finance-aware reordering (gentle, reversible) ===
  function financeBoosted(tasks, snap) {
    if (!snap?.available) return tasks;
    const risky = snap.risk_level === "high" || snap.tee_covered === false;
    if (!risky) return tasks;

    const isFinance = (t) => {
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
    };

    return [...tasks].sort((a, b) => (isFinance(b) ? 1 : 0) - (isFinance(a) ? 1 : 0));
  }

  const doNextBoosted = financeBoosted(doNextTasks, fssSnapshot);
  const showFinanceBadge = Boolean(
    fssSnapshot?.available && (fssSnapshot.risk_level === "high" || fssSnapshot.tee_covered === false)
  );

  // scorebar using helios.css strobe classes (renders only when overdue)
  const scorebar = (
    <div className="sticky top-0 z-10">
      {personalHasOverdue && (
        <div className="helios-flashbar helios-flashbar--active">
          ⚠️ Overdue personal tasks detected
        </div>
      )}

      <div className="rounded-xl shadow px-4 py-3 text-sm font-medium flex gap-4 justify-start bg-white">
        <a href="#primary-anchor" className="hover:underline text-blue-700">
          🚨 Primary: {urgentTasks.length}
        </a>
        <a href="#do-next-anchor" className="hover:underline text-blue-700">
          ✅ Do Next: {doNextTasks.length}
        </a>
        <a href="#fixed-deadlines-anchor" className="hover:underline text-blue-700">
          📅 Fixed: {fixedDeadlines.length}
        </a>
        <a href="#email-tasks-anchor" className="hover:underline text-blue-700">
          📥 Email: {emailTasks.length}
        </a>
        <a href="#personal-tasks-anchor" className="hover:underline text-blue-700">
          👤 Personal: {personalTasks.length}
        </a>

        {/* NEW: finance snapshot badge */}
        {fssSnapshot?.available && (
          <span
            className={
              "ml-2 inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border " +
              (fssSnapshot.risk_level === "high"
                ? "border-red-300 bg-red-50 text-red-700"
                : fssSnapshot.risk_level === "med"
                ? "border-amber-300 bg-amber-50 text-amber-700"
                : "border-emerald-300 bg-emerald-50 text-emerald-700")
            }
            title={
              `Buffer ${Number(fssSnapshot.buffer_pct ?? 0).toFixed(1)}%` +
              (fssSnapshot.tee_covered === false ? " • Tee not covered" : "")
            }
          >
            £{Math.round(Number(fssSnapshot.total_balance ?? 0))} • {String(fssSnapshot.risk_level || "").toUpperCase()}
          </span>
        )}
      </div>
    </div>
  );

  return (
    <DashboardLayout
      scorecard={scorebar}
      onShutdown={handleShutdown}
      onJoinNext={openMeetingWindow}
    >
      {/* === AI === */}
      <section ref={null}>
        <Card
          title="🔮 AI Assistant"
          className="h[450px] flex flex-col mb-4"
          actions={
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                askInitialAdvice({
                  urgent: urgentTasks,
                  doNext: doNextTasks,
                  email: emailTasks,
                  personal: personalTasks,
                })
              }
            >
              Refresh Advice
            </Button>
          }
        >
          {loading ? (
            <div className="p-2">
              <Skeleton lines={6} />
              <div className="mt-4">
                <Skeleton lines={2} />
              </div>
            </div>
          ) : (
            <AIAdvicePanel
              urgentTasks={urgentTasks}
              doNextTasks={doNextTasks}
              emailTasks={emailTasks}
              personalTasks={personalTasks}
            />
          )}
        </Card>
      </section>
            {/* === Today’s Schedule (block-centric) === */}
+      <section id="today-panel" className="scroll-mt-24">
  <TodayPanel />
  </section>
      
        

     

      
      

      
    </DashboardLayout>
  );
}
