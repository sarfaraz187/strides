import { DashboardScreen } from "@/components/dashboard-screen";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <DashboardScreen locale={locale} />;
}
