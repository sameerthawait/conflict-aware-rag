import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useStore } from "@/lib/store";
import { RAGApiClient } from "@/lib/api";
import { Document } from "@/lib/types";

export function useDocuments() {
  const { apiKey } = useStore();
  const queryClient = useQueryClient();
  const api = new RAGApiClient("/api/proxy", apiKey);

  // 1. Fetch all documents
  const {
    data: documents = [],
    isLoading: isDocumentsLoading,
    error: documentsError,
    refetch: refetchDocuments
  } = useQuery<Document[]>({
    queryKey: ["documents", apiKey],
    queryFn: () => api.listDocuments(),
    enabled: true // Always load, or load if apiKey exists. If apiKey is optional or required, load anyway.
  });

  // 2. Upload file mutation
  const uploadMutation = useMutation({
    mutationFn: async ({
      file,
      onProgress
    }: {
      file: File;
      onProgress?: (pct: number) => void;
    }) => {
      return api.ingestFile(file, onProgress);
    },
    onSuccess: () => {
      // Invalidate documents list to refresh repository
      queryClient.invalidateQueries({ queryKey: ["documents", apiKey] });
    }
  });

  // 3. Delete document mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      return api.deleteDocument(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", apiKey] });
    }
  });

  // 4. Reindex document mutation
  const reindexMutation = useMutation({
    mutationFn: async (id: string) => {
      return api.reindexDocument(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", apiKey] });
    }
  });

  return {
    documents,
    isDocumentsLoading,
    documentsError,
    refetchDocuments,
    uploadFile: uploadMutation.mutateAsync,
    isUploading: uploadMutation.isPending,
    deleteDocument: deleteMutation.mutateAsync,
    isDeleting: deleteMutation.isPending,
    reindexDocument: reindexMutation.mutateAsync,
    isReindexing: reindexMutation.isPending
  };
}
