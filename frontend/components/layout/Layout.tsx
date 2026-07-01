"use client";
import React, { useState } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import SourcesPanel from "../chat/SourcesPanel";

interface LayoutProps {
  children: React.ReactNode;
  title: string;
  showSourcesToggle?: boolean;
}

export default function Layout({ children, title, showSourcesToggle = false }: LayoutProps) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isSourcesOpen, setIsSourcesOpen] = useState(true);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg font-sans text-primary select-none">
      {/* 1. Left Sidebar (Fixed 240px or Icon-only Collapsed) */}
      <Sidebar 
        isCollapsed={isSidebarCollapsed} 
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)} 
      />

      {/* 2. Main Content Frame */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar
          title={title}
          onToggleSources={showSourcesToggle ? () => setIsSourcesOpen(!isSourcesOpen) : undefined}
          isSourcesOpen={isSourcesOpen}
        />
        <main className="flex-1 overflow-y-auto bg-bg p-6 focus-visible:outline-none">
          {children}
        </main>
      </div>

      {/* 3. Right Collapsible Sources/Citations Panel */}
      {showSourcesToggle && isSourcesOpen && (
        <aside className="w-[320px] shrink-0 border-l border-border bg-surface overflow-y-auto lg:block hidden">
          <SourcesPanel onClose={() => setIsSourcesOpen(false)} />
        </aside>
      )}
    </div>
  );
}
