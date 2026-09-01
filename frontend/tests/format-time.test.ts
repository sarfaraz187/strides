import { describe, expect, it } from "vitest";

import { formatMessageTime } from "../lib/format-time";

function clockTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

describe("formatMessageTime", () => {
  const now = new Date("2026-09-01T20:00:00Z").getTime();

  it("shows a bare clock time for today", () => {
    const iso = "2026-09-01T12:11:00Z";
    expect(formatMessageTime(iso, now)).toBe(clockTime(iso));
  });

  it("prefixes 'Yesterday' for the previous calendar day", () => {
    const iso = "2026-08-31T12:11:00Z";
    expect(formatMessageTime(iso, now)).toBe(`Yesterday ${clockTime(iso)}`);
  });

  it("shows month/day + time for older same-year dates", () => {
    const iso = "2026-08-14T12:11:00Z";
    expect(formatMessageTime(iso, now)).toBe(`Aug 14, ${clockTime(iso)}`);
  });

  it("shows year for dates in a previous year", () => {
    const iso = "2025-08-14T12:11:00Z";
    expect(formatMessageTime(iso, now)).toBe(`Aug 14, 2025, ${clockTime(iso)}`);
  });
});
