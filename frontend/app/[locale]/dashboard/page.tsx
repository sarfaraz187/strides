import { BottomNav } from "@/components/bottom-nav";
import { DashboardScreen } from "@/components/dashboard-screen";
import { RequireAuth } from "@/components/require-auth";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return (
    <RequireAuth locale={locale}>
      <div className="flex h-screen flex-col">
        <DashboardScreen />
        <BottomNav active="dashboard" locale={locale} />
      </div>
    </RequireAuth>
  );
}
