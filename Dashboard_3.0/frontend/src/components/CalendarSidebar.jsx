import React, { useState, useEffect, useRef } from "react";

/* ---------- Tiny minute-aligned clock ---------- */
function useNowEveryMinute() {
  const [now, setNow] = React.useState(() => new Date());

  React.useEffect(() => {
    let timeoutId, intervalId;

    const msToNextMinute = 60000 - (Date.now() % 60000);
    timeoutId = setTimeout(() => {
      setNow(new Date()); // snap to boundary
      intervalId = setInterval(() => setNow(new Date()), 60000); // tick every minute
    }, msToNextMinute);

    const onVis = () => { if (!document.hidden) setNow(new Date()); };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      clearTimeout(timeoutId);
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return now;
}

/* ---------- Helpers: compact link badges & contact chips ---------- */
function extractLinksFromEvent(ev) {
  return Array.isArray(ev?.source_links) ? ev.source_links : [];
}

function originFor(url) {
  try {
    const { hostname } = new URL(url);
    if (hostname.includes("clickup.com")) return { label: "Open in ClickUp", emoji: "⚡" };
    if (hostname.includes("todoist.com")) return { label: "Open in Todoist", emoji: "📝" };
    if (hostname.includes("reclaim.ai")) return { label: "Open in Reclaim", emoji: "🕒" };
    return { label: hostname.replace(/^www\./, ""), emoji: "🔗" };
  } catch {
    return { label: "Link", emoji: "🔗" };
  }
}

function LinkBadges({ event }) {
  const links = extractLinksFromEvent(event).slice(0, 2); // up to 2 badges
  if (links.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {links.map((href, i) => {
        const { label, emoji } = originFor(href);
        return (
          <a
            key={i}
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            title={href}
            className="text-[10px] sm:text-xs px-2 py-0.5 rounded-full border border-gray-300 text-indigo-700 hover:underline bg-indigo-50"
          >
            {emoji} {label}
          </a>
        );
      })}
    </div>
  );
}

function ContactChips({ event }) {
  const matches = event?.matched_clients || [];
  if (!matches.length) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {matches.slice(0, 3).map((c) => (
        <span
          key={c.id}
          className="text-[10px] px-2 py-0.5 rounded-full border border-gray-300 bg-gray-50"
          title={c.tags?.length ? c.tags.join(", ") : ""}
        >
          {c.name}
        </span>
      ))}
    </div>
  );
}

/* ------------------------------ Component ----------------------------- */
export default function CalendarSidebar({ onJoinNext, joinDisabled = false }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(null);
  const containerRef = useRef(null);

  const now = useNowEveryMinute();

  useEffect(() => {
    fetchEvents();
  }, []);

  async function fetchEvents() {
    try {
      const res = await fetch("http://localhost:3333/api/calendar/today_normalized");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEvents(data.events || []);
    } catch (err) {
      console.error("❌ Failed to fetch calendar events:", err);
      setError("Failed to load calendar events.");
    }
  }

  // Determine the single next upcoming event (5 min grace)
  const upcoming = events
    .map((e) => ({ e, startMs: new Date(e.start).getTime() }))
    .filter((x) => !Number.isNaN(x.startMs) && x.startMs >= Date.now() - 5 * 60 * 1000)
    .sort((a, b) => a.startMs - b.startMs);

  const nextJoinable = upcoming[0]?.e || null;
  const nextEventId = nextJoinable?.id || null;

  // Auto-scroll only when the next event CHANGES
  const lastNextIdRef = useRef(null);
  useEffect(() => {
    if (!containerRef.current) return;
    if (nextEventId && nextEventId !== lastNextIdRef.current) {
      const anchor = containerRef.current.querySelector(".next-event-anchor");
      if (anchor) anchor.scrollIntoView({ behavior: "smooth", block: "start" });
      lastNextIdRef.current = nextEventId;
    }
  }, [nextEventId]);

  const periods = {
    Morning: { start: 0, end: 12 },
    Afternoon: { start: 12, end: 18 },
    Evening: { start: 18, end: 24 },
  };

  function getPeriodLabel(date) {
    const hour = date.getHours();
    for (const [label, { start, end }] of Object.entries(periods)) {
      if (hour >= start && hour < end) return label;
    }
    return "Other";
  }

  function isOngoing(event) {
    const start = new Date(event.start);
    const end = new Date(event.end);
    return start <= now && end >= now;
  }

  function isPast(event) {
    const end = new Date(event.end);
    return end < now;
  }

  function isNextAnchor(event) {
    return nextEventId && event.id === nextEventId;
  }

  function renderEvent(event) {
    const start = new Date(event.start);
    const end = new Date(event.end);
    const timeStr = `${start.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} - ${end.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    const ongoing = isOngoing(event);
    const past = isPast(event);

    return (
      <div
        key={event.id}
        className={`rounded-lg border p-3 ${
          ongoing
            ? "bg-green-50 border-green-200"
            : past
            ? "bg-gray-50 border-gray-200 text-gray-500"
            : "bg-white border-gray-200"
        }`}
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium truncate">{event.title || event.summary}</div>
            <div className="text-xs text-gray-600">{timeStr}</div>

            {/* Compact origin link badges (ClickUp/Todoist/Reclaim) */}
            <LinkBadges event={event} />

            {/* Matched client chips */}
            <ContactChips event={event} />
          </div>

          {event.location && (
            <a
              href={event.location}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-indigo-600 hover:underline"
            >
              Open
            </a>
          )}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <section className="bg-white rounded-xl shadow p-4 h-full flex flex-col">
        <h2 className="text-lg font-bold mb-2">📅 Calendar</h2>
        <p className="text-sm text-red-600">{error}</p>
      </section>
    );
  }

  // Group events into fixed Morning → Afternoon → Evening order
  const buckets = events.reduce((acc, ev) => {
    const label = getPeriodLabel(new Date(ev.start));
    (acc[label] ||= []).push(ev);
    return acc;
  }, {});
  const orderedSections = ["Morning", "Afternoon", "Evening"].filter((l) => buckets[l]?.length);

  return (
    <section className="bg-white rounded-xl shadow p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-lg font-bold">📅 Calendar</h2>
        {onJoinNext && (
          <button
            onClick={() => onJoinNext(nextJoinable)}
            disabled={!nextJoinable || joinDisabled}
            className={`text-xs px-2 py-1 rounded border ${
              nextJoinable && !joinDisabled
                ? "bg-indigo-600 text-white border-indigo-600 hover:bg-indigo-700"
                : "bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed"
            }`}
            title={
              nextJoinable
                ? `Join: ${nextJoinable.title || "Next meeting"}`
                : "No upcoming meeting"
            }
          >
            Join next
          </button>
        )}
      </div>

      <div ref={containerRef} className="flex flex-col gap-3 overflow-y-auto grow pr-1">
        {events.length === 0 ? (
          <div className="text-sm text-gray-500 border border-dashed border-gray-300 rounded p-3">
            No events today. Use this time to clear Do Next or Email.
          </div>
        ) : (
          orderedSections.map((period) => {
            const periodEvents = buckets[period];
            return (
              <div key={period}>
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                  {period}
                </div>
                {periodEvents.map((event) => (
                  <div
                    key={event.id}
                    className={isNextAnchor(event) ? "next-event-anchor" : ""}
                  >
                    {isNextAnchor(event) && (
                      <div className="text-red-600 text-xs font-semibold mb-1">Now</div>
                    )}
                    {renderEvent(event)}
                  </div>
                ))}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
