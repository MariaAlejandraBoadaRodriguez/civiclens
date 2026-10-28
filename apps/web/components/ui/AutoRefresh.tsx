"use client";

import { useEffect } from "react";
import { useRouter } from "@/i18n/routing";

/** Re-render the server page every `seconds` (cold-start / still-processing states). */
export function AutoRefresh({ seconds = 5, maxTries = 24 }: { seconds?: number; maxTries?: number }) {
  const router = useRouter();
  useEffect(() => {
    let tries = 0;
    const id = setInterval(() => {
      tries += 1;
      if (tries > maxTries) clearInterval(id);
      else router.refresh();
    }, seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds, maxTries]);
  return null;
}
