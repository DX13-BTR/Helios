import React from "react";

export default function Splash() {
  return (
    <div className="flex items-center justify-center h-screen bg-[#0b0b0e] flex-col text-white">
      <video
        src="/helios-loader.webm"
        autoPlay
        loop
        muted
        className="w-[640px] h-[640px] mb-6"
      />
      <h1 className="text-xl font-medium tracking-wider text-white/70">
        Launching Helios...
      </h1>
    </div>
  );
}
