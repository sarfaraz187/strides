"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth-context";

export function RequireAuth({ children, locale }: { children: React.ReactNode; locale: string }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push(`/${locale}`);
    }
  }, [isLoading, user, locale, router]);

  if (isLoading || !user) return null;
  return <>{children}</>;
}
