import React from "react";
import CalendarSidebar from "./CalendarSidebar";

export default function DashboardLayout({
  scorecard,
  children,
  onShutdown,
  onJoinNext,
  showCalendar = true, // per-page toggle (CIE keeps calendar)
}) {
  return (
    <div className="min-h-screen bg-purple-800 text-gray-900 px-4 py-6">
      <div className={showCalendar ? "flex flex-col lg:flex-row gap-6 w-full" : "w-full"}>
        {/* === Main Column === */}
        <main className={showCalendar ? "flex-1 flex flex-col gap-6 min-w-0" : "flex flex-col gap-6 min-w-0"}>
          {scorecard}
          {children}
        </main>

        {/* === Sidebar (only when calendar is shown) === */}
        {showCalendar && (
          <aside className="w-full lg:w-[320px] flex-shrink-0 flex flex-col gap-4">
            <CalendarSidebar onJoinNext={onJoinNext} />
            <button
              onClick={onShutdown}
              className="w-full bg-red-600 hover:bg-red-700 active:bg-red-800 text-white font-bold py-3 px-4 rounded-xl shadow-lg transition duration-200 text-lg tracking-wide"
            >
              🔻 Shutdown Helios
            </button>
          </aside>
        )}
      </div>
      {/* When sidebar is hidden, keep shutdown accessible under content */}
      {!showCalendar && (
        <div className="mt-6 max-w-5xl mx-auto">
          <button
            onClick={onShutdown}
            className="w-full bg-red-600 hover:bg-red-700 active:bg-red-800 text-white font-bold py-3 px-4 rounded-xl shadow-lg transition duration-200 text-lg tracking-wide"
          >
            🔻 Shutdown Helios
          </button>
        </div>
      )}
    </div>
  );
}
