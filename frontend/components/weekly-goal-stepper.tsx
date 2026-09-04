import { Button } from "@/components/ui/button";

export function WeeklyGoalStepper({
  value,
  unit,
  onDecrement,
  onIncrement,
  decrementLabel,
  incrementLabel,
}: {
  value: number;
  unit: string;
  onDecrement: () => void;
  onIncrement: () => void;
  decrementLabel: string;
  incrementLabel: string;
}) {
  return (
    <div className="flex items-center gap-1 rounded-full bg-surface px-1.5 py-1 lg:gap-1 lg:py-1">
      <Button variant="ghost" onClick={onDecrement} aria-label={decrementLabel} className="h-7 w-7 rounded-full bg-card p-0 text-base font-semibold text-primary shadow-sm hover:bg-card lg:h-8 lg:w-8">
        –
      </Button>
      <div className="flex min-w-13 items-baseline justify-center gap-1 text-sm font-semibold text-primary lg:min-w-15 lg:text-base">
        <span className="font-mono">{value}</span>
        <span>{unit}</span>
      </div>
      <Button
        variant="ghost"
        onClick={onIncrement}
        aria-label={incrementLabel}
        className="h-7 w-7 rounded-full bg-primary p-0 text-base font-semibold text-primary-foreground hover:bg-primary lg:h-8 lg:w-8"
      >
        +
      </Button>
    </div>
  );
}
