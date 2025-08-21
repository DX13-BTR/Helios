import React from "react";

/**
 * Variants: primary, danger, ghost
 * Sizes: sm, md
 */
const base =
  "inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2";
const variants = {
  primary: "bg-purple-700 text-white hover:bg-purple-800 focus:ring-purple-600",
  danger: "bg-red-700 text-white hover:bg-red-800 focus:ring-red-600",
  ghost: "bg-transparent text-gray-700 hover:bg-gray-100 focus:ring-gray-300 border border-gray-300",
};
const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
};

export default function Button({ children, variant = "primary", size = "md", className = "", ...props }) {
  return (
    <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props}>
      {children}
    </button>
  );
}
