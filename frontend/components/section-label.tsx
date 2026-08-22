import { cn } from "@/lib/utils";

export function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("text-sm font-semibold uppercase text-muted", className)}>{children}</div>;
}
