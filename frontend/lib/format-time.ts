const DAY_MS = 24 * 60 * 60 * 1000;

export function formatMessageTime(isoTimestamp: string, now: number = Date.now()): string {
  const then = new Date(isoTimestamp);
  const nowDate = new Date(now);
  const time = then.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });

  const isSameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (isSameDay(then, nowDate)) return time;

  const yesterday = new Date(now - DAY_MS);
  if (isSameDay(then, yesterday)) return `Yesterday ${time}`;

  const sameYear = then.getFullYear() === nowDate.getFullYear();
  const datePart = then.toLocaleDateString("en-US", sameYear ? { month: "short", day: "numeric" } : { month: "short", day: "numeric", year: "numeric" });
  return `${datePart}, ${time}`;
}
