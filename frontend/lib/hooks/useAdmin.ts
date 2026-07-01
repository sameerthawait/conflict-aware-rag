import { useQuery } from "@tanstack/react-query";
import { useStore } from "@/lib/store";
import { RAGApiClient } from "@/lib/api";
import { HealthStatus, CostReport } from "@/lib/types";

export function useAdmin() {
  const { apiKey } = useStore();
  const api = new RAGApiClient("/api/proxy", apiKey);

  // 1. System detailed health query
  const {
    data: health,
    isLoading: isHealthLoading,
    error: healthError,
    refetch: refetchHealth
  } = useQuery<HealthStatus>({
    queryKey: ["health", apiKey],
    queryFn: () => api.getHealth(),
    refetchInterval: 10000, // Poll every 10 seconds automatically
    retry: 1
  });

  // 2. Token cost reports query (authorized via Admin Key)
  const {
    data: costs,
    isLoading: isCostsLoading,
    error: costsError,
    refetch: refetchCosts
  } = useQuery<CostReport>({
    queryKey: ["costs", apiKey],
    queryFn: () => api.getCosts(),
    enabled: !!apiKey, // Load only if apiKey is entered
    refetchInterval: 30000, // Poll every 30 seconds
    retry: 1
  });

  return {
    health,
    isHealthLoading,
    healthError,
    refetchHealth,

    costs,
    isCostsLoading,
    costsError,
    refetchCosts
  };
}
