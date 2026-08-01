export type WeekStat = { value: string; label: string };
export type RecentRun = { day: string; time: string; distance: string; pace: string };
export type Goal = { title: string; pct: number };

export const mockWeekStats: WeekStat[] = [
  { value: "21.9", label: "km" },
  { value: "5:32", label: "avg /km" },
  { value: "4", label: "runs" },
];

export const mockRecentRuns: RecentRun[] = [
  { day: "Monday", time: "6:42 AM", distance: "6.1 km", pace: "5:28/km" },
  { day: "Wednesday", time: "6:15 AM", distance: "4.8 km", pace: "5:41/km" },
  { day: "Friday", time: "7:02 AM", distance: "5.5 km", pace: "5:30/km" },
  { day: "Sunday", time: "8:20 AM", distance: "5.5 km", pace: "5:29/km" },
];

export const mockGoals: Goal[] = [
  { title: "Run 30km this week", pct: 73 },
  { title: "Sub-25min 5K by Sept", pct: 40 },
];
