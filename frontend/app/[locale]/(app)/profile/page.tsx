import { ProfileScreen } from "@/components/profile-screen";

export default async function ProfilePage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <ProfileScreen locale={locale} />;
}
