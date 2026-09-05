"use client";

import { Bell, LayoutGrid, Lock, MessageSquare } from "lucide-react";
import { useTranslations } from "next-intl";
import Image from "next/image";
import Link from "next/link";

import { Avatar } from "@/components/avatar";
import { ChatSidebar } from "@/components/chat-sidebar";
import { NotificationBadge } from "@/components/notification-badge";
import { useAuth } from "@/lib/auth-context";
import { useNotifications } from "@/hooks/use-notifications";
import { cn } from "@/lib/utils";
import { Sidebar as SidebarPrimitive, SidebarContent, SidebarFooter, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem, SidebarTrigger, useSidebar } from "@/components/ui/sidebar";

function getMenuButtonClassName(collapsed: boolean) {
  return cn("h-auto rounded-xl text-sm font-semibold", collapsed ? "w-8 justify-center p-2" : "gap-3 px-3 py-2.5");
}

export function Sidebar({
  active,
  locale,
  activeConversationId,
  className,
}: {
  active: "dashboard" | "coach" | "connectors" | "notifications" | "profile";
  locale: string;
  activeConversationId?: string;
  className?: string;
}) {
  const t = useTranslations("nav");
  const { state, toggleSidebar } = useSidebar();
  const collapsed = state === "collapsed";
  const { user } = useAuth();
  const displayName = user?.name ?? user?.email ?? "";
  const { unreadCount } = useNotifications();

  return (
    <SidebarPrimitive collapsible="none" className={cn("bg-sidebar py-5 transition-[width] duration-200 ease-linear", collapsed ? "w-19 px-3" : "w-82 px-3", className)}>
      <SidebarHeader className={cn("mb-5 flex-row items-center gap-2.5 p-0", collapsed ? "flex-col justify-center gap-3" : "justify-between")}>
        <div className={cn("flex items-center gap-2.5", collapsed && "flex-col gap-3")}>
          {collapsed ? (
            <button type="button" onClick={toggleSidebar} aria-label="Toggle Sidebar" className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg">
              <Image src="/icon-512.png" alt="Strides" width={40} height={40} className="h-full w-full object-cover" />
            </button>
          ) : (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg">
              <Image src="/icon-512.png" alt="Strides" width={40} height={40} className="h-full w-full object-cover" />
            </div>
          )}
          {!collapsed && <span className="text-lg font-bold tracking-[-0.3px] text-sidebar-accent-foreground">Strides</span>}
        </div>
        {!collapsed && <SidebarTrigger className="text-sidebar-foreground/60 hover:text-sidebar-foreground" />}
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
              <LayoutGrid size={18} strokeWidth={1.8} />
              {!collapsed && t("dashboard")}
            </SidebarMenuButton>
          </SidebarMenuItem>

          <SidebarMenuItem>
            <SidebarMenuButton render={<Link href={`/${locale}/chat`} />} isActive={active === "coach"} tooltip={collapsed ? t("coach") : undefined} className={getMenuButtonClassName(collapsed)}>
              <MessageSquare size={18} strokeWidth={1.8} />
              {!collapsed && t("coach")}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>

        {active === "coach" && !collapsed && <ChatSidebar locale={locale} activeConversationId={activeConversationId} compact />}

        <SidebarMenu className={cn("gap-1.5", collapsed && "items-center")}>
          <SidebarMenuItem>
            <SidebarMenuButton
              render={<Link href={`/${locale}/connectors`} />}
              isActive={active === "connectors"}
              tooltip={collapsed ? t("connectors") : undefined}
              className={getMenuButtonClassName(collapsed)}
            >
              <Lock size={18} strokeWidth={1.8} />
              {!collapsed && t("connectors")}
            </SidebarMenuButton>
          </SidebarMenuItem>

          <SidebarMenuItem>
            <SidebarMenuButton
              render={<Link href={`/${locale}/notifications`} />}
              isActive={active === "notifications"}
              tooltip={collapsed ? t("notifications") : undefined}
              className={cn(getMenuButtonClassName(collapsed), "relative")}
            >
              <span className="relative">
                <Bell size={18} strokeWidth={1.8} />
                <NotificationBadge count={unreadCount} />
              </span>
              {!collapsed && t("notifications")}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="p-0">
        <Link href={`/${locale}/profile`} className={cn("flex items-center gap-2.5 border-t border-sidebar-border pt-4", collapsed && "justify-center")}>
          <Avatar user={user} size="sm" className="rounded-lg bg-sidebar-primary text-sidebar-primary-foreground" />
          {!collapsed && <div className="text-sm font-medium text-sidebar-foreground">{displayName}</div>}
        </Link>
      </SidebarFooter>
    </SidebarPrimitive>
  );
}
