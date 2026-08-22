import { cn } from "@/lib/utils";

export function initialsFromName(name: string | null): string {
  if (!name) return "?";
  const words = name.trim().split(/\s+/).slice(0, 2);
  return words.map((word) => word[0]?.toUpperCase()).join("") || "?";
}

const SIZE_CLASSES = {
  sm: "h-8 w-8 text-xs",
  md: "h-9 w-9 text-sm",
  lg: "h-14 w-14 text-lg lg:h-16 lg:w-16 lg:text-xl",
};

// Matches the base (mobile) pixel size of each SIZE_CLASSES entry above, so
// the browser can reserve layout space before the image loads instead of
// shifting content once it decodes.
const SIZE_PX = { sm: 32, md: 36, lg: 56 };

export function Avatar({
  user,
  size,
  className,
}: {
  user: { name: string | null; avatar_url: string | null } | null;
  size: "sm" | "md" | "lg";
  className?: string;
}) {
  const name = user?.name ?? null;
  const avatarUrl = user?.avatar_url ?? null;

  if (avatarUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatarUrl}
        alt={name ?? "Profile picture"}
        width={SIZE_PX[size]}
        height={SIZE_PX[size]}
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
      {initialsFromName(name)}
    </div>
  );
}
