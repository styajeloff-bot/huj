import { useApiError } from './useApiError';
import { useApiLoading } from './useApiLoading';

export interface UseApiOptions {
  immediate?: boolean;
  onError?: (error: any) => void;
  onSuccess?: (data: any) => void;
}

export interface UseApiReturn<T> {
  data: Readonly<Ref<T | null>>;
  isLoading: Ref<boolean>;
  error: Ref<any>;
  isError: ComputedRef<boolean>;
  execute: (...args: any[]) => Promise<T | null>;
  refresh: () => Promise<T | null>;
  clearError: () => void;
}

export function useApi<T = any>(
  apiCall: (...args: any[]) => Promise<T>,
  options: UseApiOptions = {}
): UseApiReturn<T> {
  const { immediate = false, onError, onSuccess } = options;
  
  const data = ref<T | null>(null);
  const { isLoading, withLoading } = useApiLoading();
  const { error, isError, clearError, handleError } = useApiError();
  
  let lastArgs: any[] = [];
  
  const execute = async (...args: any[]): Promise<T | null> => {
    lastArgs = args;
    clearError();
    
    try {
      const result = await withLoading(() => apiCall(...args));
      data.value = result;
      
      if (onSuccess) {
        onSuccess(result);
      }
      
      return result;
    } catch (err) {
      handleError(err);
      
      if (onError) {
        onError(err);
      }
      
      return null;
    }
  };
  
  const refresh = () => execute(...lastArgs);
  
  // Auto-execute if immediate is true
  if (immediate && process.client) {
    execute();
  }
  
  return {
    data: readonly(data) as Readonly<Ref<T | null>>,
    isLoading,
    error,
    isError,
    execute,
    refresh,
    clearError
  };
}

// Specialized composables for common patterns
export function useApiList<T = any>(
  apiCall: (params?: any) => Promise<{ data: T[]; total: number; page: number; limit: number }>,
  options: UseApiOptions = {}
) {
  const api = useApi(apiCall, options);
  
  const items = computed(() => api.data.value?.data || []);
  const total = computed(() => api.data.value?.total || 0);
  const currentPage = computed(() => api.data.value?.page || 1);
  const limit = computed(() => api.data.value?.limit || 20);
  
  return {
    ...api,
    items: readonly(items),
    total: readonly(total),
    currentPage: readonly(currentPage),
    limit: readonly(limit)
  };
}

export function useApiItem<T = any>(
  apiCall: (id: number) => Promise<T>,
  options: UseApiOptions = {}
) {
  return useApi(apiCall, options);
}