import React, { useState, useEffect } from "react";
import DoNext from "./components/DoNext";
import CalendarSidebar from "./components/CalendarSidebar";
import TaskActions from "./components/TaskActions";
import AIAdvicePanel from "./components/AIAdvicePanel";

export default function HeliosDashboard({ onReady, onShutdown }) {
  const [urgentDetected, setUrgentDetected] = useState(false);
  const [urgentTasks, setUrgentTasks] = useState([]);
  const [doNextTasks, setDoNextTasks] = useState([]);

  // ✅ Shutdown handler
  function handleShutdown() {
    fetch("http://localhost:3333/api/exit")
      .then((res) => {
        if (res.ok) {
          console.log("🛑 Shutdown triggered");
          setTimeout(() => {
            if (onShutdown) onShutdown();
          }, 1000);
        } else {
          console.error("❌ Shutdown request failed");
        }
      })
      .catch((err) => console.error("❌ Shutdown error:", err));
  }

  // ✅ Startup: load data + call onReady
  useEffect(() => {
    async function checkUrgentTasks() {
      try {
        const res = await fetch("http://localhost:3333/api/triaged-tasks");
        const data = await res.json();

        const allTasks = [
          ...(data?.doNext || []),
          ...(data?.overdue || []),
          ...(data?.triaged || []),
        ];

        const foundUrgent = allTasks.some((task) => task.isUrgent);
        setUrgentDetected(foundUrgent);
        setUrgentTasks(allTasks.filter((t) => t.isUrgent));
        setDoNextTasks(data?.doNext || []);
      } catch (err) {
        console.error("❌ Failed to fetch triaged tasks:", err);
      } finally {
        if (onReady) {
          console.log("✅ HeliosDashboard onReady()");
          onReady();
        }
      }
    }

    checkUrgentTasks();
  }, []);

  return (
    <div className="min-h-screen bg-purple-800 text-gray-900 px-4 py-6">
      <div className="flex flex-col lg:flex-row gap-6 w-full">
        {/* === Main Column === */}
        <main className="flex-1 flex flex-col gap-6 min-w-0">

          {urgentDetected && (
            <section className="bg-white rounded-xl shadow p-4">
              <div className="bg-red-100 text-red-800 border border-red-300 rounded-lg p-3 flex items-center justify-between">
                <p className="text-sm font-semibold">🚨 Urgent task detected — review ASAP.</p>
              </div>
            </section>
          )}

          <section className="bg-white rounded-xl shadow p-6">
            <h2 className="text-xl font-bold mb-4">🧠 Do Next</h2>
            <DoNext />
          </section>

          <section className="bg-white rounded-xl shadow p-6">
            <h2 className="text-xl font-bold mb-2">⚙️ Task Actions</h2>
            <TaskActions />
          </section>

          <section className="bg-white rounded-xl shadow p-6 h-[500px] flex flex-col">
            <h2 className="text-xl font-bold mb-2">🤖 AI Assistant</h2>
            <AIAdvicePanel urgentTasks={urgentTasks} doNextTasks={doNextTasks} />
          </section>
        </main>

        {/* === Sidebar === */}
        <aside className="w-full lg:w-[320px] flex-shrink-0 flex flex-col gap-4">
          <CalendarSidebar />

          <button
            onClick={handleShutdown}
            className="w-full bg-red-600 hover:bg-red-700 active:bg-red-800 text-white font-bold py-3 px-4 rounded-xl shadow-lg transition duration-200 text-lg tracking-wide"
          >
            🔻 Shutdown Helios
          </button>
        </aside>
      </div>
    </div>
  );
}
