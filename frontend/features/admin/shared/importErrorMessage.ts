const DEFAULT_IMPORT_ERROR = 'Импорт завершился с ошибкой'

export const resolveImportErrorMessage = (
  error: string | null,
  errorSample: string[],
): string => error || errorSample[0] || DEFAULT_IMPORT_ERROR
