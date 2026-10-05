import { ref } from 'vue';

export interface UseApiLoadingReturn {
  isLoading: Ref<boolean>;
  startLoading: () => void;
  stopLoading: () => void;
  withLoading: <T>(asyncFn: () => Promise<T>) => Promise<T>;
}

export const useApiLoading = (initialState = false): UseApiLoadingReturn => {
  const isLoading = ref(initialState);
  
  const startLoading = () => {
    isLoading.value = true;
  };
  
  const stopLoading = () => {
    isLoading.value = false;
  };
  
  const withLoading = async <T>(asyncFn: () => Promise<T>): Promise<T> => {
    try {
      startLoading();
      const result = await asyncFn();
      return result;
    } finally {
      stopLoading();
    }
  };
  
  return {
    isLoading: readonly(isLoading),
    startLoading,
    stopLoading,
    withLoading
  };
};