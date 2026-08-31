"use client";

import { usePathname } from "next/navigation";
import { BottomNav } from "@/components/bottom-nav";
import { Sidebar } from "@/components/sidebar";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

// Sidebar and BottomNav mount simultaneously and are toggled via CSS
// (`hidden`/`lg:hidden`), not conditional rendering. A test that renders
// AppShell (or a full page) as one tree would see duplicate accessible
// names ("Dashboard"/"Coach") for getByRole queries — no such test exists
// today; BottomNav and Sidebar are each tested standalone.
export function AppShell({ children, locale }: { children: React.ReactNode; locale: string }) {
  const pathname = usePathname();
  const active = pathname.endsWith("/chat")
    ? "coach"
    : pathname.endsWith("/connectors")
      ? "connectors"
      : pathname.endsWith("/notifications")
        ? "notifications"
        : pathname.endsWith("/profile")
          ? "profile"
          : "dashboard";

  return (
    <SidebarProvider className="h-screen w-full flex-col overflow-hidden bg-background lg:flex-row">
      <Sidebar active={active} locale={locale} className="hidden lg:flex" />
      {/*
        Below `lg:`, the mobile-styled screens (authored for a ~390px phone
        frame) have no width cap of their own, so they'd stretch edge-to-edge
        on any desktop-width browser window under 1024px. Cap+center them
        here instead of in each screen, and let `bg-background` (the design's
        "outer canvas" color) show on the sides.
      */}
      <div className="mx-auto flex w-full max-w-[480px] flex-1 flex-col overflow-hidden bg-surface lg:mx-0 lg:max-w-none lg:flex-1 lg:bg-transparent">
        <SidebarTrigger className="m-3 hidden self-start lg:flex" />
        <main className="flex flex-1 flex-col overflow-y-auto">{children}</main>
        <BottomNav active={active} locale={locale} className="lg:hidden" />
      </div>
    </SidebarProvider>
  );
}
