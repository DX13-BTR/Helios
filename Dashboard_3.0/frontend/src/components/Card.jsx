import React from "react";

export default function Card({ title, actions = null, children, className = "" }) {
  return (
    <section className={`bg-white rounded-xl shadow p-6 ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between mb-4">
          {title ? <h2 className="text-xl font-bold">{title}</h2> : <div />}
          {actions && <div className="flex gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}
