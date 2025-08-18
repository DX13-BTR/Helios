import React, { useEffect, useMemo, useRef, useState } from "react";
import DashboardLayout from "../components/DashboardLayout";
import Card from "../components/Card";
import Button from "../components/Button";

/** JSDoc typedefs for editor hints */
/** @typedef {{ domain:string, wildcard:boolean }} ClientDomain */
/** @typedef {{ id:number, name:string, notes?:string, phone?:string, tags?:string[], emails:string[], domains:ClientDomain[], active:boolean, created_at?:string, updated_at?:string }} Client */
/** @typedef {{ id:number, email:string, last_seen:string, hits:number, subject?:string, resolved?:boolean }} UnknownSender */

const API_BASE = (import.meta?.env?.VITE_API_BASE) ?? "http://127.0.0.1:3333";
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const cn = (...xs) => xs.filter(Boolean).join(" ");
const useDebounced = (value, delay = 250) => {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), delay); return () => clearTimeout(t); }, [value, delay]);
  return v;
};

function Pill({ children, tone = "neutral" }) {
  const tones = {
    neutral: "bg-gray-100 text-gray-700",
    green: "bg-green-100 text-green-800",
    purple: "bg-purple-100 text-purple-800",
  };
  return <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-xs", tones[tone])}>{children}</span>;
}
function EmptyState({ title = "Nothing here", subtitle = "" }) {
  return (
    <div className="text-center text-sm text-gray-500 py-8 border border-dashed border-gray-300 rounded-xl">
      <div className="font-medium text-gray-700 mb-1">{title}</div>
      {subtitle && <div className="text-gray-500">{subtitle}</div>}
    </div>
  );
}

export default function ContactsPage() {
  const [query, setQuery] = useState("");
  const q = useDebounced(query, 250);

  const [clients, setClients] = useState(/** @type {Client[]} */([]));
  const [loading, setLoading] = useState(true);
  const [drawer, setDrawer] = useState({ open: false, client: /** @type {Client|null} */(null) });
  const [unknown, setUnknown] = useState(/** @type {UnknownSender[]} */([]));
  const [allowVer, setAllowVer] = useState(null);
  const [activeOnly, setActiveOnly] = useState(true);

  const [toasts, setToasts] = useState([]);
  const toastId = useRef(1);
  const pushToast = (text, tone = "ok") => {
    const id = toastId.current++;
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200);
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [cs, us, al] = await Promise.all([
        apiListClients(q),
        apiListUnknownSenders(false),
        apiGetAllowlistVersion(),
      ]);
      setClients(cs);
      setUnknown(us);
      setAllowVer(al);
    } catch (e) {
      pushToast(`Failed to load: ${e?.message || e}`, "err");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { fetchAll(); /* eslint-disable-next-line */ }, [q]);

  const handleNew = () => {
    setDrawer({ open: true, client: { id: 0, name: "", notes: "", phone: "", tags: [], emails: [], domains: [], active: true } });
  };

  const refreshUnknownAndAllow = async () => {
    try {
      const [us, al] = await Promise.all([apiListUnknownSenders(false), apiGetAllowlistVersion()]);
      setUnknown(us); setAllowVer(al);
    } catch (e) { pushToast(`Refresh failed: ${e?.message || e}`, "err"); }
  };

  const filteredClients = useMemo(() => clients.filter(c => (activeOnly ? c.active : true)), [clients, activeOnly]);

  return (
    <DashboardLayout
      scorecard={null}
      onShutdown={() => console.log("Shutdown via layout")}
      onJoinNext={() => {}}
      showCalendar={false} // hide calendar + expand layout
    >
      <Card
        title="Contacts"
        actions={(
          <div className="flex items-center gap-2">
            <div className="hidden sm:flex items-center gap-2">
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search clients…"
                className="w-64 rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring focus:border-purple-300"
              />
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} /> Active only
              </label>
            </div>
            <Button variant="ghost" size="sm" onClick={fetchAll}>⟳ Refresh</Button>
            <Button size="sm" onClick={handleNew}>＋ New Client</Button>
          </div>
        )}
        className="p-4"
      >
        <div className="flex flex-col lg:flex-row gap-4">
          <div className="flex-1">
            <ClientsTable
              loading={loading}
              clients={filteredClients}
              onRowClick={(c) => setDrawer({ open: true, client: c })}
            />
          </div>

          <div className="w-full lg:w-[360px]">
            <Card
              title={"Unknown Senders"}
              actions={<span className="text-xs text-gray-500">Allowlist v{allowVer?.version ?? "-"}</span>}
              className="p-4"
            >
              <UnknownSendersPanel
                items={unknown}
                clients={clients}
                onItemsChange={setUnknown}           // NEW: allow optimistic removal
                onActionDone={async () => { await refreshUnknownAndAllow(); pushToast("Queue updated"); }}
                onError={(msg) => pushToast(msg, "err")}
              />
            </Card>
          </div>
        </div>
      </Card>

      {drawer.open && (
        <ClientDrawer
          client={drawer.client}
          onClose={() => setDrawer({ open: false, client: null })}
          onSaved={(saved) => {
            setClients((prev) => {
              const idx = prev.findIndex((x) => x.id === saved.id);
              if (idx >= 0) { const copy = prev.slice(); copy[idx] = saved; return copy; }
              return [saved, ...prev];
            });
            setDrawer({ open: false, client: null });
            pushToast("Saved");
          }}
          onDeleted={(id) => {
            setClients((prev) => prev.filter((x) => x.id !== id));
            setDrawer({ open: false, client: null });
            pushToast("Client deactivated");
          }}
        />
      )}

      <div className="fixed bottom-4 right-4 z-50 space-y-2">
        {toasts.map((t) => (
          <div key={t.id} className={cn("rounded-xl px-4 py-3 shadow-md text-sm", t.tone === "ok" ? "bg-emerald-600 text-white" : "bg-rose-600 text-white")}>{t.text}</div>
        ))}
      </div>
    </DashboardLayout>
  );
}

/* ---------- ClientsTable (unchanged visuals) ---------- */
function ClientsTable({ loading, clients, onRowClick }) {
  const [page, setPage] = useState(0);
  const pageSize = 15;
  const totalPages = Math.max(1, Math.ceil(clients.length / pageSize));
  useEffect(() => { if (page > totalPages - 1) setPage(0); }, [clients.length]);
  const pageItems = useMemo(() => clients.slice(page * pageSize, page * pageSize + pageSize), [clients, page]);

  if (loading) return <EmptyState title="Loading…" subtitle="Fetching clients from API" />;
  if (!pageItems.length) return <EmptyState title="No clients" subtitle="Create a client to get started." />;

  return (
    <div className="bg-white rounded-xl shadow border border-gray-100 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr className="text-left text-xs text-gray-500">
              <Th>Client Name</Th>
              <Th>Primary Email(s)</Th>
              <Th>Allowed Domains</Th>
              <Th>Phone</Th>
              <Th>Notes</Th>
              <Th>Active</Th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((c, i) => (
              <tr key={c.id} className={cn("border-b hover:bg-gray-50 cursor-pointer", i % 2 === 1 && "bg-gray-50/40")} onClick={() => onRowClick(c)}>
                <Td className="font-medium text-gray-900">{c.name || <span className="text-gray-400">(unnamed)</span>}</Td>
                <Td>{c.emails?.length ? <div className="flex flex-wrap gap-1">{c.emails.map((em) => <Pill key={em} tone="purple">{em}</Pill>)}</div> : <span className="text-gray-400">—</span>}</Td>
                <Td>{c.domains?.length ? <div className="flex flex-wrap gap-1">{c.domains.map((d, idx) => <Pill key={idx}>{d.wildcard ? `*.${d.domain.replace(/^\*\./, "")}` : d.domain}</Pill>)}</div> : <span className="text-gray-400">—</span>}</Td>
                <Td>{c.phone || <span className="text-gray-400">—</span>}</Td>
                <Td><span className="inline-block max-w-[28ch] truncate align-bottom" title={c.notes || ""}>{c.notes || <span className="text-gray-400">—</span>}</span></Td>
                <Td><span className="inline-flex items-center gap-1 text-xs"><span className={cn("inline-block h-2 w-2 rounded-full", c.active ? "bg-emerald-500" : "bg-gray-400")} /><span className={cn(c.active ? "text-emerald-700" : "text-gray-500")}>{c.active ? "Active" : "Inactive"}</span></span></Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t p-2 flex items-center justify-between text-xs bg-white">
        <div>Page {page + 1} of {totalPages}</div>
        <div className="space-x-2">
          <Button variant="ghost" size="sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>Prev</Button>
          <Button variant="ghost" size="sm" onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>Next</Button>
        </div>
      </div>
    </div>
  );
}
function Th({ children }) { return <th className="px-3 py-2 font-medium">{children}</th>; }
function Td({ children, className = "" }) { return <td className={cn("px-3 py-2 align-top", className)}>{children}</td>; }

/* ---------- ClientDrawer (unchanged logic) ---------- */
function ClientDrawer({ client, onClose, onSaved, onDeleted }) {
  const [draft, setDraft] = useState(client);
  const [busy, setBusy] = useState(false);
  const isCreate = client.id === 0;

  useEffect(() => setDraft(client), [client]);

  const [emailInput, setEmailInput] = useState("");
  const [domainInput, setDomainInput] = useState("");
  const [wildcard, setWildcard] = useState(false);
  const [tagInput, setTagInput] = useState("");

  const save = async () => {
    if (!draft.name?.trim()) return alert("Name is required");
    setBusy(true);
    try {
      const saved = isCreate ? await apiCreateClient(draft) : await apiUpdateClient(draft.id, draft);
      onSaved(saved);
    } catch (e) { alert(e?.message || "Save failed"); }
    finally { setBusy(false); }
  };

  const deactivate = async () => {
    if (!confirm("Deactivate this client?")) return;
    setBusy(true);
    try { await apiDeleteClient(draft.id); onDeleted(draft.id); }
    catch (e) { alert(e?.message || "Delete failed"); }
    finally { setBusy(false); }
  };

  const addEmail = () => {
    const email = emailInput.trim();
    if (!emailRegex.test(email)) return alert("Invalid email format");
    if (draft.emails.includes(email)) return alert("Email already added");
    setDraft({ ...draft, emails: [...draft.emails, email] });
    setEmailInput("");
  };
  const addDomain = () => {
    const domain = domainInput.trim().replace(/^\*\./, "");
    if (!domain) return alert("Domain required");
    if (draft.domains.some((d) => d.domain === domain && d.wildcard === wildcard)) return alert("Domain already added with same wildcard");
    setDraft({ ...draft, domains: [...draft.domains, { domain, wildcard }] });
    setDomainInput("");
  };

  const removeEmail = (em) => setDraft({ ...draft, emails: draft.emails.filter((e) => e !== em) });
  const removeDomain = (i) => setDraft({ ...draft, domains: draft.domains.filter((_, idx) => idx !== i) });
  const removeTag = (i) => setDraft({ ...draft, tags: (draft.tags || []).filter((_, idx) => idx !== i) });
  const addTag = () => { const t = tagInput.trim(); if (!t) return; setDraft({ ...draft, tags: [...(draft.tags || []), t] }); setTagInput(""); };

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="w-[600px] max-w-full bg-white h-full shadow-2xl p-5 overflow-auto">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-lg font-semibold mr-auto">{isCreate ? "New Client" : "Edit Client"}</h2>
          <Button variant="ghost" onClick={onClose}>Close</Button>
          {!isCreate && (<Button variant="danger" onClick={deactivate} disabled={busy}>Deactivate</Button>)}
          <Button onClick={save} disabled={busy}>Save</Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-3">
            <LabeledInput label="Name" value={draft.name} onChange={(v) => setDraft({ ...draft, name: v })} required />
            <LabeledInput label="Phone" value={draft.phone || ""} onChange={(v) => setDraft({ ...draft, phone: v })} />
            <LabeledTextarea label="Notes" value={draft.notes || ""} onChange={(v) => setDraft({ ...draft, notes: v })} rows={5} />

            <div>
              <div className="text-xs font-medium text-gray-600 mb-1">Tags</div>
              <div className="flex items-center gap-2 mb-2">
                <input value={tagInput} onChange={(e) => setTagInput(e.target.value)} className="border rounded-md px-3 py-2 text-sm flex-1" placeholder="Add tag…" onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())} />
                <Button variant="ghost" size="sm" onClick={addTag}>Add</Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {(draft.tags || []).map((t, i) => (
                  <span key={i} className="inline-flex items-center gap-1 text-xs bg-gray-100 px-2 py-1 rounded-full">
                    {t}
                    <button className="ml-1 text-gray-500 hover:text-black" onClick={() => removeTag(i)} title="Remove">×</button>
                  </span>
                ))}
                {(draft.tags || []).length === 0 && <span className="text-xs text-gray-400">No tags</span>}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <div className="text-xs font-medium text-gray-600 mb-1">Emails</div>
              <div className="flex gap-2 mb-2">
                <input value={emailInput} onChange={(e) => setEmailInput(e.target.value)} className="border rounded-md px-3 py-2 text-sm flex-1" placeholder="user@domain.com" onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addEmail())} />
                <Button variant="ghost" size="sm" onClick={addEmail}>Add</Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {draft.emails.map((em) => (
                  <span key={em} className="inline-flex items-center gap-1 text-xs bg-gray-100 px-2 py-1 rounded-full">
                    {em}
                    <button className="ml-1 text-gray-500 hover:text-black" onClick={() => removeEmail(em)} title="Remove">×</button>
                  </span>
                ))}
                {draft.emails.length === 0 && <span className="text-xs text-gray-400">No emails</span>}
              </div>
            </div>

            <div>
              <div className="text-xs font-medium text-gray-600 mb-1">Allowed Domains</div>
              <div className="flex flex-col gap-2 mb-2">
                <div className="flex gap-2 items-center">
                  <input value={domainInput} onChange={(e) => setDomainInput(e.target.value)} className="border rounded-md px-3 py-2 text-sm flex-1" placeholder="example.com (no *.)" onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addDomain())} />
                  <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={wildcard} onChange={(e) => setWildcard(e.target.checked)} /> wildcard</label>
                  <Button variant="ghost" size="sm" onClick={addDomain}>Add</Button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {draft.domains.map((d, i) => (
                  <span key={i} className="inline-flex items-center gap-1 text-xs bg-gray-100 px-2 py-1 rounded-full">
                    {d.wildcard ? `*.${d.domain}` : d.domain}
                    <button className="ml-1 text-gray-500 hover:text-black" onClick={() => removeDomain(i)} title="Remove">×</button>
                  </span>
                ))}
                {draft.domains.length === 0 && <span className="text-xs text-gray-400">No domains</span>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
function LabeledInput({ label, value, onChange, type = "text", required = false }) {
  return (
    <label className="block">
      <div className="text-xs font-medium text-gray-600 mb-1">{label} {required && <span className="text-rose-600">*</span>}</div>
      <input type={type} className="border rounded-md px-3 py-2 text-sm w-full" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
function LabeledTextarea({ label, value, onChange, rows = 4 }) {
  return (
    <label className="block">
      <div className="text-xs font-medium text-gray-600 mb-1">{label}</div>
      <textarea className="border rounded-md px-3 py-2 text-sm w-full" rows={rows} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/* ---------- UnknownSendersPanel (UPDATED) ---------- */
function UnknownSendersPanel({
  items,
  clients,
  onItemsChange,     // NEW: for optimistic updates
  onActionDone,
  onError,
}) {
  const [busyId, setBusyId] = useState(null);
  const [clientPick, setClientPick] = useState("");
  const [wild, setWild] = useState(true);

  async function doResolve(item, action) {
    try {
      setBusyId(item.id);

      // Optimistic remove when ignoring
      if (action === "ignore" && Array.isArray(items) && typeof onItemsChange === "function") {
        onItemsChange(items.filter(x => x.id !== item.id));
      }

      let payload;
      if (action === "ignore") {
        payload = { action: "ignore" };
      } else if (action === "approve_email") {
        if (!clientPick) return onError("Pick a client first");
        payload = { action: "approve_email", client_id: Number(clientPick) };
      } else if (action === "approve_domain") {
        if (!clientPick) return onError("Pick a client first");
        const domain = item.email.split("@")[1]?.trim();
        if (!domain) return onError("Cannot parse domain");
        payload = { action: "approve_domain", client_id: Number(clientPick), domain, wildcard: !!wild };
      }

      const res = await fetch(`${API_BASE}/api/unknown-senders/${item.id}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        throw new Error(`Resolve failed (${res.status}): ${errText || res.statusText}`);
      }

      await onActionDone();
    } catch (e) {
      onError(e?.message || "Resolve failed");
    } finally {
      setBusyId(null);
    }
  }

  if (!items?.length) return <EmptyState title="No unknown senders" subtitle="You're all clear for now." />;

  return (
    <ul className="space-y-3">
      {items.map((it) => (
        <li key={it.id} className="rounded-lg border p-3 bg-white">
          <div className="flex items-start gap-2">
            <div className="font-mono text-xs bg-gray-100 px-2 py-1 rounded">{it.email}</div>
            <div className="ml-auto text-[11px] text-gray-500">{new Date(it.last_seen).toLocaleString()}</div>
          </div>
          {it.subject && <div className="mt-1 text-xs text-gray-600 truncate" title={it.subject}>subj: {it.subject}</div>}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              className="border rounded-md px-2 py-1 text-xs"
              value={clientPick}
              onChange={(e) => setClientPick(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Select client…</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.name || `(id:${c.id})`}</option>)}
            </select>
            <Button variant="ghost" size="sm" disabled={busyId === it.id} onClick={() => doResolve(it, "approve_email")}>Approve Email</Button>
            <label className="text-[11px] flex items-center gap-1 ml-1">
              <input type="checkbox" checked={wild} onChange={(e) => setWild(e.target.checked)} /> wildcard
            </label>
            <Button variant="ghost" size="sm" disabled={busyId === it.id} onClick={() => doResolve(it, "approve_domain")}>Approve Domain</Button>
            <Button variant="danger" size="sm" disabled={busyId === it.id} onClick={() => doResolve(it, "ignore")}>Ignore</Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ---------- API ---------- */
async function handle(res) {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(msg);
  }
  return res.json();
}
async function apiListClients(q) {
  const url = new URL(`/api/clients`, API_BASE);
  if (q?.trim()) url.searchParams.set("q", q.trim());
  return handle(await fetch(url.toString()));
}
async function apiCreateClient(payload) {
  return handle(await fetch(`${API_BASE}/api/clients`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }));
}
async function apiUpdateClient(id, patch) {
  return handle(await fetch(`${API_BASE}/api/clients/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }));
}
async function apiDeleteClient(id) {
  return handle(await fetch(`${API_BASE}/api/clients/${id}`, { method: "DELETE" }));
}
async function apiListUnknownSenders(resolved = false) {
  const url = new URL(`/api/unknown-senders`, API_BASE);
  url.searchParams.set("resolved", String(resolved));
  return handle(await fetch(url.toString()));
}
async function apiGetAllowlistVersion() {
  return handle(await fetch(`${API_BASE}/api/allowlist`));
}
