// src/modules/fss/FSSDashboard.jsx
import React, { useEffect, useState } from "react";
import DashboardLayout from "../../components/DashboardLayout.jsx";
import Card from "../../components/Card.jsx";
import Button from "../../components/Button.jsx";
import { API_BASE } from "../../config"; // unchanged

export default function FSSDashboard() {
  const [balances, setBalances] = useState(null);
  const [advice, setAdvice] = useState(null);     // can be object/string/array
  const [adviceRaw, setAdviceRaw] = useState(null); // raw payload for debugging
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAdviceDebug, setShowAdviceDebug] = useState(false);

  const currency = (val) => `£${Number(val ?? 0).toFixed(2)}`;

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);

        const [bRes, aRes, sRes] = await Promise.all([
          fetch(`${API_BASE}/balances/current`),
          fetch(`${API_BASE}/latest`),
          fetch(`${API_BASE}/fss/summary/latest`),
        ]);

        const [b, a, s] = await Promise.all([
          bRes.ok ? bRes.json() : null,
          aRes.ok ? aRes.json() : null,
          sRes.ok ? sRes.json() : null,
        ]);

        setBalances(b);
        setAdviceRaw(a);

        // Normalize advice to something renderable
        if (a == null) {
          setAdvice(null);
        } else if (typeof a === "string") {
          setAdvice({ text: a });
        } else if (Array.isArray(a)) {
          setAdvice({ items: a });
        } else if (typeof a === "object") {
          // keep as-is; renderer will handle both the ideal and generic cases
          setAdvice(a);
        } else {
          setAdvice({ text: String(a) });
        }

        setSummary(s);
      } catch (err) {
        console.error("FSS fetch failed:", err);
        setAdvice(null);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    const id = setInterval(fetchData, 60_000);
    return () => clearInterval(id);
  }, []);

  return (
    <DashboardLayout
      scorecard={null}
      onShutdown={() => console.log("FSS: shutdown clicked")}
      onJoinNext={() => {}}
      showCalendar={false}
    >
      <Card
        title="Financial Safety Snapshot"
        actions={<Button variant="ghost" size="sm" onClick={() => window.location.reload()}>⟳ Refresh</Button>}
      >
        {!summary ? (
          <div className="text-sm text-gray-600">Loading summary…</div>
        ) : (
          <div className="space-y-1 text-sm">
            <div className="rounded-lg border p-3" style={{ backgroundColor: summary.uc_safe ? "#f0fff0" : "#fff0f0" }}>
              <p>UC Safe: {summary.uc_safe ? "✅ Yes" : "❌ No"} (Entitlement {currency(summary.uc_entitlement)})</p>
              <p>Buffer: {Number(summary.buffer_pct).toFixed(1)}% ({currency(summary.total_balance)})</p>
              <p>Tee Covered: {summary.tee_covered ? "✅" : "❌"} (Paid {currency(summary.tee_paid)})</p>
              <p>Drawdown Available: {currency(summary.drawdown_available)}</p>
              <p>Suggested Pay: {currency(summary.suggested_pay)}</p>
              <p>Suggested Savings: {currency(summary.suggested_savings)}</p>
            </div>
          </div>
        )}
      </Card>

      <Card title="Bank Balances">
        {!balances ? (
          <div className="text-sm text-gray-600">Loading balances…</div>
        ) : (
          <div className="grid md:grid-cols-2 gap-4">
            {["efkaristo", "personal"].map((accountKey) => {
              const snapshot = balances[accountKey];
              const label = accountKey === "efkaristo" ? "Company (Efkaristo)" : "Personal";
              const grouped = snapshot?.by_space?.filter((row) => row.account?.toLowerCase() === accountKey) || [];

              return (
                <div key={accountKey} className="rounded-xl border p-4 flex flex-col gap-2">
                  <div>
                    <h3 className="font-semibold mb-1">{label}</h3>
                    <p className="text-xs text-gray-600 mb-2">
                      <strong>Timestamp:</strong>{" "}
                      {snapshot?.timestamp
                        ? new Date(snapshot.timestamp).toLocaleString(undefined, { timeZoneName: "short" })
                        : <em className="text-gray-400">Unavailable</em>}
                    </p>

                    {grouped.length > 0 ? (
                      <ul className="list-disc pl-5 space-y-1 text-sm">
                        {grouped.map((space, idx) => (
                          <li key={idx}>
                            {space.space}: <strong>{currency(space.balance)}</strong>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="italic text-gray-500 text-sm">No sub-balances</p>
                    )}
                  </div>

                  <p className="font-semibold mt-auto">Account Total: {currency(snapshot?.by_account?.[accountKey])}</p>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card
        title="Latest Advice"
        actions={
          advice && !hasIdealAdvice(advice) ? (
            <Button variant="ghost" size="sm" onClick={() => setShowAdviceDebug((s) => !s)}>
              {showAdviceDebug ? "Hide payload" : "Show payload"}
            </Button>
          ) : null
        }
      >
        <AdviceRenderer advice={advice} loading={loading} />

        {/* Debug raw payload when advice doesn't match ideal shape */}
        {advice && !hasIdealAdvice(advice) && showAdviceDebug && (
          <div className="mt-3">
            <div className="text-xs text-gray-600 mb-1">/latest raw payload</div>
            <pre className="text-xs bg-gray-100 rounded-lg p-3 overflow-auto max-h-64">
              {safeStringify(adviceRaw)}
            </pre>
          </div>
        )}
      </Card>
    </DashboardLayout>
  );
}

/* ---------- Advice rendering helpers ---------- */
function hasIdealAdvice(a) {
  return a && typeof a === "object" &&
    ("uc" in a || "buffer" in a || "tee" in a || "spending" in a || "savings" in a);
}

function AdviceRenderer({ advice, loading }) {
  if (loading && advice == null) return <div className="text-sm text-gray-600">Loading advice…</div>;
  if (advice == null) return <div className="text-sm text-gray-600">No advice available.</div>;

  // Ideal (fielded) advice
  if (hasIdealAdvice(advice)) {
    return (
      <div className="rounded-xl border p-4 space-y-1 text-sm">
        {"uc" in advice && <p><strong>UC:</strong> {advice.uc}</p>}
        {"buffer" in advice && <p><strong>Buffer:</strong> {advice.buffer}</p>}
        {"tee" in advice && <p><strong>Tee:</strong> {advice.tee}</p>}
        {"spending" in advice && <p><strong>Spending:</strong> {advice.spending}</p>}
        {"savings" in advice && <p><strong>Savings:</strong> {advice.savings}</p>}
      </div>
    );
  }

  // Single string
  if (typeof advice.text === "string") {
    return (
      <div className="rounded-xl border p-4 text-sm whitespace-pre-wrap">
        {advice.text}
      </div>
    );
  }

  // Array of items
  if (Array.isArray(advice.items)) {
    return (
      <ul className="rounded-xl border p-4 text-sm list-disc pl-5 space-y-1">
        {advice.items.map((x, i) => <li key={i}>{typeof x === "string" ? x : safeStringify(x)}</li>)}
      </ul>
    );
  }

  // Fallback: generic object
  return (
    <div className="rounded-xl border p-4 text-sm">
      <div className="text-gray-700 mb-2">Advice payload (unrecognized shape):</div>
      <pre className="text-xs bg-gray-100 rounded-lg p-3 overflow-auto max-h-64">{safeStringify(advice)}</pre>
    </div>
  );
}

function safeStringify(x) {
  try { return JSON.stringify(x, null, 2); } catch { return String(x); }
}
