import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function RunCard({ title, subtitle, leading, trailing, className }: { title: string; subtitle: string; leading?: React.ReactNode; trailing?: React.ReactNode; className?: string }) {
  return (
    <Card className={cn("flex flex-row items-center justify-between rounded-2xl p-4 lg:px-5 lg:py-5", className)}>
      <div className="flex items-center gap-3">
        {leading}
        <div>
          <div className="text-sm font-semibold text-primary">{title}</div>
          <div className="text-xs text-muted-light">{subtitle}</div>
        </div>
      </div>
      {trailing}
    </Card>
  );
}
