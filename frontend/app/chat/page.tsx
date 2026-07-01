"use client";
import React from "react";
import Layout from "@/components/layout/Layout";
import ChatWindow from "@/components/chat/ChatWindow";
import QueryInput from "@/components/chat/QueryInput";
import { useStore } from "@/lib/store";
import { useRAGQuery } from "@/lib/hooks/useQuery";

export default function ChatPage() {
  const { messages, isLoading } = useStore();
  const { submitQuery } = useRAGQuery();
  
  // Show citations panel toggle if there are messages with sources available
  const hasCitations = messages.some(
    (msg) => msg.role === "assistant" && msg.response && msg.response.sources.length > 0
  );

  return (
    <Layout title="Query Chat Interface" showSourcesToggle={hasCitations}>
      <div className="flex h-[calc(100vh-104px)] flex-col justify-between max-w-4xl mx-auto overflow-hidden">
        {/* Chat message history box */}
        <div className="flex-1 overflow-y-auto pr-2">
          <ChatWindow />
        </div>
        
        {/* Chat prompt input box */}
        <div className="shrink-0 bg-white pt-3 border-t border-border">
          <QueryInput onSubmit={submitQuery} isLoading={isLoading} />
        </div>
      </div>
    </Layout>
  );
}
