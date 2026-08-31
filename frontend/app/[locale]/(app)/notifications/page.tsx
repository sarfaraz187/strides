import { NotificationsScreen } from "@/components/notifications-screen";

export default async function NotificationsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <NotificationsScreen locale={locale} />;
}
