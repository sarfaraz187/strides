// frontend/lib/goal-progress.ts

export function computeGoalProgress(doneKm: number, goalKm: number): { toGoKm: number; goalPct: number } {
  const toGoKm = Math.max(0, goalKm - doneKm);
  const goalPct = goalKm > 0 ? Math.min(100, Math.round((doneKm / goalKm) * 100)) : 0;
  return { toGoKm, goalPct };
}
