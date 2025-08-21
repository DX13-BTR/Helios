// src/hooks/useHotkeys.js
import { useEffect, useRef } from "react";

/**
 * useHotkeys
 * - bindings: [{ combo: "1", handler: (e) => void, when?: () => boolean }]
 * - Ignores events when focused element is a text input/textarea/contenteditable unless binding sets .force=true
 */
export default function useHotkeys(bindings) {
  const bindingsRef = useRef(bindings);
  useEffect(() => { bindingsRef.current = bindings; }, [bindings]);

  useEffect(() => {
    function onKeyDown(e) {
      const el = document.activeElement;
      const isTyping =
        el && (["INPUT", "TEXTAREA"].includes(el.tagName) || el.isContentEditable);

      for (const b of bindingsRef.current || []) {
        if (e.key === b.combo &&
            (b.force || !isTyping) &&
            (typeof b.when !== "function" || b.when())) {
          b.handler(e);
          e.preventDefault();
          return;
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
