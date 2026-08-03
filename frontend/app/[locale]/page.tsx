"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

import { SignInScreen } from "@/components/sign-in-screen";
import { useAuth } from "@/lib/auth-context";

export default function Home({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = use(params);
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.push(`/${locale}/dashboard`);
    }
  }, [isLoading, user, locale, router]);

  if (isLoading || user) return null;
  return <SignInScreen />;
}
