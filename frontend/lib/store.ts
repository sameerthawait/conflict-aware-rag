import { create } from "zustand";
import { ChatMessage, Source } from "./types";

interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  currentSources: Source[];
  apiKey: string;
  inputValue: string;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  setLoading: (loading: boolean) => void;
  setCurrentSources: (sources: Source[]) => void;
  clearChat: () => void;
  setApiKey: (key: string) => void;
  setInputValue: (val: string) => void;
}

export const useStore = create<ChatState>((set) => ({
  messages: [],
  isLoading: false,
  currentSources: [],
  apiKey: typeof window !== "undefined" ? localStorage.getItem("rag_api_key") || process.env.NEXT_PUBLIC_DEFAULT_API_KEY || "" : "",
  inputValue: "",
  
  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),
    
  updateMessage: (id, updates) =>
    set((state) => ({
      messages: state.messages.map((m) => (m.id === id ? { ...m, ...updates } : m))
    })),
    
  setLoading: (loading) => set({ isLoading: loading }),
  
  setCurrentSources: (sources) => set({ currentSources: sources }),
  
  clearChat: () => set({ messages: [], currentSources: [] }),
  
  setApiKey: (key) => {
    if (typeof window !== "undefined") {
      if (key) {
        localStorage.setItem("rag_api_key", key);
      } else {
        localStorage.removeItem("rag_api_key");
      }
    }
    set({ apiKey: key });
  },
  setInputValue: (val) => set({ inputValue: val })
}));
export default useStore;
