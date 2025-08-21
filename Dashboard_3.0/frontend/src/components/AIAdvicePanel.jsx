import React, { useEffect, useMemo, useRef, useState } from "react";

/**
 * AIAdvicePanel – single-source TTS:
 * - initialMessage only seeds the chat; it does NOT speak
 * - one effect speaks the latest agent message iff not spoken before
 * - Google TTS first (POST /api/voice/speak), browser TTS as fallback
 */

export default function AIAdvicePanel({
  urgentTasks = [],
  doNextTasks = [],
  emailTasks = [],
  personalTasks = [],
  initialMessage = null,
}) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Remember which messages we’ve already spoken (guards re-renders & StrictMode)
  const spokenIds = useRef(new Set());
  // Unlock audio at least once via user gesture
  const audioUnlockedRef = useRef(false);

  // ---- utils ----
  function ensureAudioUnlocked() {
    if (audioUnlockedRef.current) return;
    try {
      const el = new Audio();
      el.muted = true;
      el.play().catch(() => {});
      el.pause();
      audioUnlockedRef.current = true;
    } catch {}
  }
  useEffect(() => {
    const onFirst = () => { ensureAudioUnlocked(); document.removeEventListener("click", onFirst); };
    document.addEventListener("click", onFirst);
    return () => document.removeEventListener("click", onFirst);
  }, []);

  // Stable id for a message (text-based)
  function msgId(text) {
    // cheap stable hash
    let h = 0;
    for (let i = 0; i < (text || "").length; i++) h = (h * 31 + text.charCodeAt(i)) | 0;
    return String(h);
  }

  async function speak(text) {
    if (!text) return;

    // prevent overlaps from any previous queues
    try { window.speechSynthesis?.cancel(); } catch {}

    // 1) Try Google TTS via backend
    try {
      const res = await fetch("http://localhost:3333/api/voice/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, tone: "neutral", speaking_rate: 1.0, pitch: 0 }),
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        await audio.play().catch(() => {});
        return; // success
      }
    } catch (e) {
      // fall through to browser TTS
      console.warn("Google TTS failed; falling back to speechSynthesis.", e);
    }

    // 2) Fallback: browser TTS
    try {
      const u = new SpeechSynthesisUtterance(text);
      u.rate = 1;
      u.pitch = 1;
      u.volume = 1;
      window.speechSynthesis?.speak(u);
    } catch (e) {
      console.error("Fallback TTS failed", e);
    }
  }

  // ---- single TTS path: speak latest agent message once ----
  const lastAgent = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].from === "agent") return messages[i];
    }
    return null;
  }, [messages]);

  useEffect(() => {
    if (!lastAgent) return;
    const id = lastAgent.id || msgId(lastAgent.text);
    if (spokenIds.current.has(id)) return;     // already spoken
    spokenIds.current.add(id);
    speak(lastAgent.text);
  }, [lastAgent]);

  // ---- send message ----
  async function sendMessage() {
    const content = input.trim();
    if (!content || loading) return;

    const userMsg = { from: "user", text: content, id: msgId(`u:${content}`) };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    // Build context
    const annotate = (tasks, emoji) => tasks.map((t) => ({ ...t, source: emoji }));
    const combined = [
      ...annotate(urgentTasks, "🚨"),
      ...annotate(doNextTasks, "✅"),
      ...annotate(emailTasks, "📥"),
      ...annotate(personalTasks, "👤"),
    ];

    // Convert current messages to history for backend
    const history = messages.map((m) => ({
      role: m.from === "agent" ? "assistant" : "user",
      content: m.text,
    }));

    try {
      const res = await fetch("http://localhost:3333/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [{ role: "user", content }],
          history,
          task_context: combined,
        }),
      });
      const data = await res.json();
      const reply = data?.reply?.content || "I didn't get a response.";
      const agentMsg = { from: "agent", text: reply, id: msgId(reply) };
      setMessages((prev) => [...prev, agentMsg]); // speaking handled by effect
    } catch (e) {
      console.error("sendMessage failed", e);
      setError("Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-3 mb-4">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`p-3 rounded-lg text-sm whitespace-pre-line ${
              m.from === "user" ? "bg-blue-100 text-blue-900 self-end" : "bg-gray-100 text-gray-800 self-start"
            }`}
          >
            {m.text}
          </div>
        ))}
        {loading && <p className="text-xs text-gray-500 italic">Thinking…</p>}
        {error && <p className="text-xs text-red-500 italic">{error}</p>}
      </div>

      <div className="mt-auto">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask Helios for guidance…"
          rows={2}
          className="w-full border rounded p-2 text-sm mb-2"
        />
        <button
          onClick={sendMessage}
          className="w-full bg-purple-700 text-white py-2 rounded text-sm"
          disabled={loading || !input.trim()}
        >
          ➤ Ask AI
        </button>
      </div>
    </div>
  );
}
