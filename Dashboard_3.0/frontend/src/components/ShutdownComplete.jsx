import React from "react";

// src/components/ShutdownComplete.jsx
export default function ShutdownComplete() {
  return (
    <div className="flex flex-col justify-center items-center min-h-screen bg-purple-900 text-white">
        <h1 className="text-3xl font-bold">🌙 Helios has powered down</h1>
        <p className="text-lg text-white/70">All systems are now offline.</p>
        <p className="text-sm text-white/50">You can now close this window.</p>
      </div>
  );
}
