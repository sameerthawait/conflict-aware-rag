"use client";
import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useStore } from "@/lib/store";
import { 
  MessageSquare, 
  FileText, 
  Settings, 
  ChevronLeft, 
  ChevronRight,
  Key
} from "lucide-react";
import clsx from "clsx";

interface SidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export default function Sidebar({ isCollapsed, onToggleCollapse }: SidebarProps) {
  const pathname = usePathname();
  const { apiKey } = useStore();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  const hasKey = mounted ? !!apiKey : false;

  const navItems = [
    { name: "Query Chat", path: "/chat", icon: MessageSquare },
    { name: "Documents", path: "/documents", icon: FileText },
    { name: "Administration", path: "/admin", icon: Settings }
  ];

  return (
    <div
      className={clsx(
        "flex h-full flex-col border-r border-border bg-surface transition-all duration-base",
        isCollapsed ? "w-16" : "w-60"
      )}
    >
      {/* 1. Header Logo */}
      <div className="flex h-14 items-center justify-between border-b border-border px-4">
        {!isCollapsed && (
          <span className="font-sans text-base font-bold text-accent tracking-tight">
            RAG SYSTEM
          </span>
        )}
        <button
          onClick={onToggleCollapse}
          className="rounded p-1 text-secondary hover:bg-surface-2 transition-colors duration-fast"
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {isCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      {/* 2. Navigation Items */}
      <nav className="flex-1 space-y-1 py-4">
        {navItems.map((item) => {
          const isActive = pathname === item.path;
          const Icon = item.icon;

          return (
            <Link
              key={item.path}
              href={item.path}
              className={clsx(
                "group flex items-center px-4 py-2.5 font-sans text-sm font-medium transition-all duration-fast relative",
                isActive
                  ? "bg-accent text-white border-l-4 border-accent-hover"
                  : "text-secondary hover:bg-surface-2 hover:text-primary"
              )}
            >
              <Icon
                size={18}
                className={clsx(
                  "shrink-0",
                  isActive ? "text-white" : "text-muted group-hover:text-primary"
                )}
              />
              {!isCollapsed && (
                <span className="ml-3 transition-opacity duration-base">
                  {item.name}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* 3. Footer Auth/API Status */}
      <div className="border-t border-border p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            <Key size={16} className={hasKey ? "text-success" : "text-danger"} />
            {!isCollapsed && (
              <span className="font-sans text-xs text-secondary truncate">
                {hasKey ? "API Key Loaded" : "Key Required"}
              </span>
            )}
          </div>
          {!isCollapsed && (
            <span
              className={clsx(
                "h-2 w-2 rounded-full",
                hasKey ? "bg-success" : "bg-danger"
              )}
            />
          )}
        </div>
      </div>
    </div>
  );
}
