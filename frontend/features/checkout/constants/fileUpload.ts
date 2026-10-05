export const FILE_UPLOAD_LIMITS = {
  MAX_SIZE: 10 * 1024 * 1024, // 10MB
  MAX_FILES: 10,
} as const;

export const ALLOWED_FILE_EXTENSIONS = [
  '.pdf',
  '.doc', 
  '.docx',
  '.pptx',
  '.jpg',
  '.jpeg',
  '.png',
  '.xlsx'
] as const;

export const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'image/jpeg',
  'image/jpg',
  'image/png',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
] as const;

export const FILE_UPLOAD_ERRORS = {
  FILE_TOO_LARGE: 'Файл превышает максимально допустимый размер (10MB)',
  UNSUPPORTED_TYPE: 'Неподдерживаемый тип файла. Разрешены: PDF, DOC, DOCX, PPTX, JPG, PNG, XLSX',
  TOO_MANY_FILES: 'Превышено максимальное количество файлов (10)',
  UPLOAD_FAILED: 'Ошибка при загрузке файла'
} as const;
