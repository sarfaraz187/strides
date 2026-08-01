import { BottomNav } from "@/components/bottom-nav";
import { DashboardScreen } from "@/components/dashboard-screen";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return (
    <div className="flex h-screen flex-col">
      <DashboardScreen />
      <BottomNav active="dashboard" locale={locale} />
    </div>
  );
}
