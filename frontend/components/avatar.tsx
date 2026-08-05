import { cn } from "@/lib/utils";

export function initialsFromName(name: string | null): string {
  if (!name) return "?";
  const words = name.trim().split(/\s+/).slice(0, 2);
  return words.map((word) => word[0]?.toUpperCase()).join("") || "?";
}

const SIZE_CLASSES = {
  sm: "h-8 w-8 text-xs",
  md: "h-9 w-9 text-[13px]",
  lg: "h-14 w-14 text-lg lg:h-16 lg:w-16 lg:text-xl",
};

export function Avatar({
  user,
  size,
  className,
}: {
  user: { name: string | null; avatar_url: string | null };
  size: "sm" | "md" | "lg";
  className?: string;
}) {
  if (user.avatar_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={user.avatar_url}
        alt={user.name ?? "Profile picture"}
        className={cn("flex-none rounded-full object-cover", SIZE_CLASSES[size], className)}
      />
    );
  }

  return (
    <div
      className={cn(
        "flex flex-none items-center justify-center rounded-full bg-avatar-bg font-semibold text-primary",
        SIZE_CLASSES[size],
        className
      )}
    >
      {initialsFromName(user.name)}
    </div>
  );
}
