"use client";

import { useEffect } from "react";

export function RegisterServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;

    // Dev-only: unregister any previously-registered SW so cached chunks
    // from an earlier session can't mask live code changes. Turbopack dev
    // builds don't reliably change chunk URLs per rebuild the way
    // production's content-hashed build does, so a cache-first SW here
    // silently serves stale JS indefinitely.
    if (process.env.NODE_ENV !== "production") {
      navigator.serviceWorker.getRegistrations().then((regs) => {
        regs.forEach((reg) => reg.unregister());
      });
      return;
    }

    navigator.serviceWorker.register("/sw.js").catch((error) => {
      console.error("Service worker registration failed:", error);
    });
  }, []);

  return null;
}
