import { AppShell } from "@/components/app-shell";
import { RequireAuth } from "@/components/require-auth";

export default async function AppLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return (
    <RequireAuth locale={locale}>
      <AppShell locale={locale}>{children}</AppShell>
    </RequireAuth>
  );
}
