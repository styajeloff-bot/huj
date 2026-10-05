import { ref } from 'vue';

export interface ApiError {
  message: string;
  status?: number;
  details?: any;
  timestamp: Date;
}

export interface UseApiErrorReturn {
  error: Ref<ApiError | null>;
  isError: ComputedRef<boolean>;
  clearError: () => void;
  handleError: (error: any) => void;
  showError: (message: string, details?: any) => void;
}

export const useApiError = (): UseApiErrorReturn => {
  const error = ref<ApiError | null>(null);
  
  const isError = computed(() => error.value !== null);
  
  const clearError = () => {
    error.value = null;
  };
  
  const handleError = (err: any) => {
    let apiError: ApiError = {
      message: 'Произошла неизвестная ошибка',
      timestamp: new Date()
    };
    
    if (err instanceof Error) {
      apiError.message = err.message;
    } else if (typeof err === 'string') {
      apiError.message = err;
    } else if (err && typeof err === 'object') {
      if (err.data?.message) {
        apiError.message = err.data.message;
      } else if (err.message) {
        apiError.message = err.message;
      }
      
      if (err.status || err.statusCode) {
        apiError.status = err.status || err.statusCode;
      }
      
      if (err.data || err.details) {
        apiError.details = err.data || err.details;
      }
      
      // Handle specific status codes
      if (apiError.status) {
        switch (apiError.status) {
          case 400:
            apiError.message = 'Неверные данные запроса';
            break;
          case 401:
            apiError.message = 'Требуется авторизация';
            break;
          case 403:
            apiError.message = 'Недостаточно прав доступа';
            break;
          case 404:
            apiError.message = 'Ресурс не найден';
            break;
          case 409:
            apiError.message = 'Конфликт данных';
            break;
          case 422:
            apiError.message = 'Ошибка валидации данных';
            break;
          case 500:
            apiError.message = 'Внутренняя ошибка сервера';
            break;
          case 503:
            apiError.message = 'Сервис временно недоступен';
            break;
        }
      }
    }
    
    error.value = apiError;
  };
  
  const showError = (message: string, details?: any) => {
    error.value = {
      message,
      details,
      timestamp: new Date()
    };
  };
  
  return {
    error: readonly(error),
    isError,
    clearError,
    handleError,
    showError
  };
};