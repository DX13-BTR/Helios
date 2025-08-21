import React from "react";

/**
 * Skeleton
 * - Lightweight Tailwind-based skeleton loader.
 * - Props:
 *   - lines: number of text lines (default 3)
 *   - className: extra classes for sizing/placement
 *   - rounded: tailwind radius (default "rounded-lg")
 */
export default function Skeleton({ lines = 3, className = "", rounded = "rounded-lg" }) {
  return (
    <div className={`animate-pulse ${className}`}>
      {[...Array(lines)].map((_, i) => (
        <div key={i} className={`mb-2 last:mb-0 ${rounded} bg-gray-200 h-4`} />
      ))}
    </div>
  );
}
