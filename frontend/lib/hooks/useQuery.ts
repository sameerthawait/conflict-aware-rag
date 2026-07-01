import { useMutation } from "@tanstack/react-query";
import { useStore } from "@/lib/store";
import { RAGApiClient } from "@/lib/api";
import { ChatMessage, RAGResponse, MultiPerspectiveRAGResponse } from "@/lib/types";

export function useRAGQuery() {
  const { apiKey, addMessage, setLoading, setCurrentSources } = useStore();

  const api = new RAGApiClient("/api/proxy", apiKey);

  const mutation = useMutation({
    mutationFn: async (queryText: string) => {
      // 1. Add user message to UI immediately
      const userMsgId = "user-" + Date.now();
      addMessage({
        id: userMsgId,
        role: "user",
        content: queryText,
        timestamp: Date.now()
      });

      // 2. Set loading status and append loading bubble
      setLoading(true);
      addMessage({
        id: "loading",
        role: "assistant",
        content: "",
        timestamp: Date.now()
      });

      try {
        const response = await api.queryMultiPerspective({ query: queryText });
        return { response, queryText };
      } catch (err: any) {
        throw { error: err, queryText };
      }
    },
    onSuccess: (data) => {
      // Remove loading message indicator
      useStore.setState((state) => ({
        messages: state.messages.filter((m) => m.id !== "loading")
      }));

      // Add final assistant message bubble
      const assistantMsgId = "assistant-" + Date.now();
      addMessage({
        id: assistantMsgId,
        role: "assistant",
        content: data.response.answer,
        response: data.response,
        timestamp: Date.now()
      });

      // Update current sources panel state
      if (data.response.sources) {
        setCurrentSources(data.response.sources);
      }
      setLoading(false);
    },
    onError: (errData: any) => {
      // Remove loading message indicator
      useStore.setState((state) => ({
        messages: state.messages.filter((m) => m.id !== "loading")
      }));

      const errorMsg = errData.error?.detail || errData.error?.message || "Failed to retrieve answer.";
      const assistantMsgId = "error-" + Date.now();
      
      // Add error feedback message bubble
      addMessage({
        id: assistantMsgId,
        role: "assistant",
        content: `Request processing failed: ${errorMsg}`,
        timestamp: Date.now(),
        error: errorMsg
      });
      setLoading(false);
    }
  });

  return {
    submitQuery: (queryText: string) => mutation.mutate(queryText),
    isLoading: mutation.isPending,
    error: mutation.error
  };
}
