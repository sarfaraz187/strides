"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";

import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";
import {
  Sidebar as SidebarPrimitive,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

function getMenuButtonClassName(collapsed: boolean) {
  return cn(
    "h-auto rounded-[10px] text-sm font-semibold",
    collapsed ? "w-8 justify-center p-2" : "gap-3 px-3 py-[11px]"
  );
}

export function Sidebar({
  active,
  locale,
  className,
}: {
  active: "dashboard" | "coach" | "connectors" | "profile";
  locale: string;
  className?: string;
}) {
  const t = useTranslations("nav");
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const { user } = useAuth();
  const displayName = user?.name ?? user?.email ?? "";
  const initials = displayName
    ? displayName
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((word) => word[0]?.toUpperCase())
        .join("")
    : "?";

  return (
    <SidebarPrimitive
      collapsible="none"
      className={cn(
        "bg-sidebar py-7 transition-[width] duration-200 ease-linear",
        collapsed ? "w-[76px] px-3" : "w-[240px] px-5",
        className
      )}
    >
      <SidebarHeader
        className={cn(
          "mb-9 flex-row items-center gap-2.5 p-0",
          collapsed && "justify-center"
        )}
      >
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] bg-sidebar-primary">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
            <path
              d="M4 17L9 10L13 14L20 5"
              stroke="var(--sidebar-primary-foreground)"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        {!collapsed && (
          <span className="text-lg font-bold tracking-[-0.3px] text-sidebar-accent-foreground">
            Strides
          </span>
        )}
      </SidebarHeader>

      <SidebarContent className="gap-1.5 overflow-visible">
        <SidebarMenu className={cn("gap-1.5", collapsed && "items-center")}>
          <SidebarMenuItem>
            <SidebarMenuButton
              render={<Link href={`/${locale}/dashboard`} />}
              isActive={active === "dashboard"}
              tooltip={collapsed ? t("dashboard") : undefined}
              className={getMenuButtonClassName(collapsed)}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
                <rect x="13" y="3" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
                <rect x="3" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
                <rect x="13" y="13" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.8" />
              </svg>
              {!collapsed && t("dashboard")}
            </SidebarMenuButton>
          </SidebarMenuItem>

          <SidebarMenuItem>
            <SidebarMenuButton
              render={<Link href={`/${locale}/chat`} />}
              isActive={active === "coach"}
              tooltip={collapsed ? t("coach") : undefined}
              className={getMenuButtonClassName(collapsed)}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M4 5h16v11H8l-4 4V5z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
              </svg>
              {!collapsed && t("coach")}
            </SidebarMenuButton>
          </SidebarMenuItem>

          <SidebarMenuItem>
            <SidebarMenuButton
              render={<Link href={`/${locale}/connectors`} />}
              isActive={active === "connectors"}
              tooltip={collapsed ? t("connectors") : undefined}
              className={getMenuButtonClassName(collapsed)}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path
                  d="M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3M6 10h12v4a6 6 0 01-6 6 6 6 0 01-6-6v-4z"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinejoin="round"
                />
              </svg>
              {!collapsed && t("connectors")}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="p-0">
        <Link
          href={`/${locale}/profile`}
          className={cn(
            "flex items-center gap-2.5 border-t border-sidebar-border pt-4",
            collapsed && "justify-center"
          )}
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px] bg-sidebar-primary text-xs font-semibold text-sidebar-primary-foreground">
            {initials}
          </div>
          {!collapsed && (
            <div className="text-[13px] font-medium text-sidebar-foreground">{displayName}</div>
          )}
        </Link>
      </SidebarFooter>
    </SidebarPrimitive>
  );
}
