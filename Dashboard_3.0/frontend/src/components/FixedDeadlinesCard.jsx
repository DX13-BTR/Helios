import React from "react";

const LABEL = {
  vat_return: "VAT Return",
  payroll: "Payroll (EPS)",
  ct600: "CT600",
  cs01: "CS01",
  sa100: "SA100",
  sa800: "SA800",
  cis_return: "CIS Return",
};

function dd(iso) {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Europe/London",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

function daysUntil(iso) {
  const d = new Date(iso).getTime();
  const now = Date.now();
  return Math.ceil((d - now) / (1000 * 60 * 60 * 24));
}

function chipClass(n) {
  if (n < 0) return "bg-red-100 text-red-700";
  if (n <= 1) return "bg-red-50 text-red-700";
  if (n <= 3) return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-700";
}

export default function FixedDeadlinesCard({ items, loading, error, onRefresh }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <h3 className="text-lg font-semibold text-slate-900">Fixed Deadlines</h3>
        <button
          className="text-sm text-slate-600 hover:text-slate-900"
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <div className="p-4 text-sm text-red-700 bg-red-50">{error}</div>
      ) : items.length === 0 ? (
        <div className="p-4 text-sm text-slate-600">No fixed deadlines found.</div>
      ) : (
        <ul className="divide-y divide-slate-100">
          {items.map((t) => {
            const label = t.deadline_type ? LABEL[t.deadline_type] ?? t.deadline_type : "Fixed date";
            const days = daysUntil(t.fixed_date);
            return (
              <li key={t.id} className="px-4 py-3 hover:bg-slate-50">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate font-medium text-slate-900">{t.name}</div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {label} • {dd(t.fixed_date)}
                      {t.client_code ? <> • Client: {t.client_code}</> : null}
                    </div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${chipClass(days)}`}>
                    {days < 0 ? `${Math.abs(days)}d overdue` : `in ${days}d`}
                  </span>
                </div>
                {t.status ? <div className="mt-1 text-xs text-slate-500">Status: {t.status}</div> : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
