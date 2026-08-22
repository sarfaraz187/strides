export function Logo({
  size = 16,
  strokeWidth = 2.2,
  stroke = "#D8DED0",
  className,
}: {
  size?: number;
  strokeWidth?: number;
  stroke?: string;
  className?: string;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4 17L9 10L13 14L20 5" stroke={stroke} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
